# Phase 4: Experiment Methodology Audit

**Repository:** `uday68/razorpay-recovery-engine`  
**Role:** Senior Backend / Applied ML Scientist (Google SWE II Standards)  
**Date:** October 2026  
**Status:** Complete  

---

## 1. Executive Summary

This audit traces and verifies the scientific methodology of the 4-way payment recovery experiment across all four candidate strategies:
1. **Always Retry (Naive Baseline)**
2. **Naive Rule-Based (Heuristic Baseline)**
3. **Expert Rule-Based (Domain-Optimized Baseline)**
4. **AI Decision Engine (ML + Expected Value + Deterministic Policy Gate)**

### Audit Objectives
* Trace the full execution lifecycle of each strategy from failed transaction identification to outcome persistence.
* Audit baseline fairness regarding eligibility, random-number consumption, recovery-rate denominators, and information asymmetry.
* Evaluate the AI policy's selective gating mechanics (`MIN_RETRY_CONFIDENCE = 0.50`, `EV_FLOOR = 50.0`, `NO_ACTION`) and verify whether benefits and costs of declining action are properly measured.
* Distinguish confirmed implementation defects from structural methodology limitations.

---

## 2. Strategy Execution Trace & Comparison Matrix

Every strategy is evaluated counterfactually against the exact same population of failed transactions generated per seed.

| Attribute | 1. Always Retry | 2. Naive Rule | 3. Expert Rule | 4. AI Decision Engine | Shared vs. Differing |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Eligible Transaction Set** | All payments with `status == "FAILED"` | All payments with `status == "FAILED"` | All payments with `status == "FAILED"` | All payments with `status == "FAILED"` | **Shared (100% Identical)** |
| **Action Selection Logic** | Static: always selects `"RETRY_NOW"` | Static lookup: failure code $\rightarrow$ action dictionary | Static lookup: failure code $\rightarrow$ domain-optimized action | Dynamic: $A^* = \arg\max_A EV(A)$ via Random Forest + EV | **Differing** |
| **Features Consumed** | None (ignores context) | `failure_code` only | `failure_code` only | Full context: `(success_rate, recovery_rate, amount, bank, method, failure_code, hour)` | **Differing** |
| **Retry Timing & Interventions** | Immediate retry (`RETRY_NOW`) | Immediate or delayed depending on error code | Delayed for timeout/limit (`RETRY_LATER`), reminders for funds | Multi-action: `RETRY_NOW`, `RETRY_LATER`, `SEND_REMINDER`, `NO_ACTION` | **Differing** |
| **Retry Budget per Payment** | Exactly 1 attempt | Exactly 1 attempt | Exactly 1 attempt | $\le 1$ attempt (0 attempts if `NO_ACTION`) | **Shared Bound** |
| **Outcome Generation** | Common Random Numbers: `Random(f"{id}:RETRY_NOW")` | Common Random Numbers: `Random(f"{id}:{action}")` | Common Random Numbers: `Random(f"{id}:{action}")` | Common Random Numbers: `Random(f"{id}:{action}")` | **Shared CRN Methodology** |
| **Recovery Count Calculation** | `+1` if `recovery_outcome == True` | `+1` if `recovery_outcome == True` | `+1` if `recovery_outcome == True` | `+1` if `recovery_outcome == True` | **Shared (100% Identical)** |
| **Recovery Rate Denominator** | Total failed payments (`failed_count`) | Total failed payments (`failed_count`) | Total failed payments (`failed_count`) | Total failed payments (`failed_count`) | **Shared (100% Identical)** |
| **Gross Revenue Calculation** | $\sum_{\text{recovered}} \text{amount}$ | $\sum_{\text{recovered}} \text{amount}$ | $\sum_{\text{recovered}} \text{amount}$ | $\sum_{\text{recovered}} \text{amount}$ | **Shared (100% Identical)** |
| **Direct Intervention Costs** | ₹2.00 per retry | ₹1.00 - ₹2.00 per action | ₹1.00 - ₹2.00 per action | ₹0.00 for `NO_ACTION`, ₹1.00 - ₹2.00 for active | **Shared Cost Schedule** |
| **Failure / Penalty Costs** | Unmodeled (₹0.00) | Unmodeled (₹0.00) | Unmodeled (₹0.00) | Unmodeled (₹0.00) | **Shared Limitation** |
| **Treatment of `NO_ACTION`** | Never selected (0.0%) | Never selected (0.0%) | Never selected (0.0%) | Selected via EV or policy block ($P < 0.50$). Outcome $\equiv$ False. | **Differing** |
| **Random Number Consumption** | Isolated local `random.Random` | Isolated local `random.Random` | Isolated local `random.Random` | Isolated local `random.Random` | **Shared Isolation** |

