# Batch Policy Re-evaluation Engine (PySpark)

This module provides an offline, batch evaluation pipeline for replaying historical payment recovery decisions against alternative routing and decision policies.

---

## 1. Supported Policies

The re-evaluation engine loads historical failure contexts (exported from PostgreSQL `recovery_audit` or transaction data lakes) and computes the counterfactual expected recovery value across 4 distinct strategies:

1. **Always Retry (Naive Baseline):** Unconditionally executes `RETRY_NOW` on every failed payment ($Cost = \text{₹}2.00$).
2. **Naive Rule-Based (Heuristic):** Static failure-code mapping (e.g., `BANK_TIMEOUT` $\to$ `RETRY_NOW`, `INSUFFICIENT_FUNDS` $\to$ `SEND_REMINDER`).
3. **Expert Rule-Based (Domain-Tuned):** Industry-optimized static mapping (e.g., `BANK_TIMEOUT` $\to$ `RETRY_LATER`, `LIMIT_EXCEEDED` $\to$ `RETRY_LATER`).
4. **Current AI Decision Policy:** Expected-value optimization ($\arg\max EV(a)$) subject to deterministic policy guardrails (`MIN_RETRY_CONFIDENCE = 0.50`, `ev_floor = 50.0`).

---

## 2. Running Locally

### Prerequisites
* Java 17+ (Java 19 verified locally)
* Python 3.12 with `pyspark>=3.5.0`

### Execution Command
Run the replay job against an exported CSV or Parquet decision dataset:

```bash
# Replay against CSV export with 100% merchant margin
python batch/policy_replay/replay_job.py --input tests/fixtures/sample_decisions.csv --margin 1.0

# Replay against Parquet export with 2% payment aggregator margin
python batch/policy_replay/replay_job.py --input path/to/decisions.parquet --margin 0.02 --output summary.json
```

---

## 3. Scope & Limitations

> [!NOTE]
> **Local Evaluation Only:** This pipeline is built and verified for local workstation execution using Spark's local execution engine (`local[*]`). It is intended for offline backtesting, regression auditing, and policy sanity checks.
> 
> **No Cluster-Scale Claims:** This pipeline has not been benchmarked or tuned for petabyte-scale distributed execution across multi-node clusters (e.g., AWS EMR, GCP Dataproc, or Databricks). Performance claims are strictly limited to local single-node batch evaluation.
