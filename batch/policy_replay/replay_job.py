#!/usr/bin/env python3
"""
PySpark Batch Policy Re-evaluation Job
======================================
Reads stored payment recovery decision/outcome history (CSV or Parquet) exported
from PostgreSQL or operational stores, and counterfactually evaluates alternative
recovery policies:

1. Always Retry: Naive baseline retrying all failed transactions immediately.
2. Naive Rule-Based: Static heuristic mapping from failure code to action.
3. Expert Rule-Based: Domain-tuned failure-to-action routing table.
4. Current AI Decision Policy: Expected-value maximization + deterministic guardrails.

Usage:
    python batch/policy_replay/replay_job.py --input path/to/decisions.csv --margin 1.0
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

# Ensure project root is in sys.path
ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Ensure Python executable is correctly set for PySpark worker processes
if "PYSPARK_PYTHON" not in os.environ:
    os.environ["PYSPARK_PYTHON"] = sys.executable
if "PYSPARK_DRIVER_PYTHON" not in os.environ:
    os.environ["PYSPARK_DRIVER_PYTHON"] = sys.executable

from backend.decision.engine import ACTION_COSTS, choose_action, expected_value
from backend.policy.engine import apply_policy
from backend.rule_baseline import choose_expert_rule_action, choose_rule_action


def parse_probabilities(raw_probs: Any) -> Dict[str, float]:
    """
    Parses probabilities whether stored as dict, json string, or formatted string.
    Safely unescapes CSV and JSON artifacts.
    """
    if isinstance(raw_probs, dict):
        return {k: float(v) for k, v in raw_probs.items()}

    if isinstance(raw_probs, str):
        cleaned = raw_probs.strip()
        # Handle doubled quotes or outer quotes from CSV serializers
        if cleaned.startswith('"') and cleaned.endswith('"'):
            cleaned = cleaned[1:-1]
        cleaned = cleaned.replace('""', '"')
        try:
            parsed = json.loads(cleaned)
            # In case of double serialization
            if isinstance(parsed, str):
                parsed = json.loads(parsed)
            if isinstance(parsed, dict):
                return {k: float(v) for k, v in parsed.items()}
        except Exception:
            pass

    return {
        "RETRY_NOW": 0.5,
        "RETRY_LATER": 0.5,
        "SEND_REMINDER": 0.5,
        "NO_ACTION": 0.0,
    }


def evaluate_row_policies(
    amount: float,
    failure_code: str,
    probabilities: Dict[str, float],
    margin: float = 1.0,
) -> Dict[str, Any]:
    """
    Replays all 4 recovery strategies on a single transaction using the exact
    canonical domain engines from backend/decision, backend/rule_baseline, and backend/policy.
    """
    amt = float(amount or 0.0)
    fc = str(failure_code or "UNKNOWN").strip().upper()
    probs = parse_probabilities(probabilities)

    # 1. Always Retry
    ar_action = "RETRY_NOW"
    ar_prob = float(probs.get(ar_action, 0.0))
    ar_cost = float(ACTION_COSTS.get(ar_action, 2.0))
    ar_gross = ar_prob * amt
    ar_net_ev = expected_value(ar_prob, amt, ar_action, margin=margin)

    # 2. Naive Rule
    nr_action = choose_rule_action(fc)
    nr_prob = float(probs.get(nr_action, 0.0))
    nr_cost = float(ACTION_COSTS.get(nr_action, 0.0))
    nr_gross = (nr_prob * amt) if nr_action != "NO_ACTION" else 0.0
    nr_net_ev = expected_value(nr_prob, amt, nr_action, margin=margin)

    # 3. Expert Rule
    er_action = choose_expert_rule_action(fc)
    er_prob = float(probs.get(er_action, 0.0))
    er_cost = float(ACTION_COSTS.get(er_action, 0.0))
    er_gross = (er_prob * amt) if er_action != "NO_ACTION" else 0.0
    er_net_ev = expected_value(er_prob, amt, er_action, margin=margin)

    # 4. Current AI Decision Engine + Deterministic Policy Guardrails
    ai_decision = choose_action(amt, probs, margin=margin)
    recommended_action = ai_decision["action"]
    rec_prob = float(probs.get(recommended_action, 0.0))
    rec_ev = float(ai_decision.get("expected_value", 0.0))

    policy_eval = apply_policy(
        action=recommended_action,
        amount=amt,
        probability=rec_prob,
        expected_value=rec_ev,
    )
    approved_action = policy_eval["action"]
    appr_prob = float(probs.get(approved_action, 0.0))
    ai_cost = float(ACTION_COSTS.get(approved_action, 0.0))
    ai_gross = (appr_prob * amt) if approved_action != "NO_ACTION" else 0.0
    ai_net_ev = expected_value(appr_prob, amt, approved_action, margin=margin)

    return {
        "amount": amt,
        "failure_code": fc,
        "always_retry": {
            "action": ar_action,
            "cost": ar_cost,
            "expected_gross": ar_gross,
            "expected_net_ev": ar_net_ev,
        },
        "naive_rule": {
            "action": nr_action,
            "cost": nr_cost,
            "expected_gross": nr_gross,
            "expected_net_ev": nr_net_ev,
        },
        "expert_rule": {
            "action": er_action,
            "cost": er_cost,
            "expected_gross": er_gross,
            "expected_net_ev": er_net_ev,
        },
        "ai_policy": {
            "recommended_action": recommended_action,
            "action": approved_action,
            "policy_allowed": policy_eval["allowed"],
            "policy_reason": policy_eval["reason"],
            "cost": ai_cost,
            "expected_gross": ai_gross,
            "expected_net_ev": ai_net_ev,
        },
    }


def aggregate_replay_results(row_evaluations: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Computes summary metrics and strategy comparisons over an iterable of evaluated rows.
    """
    total_count = 0
    total_at_risk_amount = 0.0

    strategies = ["always_retry", "naive_rule", "expert_rule", "ai_policy"]
    stats: Dict[str, Dict[str, Any]] = {
        s: {
            "total_expected_gross": 0.0,
            "total_cost": 0.0,
            "total_expected_net_ev": 0.0,
            "action_counts": {},
        }
        for s in strategies
    }
    stats["ai_policy"]["policy_allowed"] = 0
    stats["ai_policy"]["policy_blocked"] = 0

    for item in row_evaluations:
        total_count += 1
        total_at_risk_amount += item["amount"]

        for s in strategies:
            strat_res = item[s]
            stats[s]["total_expected_gross"] += strat_res["expected_gross"]
            stats[s]["total_cost"] += strat_res["cost"]
            stats[s]["total_expected_net_ev"] += strat_res["expected_net_ev"]

            act = strat_res["action"]
            stats[s]["action_counts"][act] = stats[s]["action_counts"].get(act, 0) + 1

        if item["ai_policy"]["policy_allowed"]:
            stats["ai_policy"]["policy_allowed"] += 1
        else:
            stats["ai_policy"]["policy_blocked"] += 1

    summary = {
        "total_records": total_count,
        "total_at_risk_amount": round(total_at_risk_amount, 2),
        "strategies": {},
    }

    for s in strategies:
        st = stats[s]
        summary["strategies"][s] = {
            "expected_gross_recovered": round(st["total_expected_gross"], 2),
            "total_intervention_cost": round(st["total_cost"], 2),
            "expected_net_ev": round(st["total_expected_net_ev"], 2),
            "action_distribution": st["action_counts"],
        }
        if s == "ai_policy":
            summary["strategies"][s]["policy_allowed_count"] = st["policy_allowed"]
            summary["strategies"][s]["policy_blocked_count"] = st["policy_blocked"]

    return summary


