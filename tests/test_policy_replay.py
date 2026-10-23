import csv
import json
import os
import sys
import tempfile
import pytest

# Ensure PySpark workers use the active Python binary
os.environ["PYSPARK_PYTHON"] = sys.executable
os.environ["PYSPARK_DRIVER_PYTHON"] = sys.executable

from batch.policy_replay.replay_job import (
    evaluate_row_policies,
    replay_with_python,
    replay_with_spark,
)


@pytest.fixture(scope="module")
def spark_session():
    from pyspark.sql import SparkSession

    spark = (
        SparkSession.builder.master("local[1]")
        .appName("TestPolicyReplay")
        .config("spark.driver.memory", "512m")
        .config("spark.ui.enabled", "false")
        .getOrCreate()
    )
    yield spark
    spark.stop()


def test_evaluate_row_policies_canonical_agreement():
    """
    Verifies that evaluate_row_policies matches hand-calculated expected values.
    """
    probs = {
        "RETRY_NOW": 0.8,
        "RETRY_LATER": 0.4,
        "SEND_REMINDER": 0.2,
        "NO_ACTION": 0.0,
    }
    amount = 1000.0
    failure_code = "BANK_TIMEOUT"

    row_eval = evaluate_row_policies(amount, failure_code, probs, margin=1.0)

    # Always retry: RETRY_NOW, cost 2.0, gross = 0.8 * 1000 = 800, net = 800 - 2 = 798
    assert row_eval["always_retry"]["action"] == "RETRY_NOW"
    assert row_eval["always_retry"]["expected_gross"] == 800.0
    assert row_eval["always_retry"]["cost"] == 2.0
    assert row_eval["always_retry"]["expected_net_ev"] == 798.0

    # Naive rule for BANK_TIMEOUT is RETRY_NOW
    assert row_eval["naive_rule"]["action"] == "RETRY_NOW"
    assert row_eval["naive_rule"]["expected_gross"] == 800.0
    assert row_eval["naive_rule"]["expected_net_ev"] == 798.0

    # Expert rule for BANK_TIMEOUT is RETRY_LATER
    # prob = 0.4, cost = 2.0, gross = 400.0, net = 398.0
    assert row_eval["expert_rule"]["action"] == "RETRY_LATER"
    assert row_eval["expert_rule"]["expected_gross"] == 400.0
    assert row_eval["expert_rule"]["expected_net_ev"] == 398.0

    # AI policy: RETRY_NOW has highest EV (798.0), prob=0.8 >= 0.50, EV >= 50.0 -> ALLOWED
    assert row_eval["ai_policy"]["action"] == "RETRY_NOW"
    assert row_eval["ai_policy"]["policy_allowed"] is True
    assert row_eval["ai_policy"]["expected_gross"] == 800.0
    assert row_eval["ai_policy"]["expected_net_ev"] == 798.0


def test_spark_matches_python_evaluation_on_fixture(spark_session):
    """
    Proves that PySpark batch execution and Python sequential execution
    produce identical results on a known multi-transaction fixture.
    """
    fixture_data = [
        {
            "payment_id": "pay_fix_001",
            "amount": 5000.0,
            "failure_code": "BANK_TIMEOUT",
            "probabilities": json.dumps({"RETRY_NOW": 0.85, "RETRY_LATER": 0.40, "SEND_REMINDER": 0.10, "NO_ACTION": 0.0}),
        },
        {
            "payment_id": "pay_fix_002",
            "amount": 2500.0,
            "failure_code": "INSUFFICIENT_FUNDS",
            "probabilities": json.dumps({"RETRY_NOW": 0.10, "RETRY_LATER": 0.20, "SEND_REMINDER": 0.70, "NO_ACTION": 0.0}),
        },
        {
            "payment_id": "pay_fix_003",
            "amount": 100.0,
            "failure_code": "NETWORK_ERROR",
            "probabilities": json.dumps({"RETRY_NOW": 0.30, "RETRY_LATER": 0.25, "SEND_REMINDER": 0.05, "NO_ACTION": 0.0}),
        },
        {
            "payment_id": "pay_fix_004",
            "amount": 7500.0,
            "failure_code": "LIMIT_EXCEEDED",
            "probabilities": json.dumps({"RETRY_NOW": 0.15, "RETRY_LATER": 0.65, "SEND_REMINDER": 0.35, "NO_ACTION": 0.0}),
        },
    ]

    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, newline="") as tf:
        writer = csv.DictWriter(tf, fieldnames=["payment_id", "amount", "failure_code", "probabilities"])
        writer.writeheader()
        writer.writerows(fixture_data)
        temp_csv_path = tf.name

    try:
        # Run canonical Python replay
        python_results = replay_with_python(fixture_data, margin=1.0)

        # Run PySpark replay on the exported CSV
        spark_results = replay_with_spark(spark_session, temp_csv_path, margin=1.0)

        # Assert identical high-level counts
        assert spark_results["total_records"] == python_results["total_records"] == 4
        assert spark_results["total_at_risk_amount"] == python_results["total_at_risk_amount"] == 15100.0

        # Assert exact agreement per strategy
        for strategy in ["always_retry", "naive_rule", "expert_rule", "ai_policy"]:
            spark_strat = spark_results["strategies"][strategy]
            py_strat = python_results["strategies"][strategy]

            assert spark_strat["expected_gross_recovered"] == pytest.approx(py_strat["expected_gross_recovered"], abs=1e-2)
            assert spark_strat["total_intervention_cost"] == pytest.approx(py_strat["total_intervention_cost"], abs=1e-2)
            assert spark_strat["expected_net_ev"] == pytest.approx(py_strat["expected_net_ev"], abs=1e-2)
            assert spark_strat["action_distribution"] == py_strat["action_distribution"]

    finally:
        if os.path.exists(temp_csv_path):
            os.remove(temp_csv_path)
