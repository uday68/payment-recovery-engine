# Razorpay Recovery Engine: Benchmark & Performance Tracking

This document serves as the single source of truth for all recovery benchmarks, multi-seed stability evaluations, and comparative analyses across strategies.

---

## 1. Executive Summary & Strategy Matrix

Every transaction is evaluated counterfactually under identical transaction conditions across three strategies:

1. **Always Retry (Naive Baseline):** The legacy approach of immediately retrying all failed payments regardless of failure reason.
2. **Rule-Based (Heuristic Baseline):** An industry-standard static routing policy mapping failure codes to fixed actions (e.g. `BANK_TIMEOUT` -> `RETRY_NOW`, `INSUFFICIENT_FUNDS` -> `SEND_REMINDER`).
3. **AI Decision Engine:** An expected-value optimizing machine learning engine (`RandomForestClassifier` trained on multi-trial distributions) governed by a safety policy engine with idempotency controls.

### End-to-End System Flow

```text
                         ┌──────────────────┐
                         │ Failed Payment   │
                         └────────┬─────────┘
                                  │
                                  ▼
                         ┌──────────────────┐
                         │ Feature Context  │
                         └────────┬─────────┘
                                  │
                                  ▼
                         ┌──────────────────┐
                         │ ML Model         │
                         │ P(success|X,A)   │
                         └────────┬─────────┘
                                  │
                            probabilities
                                  │
                                  ▼
                         ┌──────────────────┐
                         │ Decision Engine  │
                         │ Expected Value   │
                         └────────┬─────────┘
                                  │
                            recommendation
                                  │
                                  ▼
                         ┌──────────────────┐
                         │ Policy Engine    │
                         │ deterministic    │
                         │ guardrails       │
                         └────────┬─────────┘
                                  │
                       ┌──────────┴──────────┐
                       │                     │
                    APPROVE                BLOCK
                       │                     │
                       ▼                     ▼
                Recovery Command          NO_ACTION
                       │
                       ▼
                ┌──────────────┐
                │ Go Executor  │
                └──────┬───────┘
                       │
                       ▼
                    Gateway
                       │
                       ▼
                    Outcome
                       │
                       ▼
                Audit + Metrics
```

---

## 2. Multi-Seed Stability Benchmark (5 Random Seeds)

Run via:
```powershell
python backend/run_stability.py
```

### Aggregate Seed Results (1,000 Customers, 10,000 Total Payments per Seed)

| Seed | Failed Payments | At-Risk Revenue | Always Retry (₹) | Rule-Based (₹) | AI Engine (₹) | AI vs Always Retry | AI vs Rule-Based |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **1** | 3,020 | ₹15,356,524.82 | ₹5,762,572.32 | ₹7,650,196.15 | **₹8,241,580.83** | **+43.02%** | **+7.73%** |
| **2** | 3,029 | ₹15,432,331.85 | ₹6,064,587.71 | ₹7,909,474.16 | **₹8,413,203.36** | **+38.73%** | **+6.37%** |
| **3** | 3,067 | ₹15,765,172.29 | ₹6,006,345.20 | ₹7,584,962.26 | **₹7,982,195.34** | **+32.90%** | **+5.24%** |
| **4** | 3,058 | ₹15,289,628.01 | ₹5,972,236.83 | ₹7,798,148.73 | **₹8,363,149.63** | **+40.03%** | **+7.25%** |
| **5** | 2,992 | ₹15,315,915.18 | ₹5,857,471.91 | ₹7,543,897.89 | **₹8,121,766.42** | **+38.66%** | **+7.66%** |

---

## 3. Statistical Analysis

### AI vs Always Retry (Naive Benchmark)
* **Mean Revenue Improvement:** **+38.67%**
* **Standard Deviation:** **3.68%**
* **Range:** +32.90% to +43.02%
* **Win Rate:** **100% (5/5 seeds)**

### AI vs Rule-Based (Heuristic Benchmark)
* **Mean Revenue Improvement:** **+6.85%**
* **Standard Deviation:** **1.05%**
* **Range:** +5.24% to +7.73%
* **Win Rate:** **100% (5/5 seeds)**

> **Key Takeaway for Pitch:**  
> The standard deviation of improvement against the Rule-Based strategy is exceptionally tight at **1.05%**. This demonstrates that the AI's advantage is structural and algorithmic, not a product of stochastic variance or favorable seeds.

---

## 4. Single-Batch Controlled Experiment (Detailed Diagnostics)