def replay_with_python(rows: Iterable[Dict[str, Any]], margin: float = 1.0) -> Dict[str, Any]:
    """
    Evaluates policy replay purely in Python (used for verification fixture and fallback).
    """
    evaluated = [
        evaluate_row_policies(
            amount=row.get("amount", 0.0),
            failure_code=row.get("failure_code", "UNKNOWN"),
            probabilities=row.get("probabilities", {}),
            margin=margin,
        )
        for row in rows
    ]
    return aggregate_replay_results(evaluated)


def replay_with_spark(spark_session: Any, input_path: str, margin: float = 1.0) -> Dict[str, Any]:
    """
    Evaluates policy replay using PySpark on local/cluster dataset (Parquet or CSV).
    """
    p = str(input_path).lower()
    if p.endswith(".parquet"):
        df = spark_session.read.parquet(input_path)
    else:
        df = (
            spark_session.read.option("header", "true")
            .option("quote", '"')
            .option("escape", '"')
            .csv(input_path)
        )

    # Collect rows for partitioned execution
    def process_partition(iterator):
        for row in iterator:
            r_dict = row.asDict()
            amt = float(r_dict.get("amount", 0.0) or 0.0)
            fc = str(r_dict.get("failure_code", "") or "UNKNOWN")
            raw_p = r_dict.get("probabilities", {})
            yield evaluate_row_policies(amt, fc, raw_p, margin=margin)

    evaluated_rdd = df.rdd.mapPartitions(process_partition)
    evaluated_records = evaluated_rdd.collect()

    return aggregate_replay_results(evaluated_records)


def main():
    parser = argparse.ArgumentParser(description="PySpark Batch Policy Replay Job")
    parser.add_argument("--input", required=True, help="Input CSV or Parquet file path")
    parser.add_argument("--output", default=None, help="Optional output JSON summary path")
    parser.add_argument("--margin", type=float, default=1.0, help="Merchant recovery margin (default: 1.0)")
    args = parser.parse_args()

    print(f"Starting Policy Replay Job on '{args.input}' (margin={args.margin})...")

    from pyspark.sql import SparkSession

    spark = (
        SparkSession.builder.master("local[*]")
        .appName("PolicyReplayBatchJob")
        .config("spark.driver.memory", "1g")
        .config("spark.sql.shuffle.partitions", "2")
        .getOrCreate()
    )

    try:
        results = replay_with_spark(spark, args.input, margin=args.margin)
        print("\n=== POLICY REPLAY SUMMARY ===")
        print(json.dumps(results, indent=2))

        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(results, f, indent=2)
            print(f"\nSaved replay summary to: {args.output}")

    finally:
        spark.stop()


if __name__ == "__main__":
    main()