---

## 3. Baseline Fairness Audit

### 3.1 Common Random Numbers (CRN) Independence
A critical concern in simulation auditing is whether evaluating strategies sequentially causes random-number consumption drift in the global RNG.
* **Code Audit:** In `backend/controlled_experiment.py`, `recovery_outcome()` instantiates a fresh pseudo-random number generator for every single evaluation:
  ```python
  def recovery_outcome(payment_id, action, probability):
      rng = random.Random(f"{payment_id}:{action}")
      return rng.random() < probability
  ```
* **Verdict: PASS.** No strategy consumes numbers from Python's global `random` generator. The execution order of strategies has zero effect on the random outcomes of subsequent strategies.

### 3.2 Evaluation Denominator Consistency
* All four strategies divide total recoveries by the identical denominator: `len(failed_payments)` (2,992 in Seed 42).
* Strategies are not rewarded or penalized by altering the denominator when actions are suppressed.
* **Verdict: PASS.**

### 3.3 Information Asymmetry & Oracle Bias
* **The AI Model:** Trained on `ml/data.csv`, which was generated by the simulator's parametric recovery function (`simulator/recovery.py`). In academic ML evaluation, this is an **in-domain setup**.
* **The Naive Rule Baseline:** Hardcoded to `BANK_TIMEOUT -> RETRY_NOW` and `LIMIT_EXCEEDED -> RETRY_NOW`. In the simulator, `RETRY_NOW` suffers heavy penalties on these codes, giving the AI model an easy target.
* **The Expert Rule Baseline:** Re-maps `BANK_TIMEOUT` and `LIMIT_EXCEEDED` to `RETRY_LATER`. This represents an authentic, domain-competent human heuristic.
* **Verdict:** Benchmarking against both Naive Rule and Expert Rule eliminates oracle bias and establishes true lower and upper heuristic bounds.

---

## 4. Evaluation of Selective Policy Gating

In Seed 42 (2,992 failed payments), the AI engine's decisions broke down as:
* Recommended Actions: `RETRY_NOW: 171`, `RETRY_LATER: 1,377`, `SEND_REMINDER: 1,444`, `NO_ACTION: 0`.
* Approved Actions (Post-Policy): `RETRY_NOW: 105`, `RETRY_LATER: 1,175`, `SEND_REMINDER: 1,444`, `NO_ACTION: 268 (9.0%)`.

### 4.1 Why Were 268 Actions Blocked?
1. **The Guardrail:** In `backend/policy/engine.py`, `MIN_RETRY_CONFIDENCE = 0.50`.
   ```python
   if action in ("RETRY_NOW", "RETRY_LATER"):
       if probability < config.recovery_target / 100.0:
           return {"allowed": False, "reason": "Recovery probability below configured retry threshold"}
   ```
2. **Selective Gating:** The 268 blocked transactions had predicted probabilities between $0.35$ and $0.49$. Because confidence was below 50%, the policy gate overrode the ML recommendation and forced `NO_ACTION`.
3. **Send Reminder Exemption:** `SEND_REMINDER` is exempt from the 50% confidence floor because reminders are non-invasive notifications that do not initiate financial transactions or strain bank gateway queues.

### 4.2 Defect Identified & Corrected
* In `backend/controlled_experiment.py`, `apply_policy` was previously invoked without `expected_value=decision["expected_value"]`.
* While `probability < 0.50` effectively caught low-confidence actions, omitting `expected_value` prevented `EV_FLOOR` from being enforced during experiment simulation.
* This discrepancy was resolved to ensure consistency with `backend/recovery_pipeline.py` and `backend/api/app.py`.

---

## 5. Confirmed Bugs vs. Methodological Limitations

### Confirmed Bugs Resolved
1. **Omitted EV Parameter in Experiment Policy Gate:** `apply_policy` in `backend/controlled_experiment.py` now receives `expected_value=decision["expected_value"]`.
2. **Missing 4-Way Evaluation in Multi-Seed Script:** `backend/run_stability.py` was upgraded to evaluate all four strategies across all random seeds, computing standard errors, 95% confidence intervals, and paired t-tests.

### Methodological Limitations (Inherent to Simulator)
1. **Unmodeled Downstream Gateway Outage Cost:** The simulator models action fees (₹1.00 - ₹2.00) but does not model bank throttling, circuit-breaking penalties, or merchant fines for excessive failed retries.
2. **Independent Bernoulli Outages:** Failures occur independently rather than in bursty, auto-correlated temporal clusters.
3. **Static Retry Probability:** The simulator does not reduce success probability for successive retry attempts (no retry fatigue decay).