Run via:
```powershell
python backend/run_experiment.py
```

### Strategy Performance Summary (Seed 42)

| Metric | Always Retry (Naive) | Rule-Based (Heuristic) | AI Decision Engine | AI vs Always Retry | AI vs Rule-Based |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Failed Payments** | 2,978 | 2,978 | 2,978 | - | - |
| **Recovered Count** | 1,173 | 1,529 | **1,616** | **+443 (+37.8%)** | **+87 (+5.7%)** |
| **Recovery Rate** | 39.39% | 51.34% | **54.26%** | **+14.87 pp** | **+2.92 pp** |
| **Gross Recovered Revenue** | ₹6,031,208.04 | ₹7,743,805.85 | **₹8,255,913.70** | **+₹2,224,705.66 (+36.89%)** | **+₹512,107.85 (+6.61%)** |
| **Intervention Costs** | ₹5,956.00 | ₹4,297.00 | **₹4,013.00** | **-₹1,943.00 (-32.6%)** | **-₹284.00 (-6.6%)** |
| **Net Recovered Revenue** | ₹6,025,252.04 | ₹7,739,508.85 | **₹8,251,900.70** | **+₹2,226,648.66 (+36.95%)** | **+₹512,391.85 (+6.62%)** |
| **Net Revenue / Failure** | ₹2,023.25 | ₹2,598.89 | **₹2,770.95** | **+₹747.70** | **+₹172.06** |

---

## 5. AI Action Breakdown & Gateway Load Reduction

A critical advantage of the AI Decision Engine is **operational efficiency** and **gateway health**:

```text
AI Action Distribution:
   RETRY_NOW:          70 ( 2.4%)
   RETRY_LATER:     1,194 (40.1%)
   SEND_REMINDER:   1,365 (45.8%)
   NO_ACTION:         349 (11.7%)
Total Retries:      1,264
```

### Gateway Health Impact:
* **Naive Strategy:** Fires **2,978 immediate retries**, contributing to bank rate-limiting, cascade failures during bank outages, and high transaction gateway fees.
* **AI Engine:** Fires only **70 immediate retries** and schedules **1,194 deferred retries**, reducing peak gateway congestion by **>57%** while recovering **+36.89% more revenue**.

---

## 6. How to Reproduce All Benchmarks

```powershell
# 1. Run full leak-free unit tests (103 Python tests + 100% Go tests)
python -m pytest -m "not integration"
cd backend/go-executor && go test ./... && cd ../..

# 2. Run 5-Fold GroupKFold ML Model Benchmark
python run_ml_audit.py

# 3. Run single controlled 3-way experiment with net economics
python backend/run_experiment.py

# 4. Run multi-seed stability evaluation
python backend/run_stability.py
```

---

## 7. Machine Learning Model Benchmark (5-Fold GroupKFold)

From `ml/evaluation_audit.json` (evaluated with zero group leakage across `payment_id`):

| Model Architecture | ROC-AUC | PR-AUC | Brier Score Loss | Log Loss | ECE | Preferred Status |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Dummy (Prior Classifier)** | 0.5000 ± 0.0000 | 0.3310 ± 0.0048 | 0.2214 ± 0.0016 | 0.6349 ± 0.0033 | 0.0045 ± 0.0039 | Baseline |
| **Logistic Regression (L2)** | 0.7697 ± 0.0029 | 0.5654 ± 0.0067 | 0.1749 ± 0.0007 | 0.4937 ± 0.0015 | 0.0080 ± 0.0023 | Linear Baseline |
| **Random Forest (Raw)** | **0.7897 ± 0.0029** | **0.6036 ± 0.0071** | **0.1699 ± 0.0011** | **0.4836 ± 0.0025** | **0.0124 ± 0.0021** | **Production Preferred** |
| **Random Forest (Sigmoid)** | 0.7913 ± 0.0033 | 0.6062 ± 0.0074 | 0.1826 ± 0.0012 | 0.5416 ± 0.0036 | 0.0975 ± 0.0029 | Degraded Calibration |
| **Random Forest (Isotonic)** | 0.7884 ± 0.0028 | 0.6028 ± 0.0073 | 0.1706 ± 0.0011 | 0.4901 ± 0.0026 | 0.0163 ± 0.0024 | Sub-fold Overfitting |

*For deep dive on the calibration discrepancy and causal simulator limitations, see [Portfolio Applied ML Report](PORTFOLIO_APPLIED_ML_SYSTEMS_REPORT.md).*

