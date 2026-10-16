# Phase 2: Payment Simulator & Decision Engine Audit

**Repository:** `uday68/razorpay-recovery-engine`  
**Evaluation Role:** Senior Backend / Applied ML Scientist (Google SWE II AI/ML Standards)  
**Date:** October 2026  
**Status:** Complete  

---

## 1. Executive Summary

A rigorous audit of the payment simulator (`simulator/generator.py`, `simulator/recovery.py`), dataset construction pipeline (`ml/dataset.py`), and strategy evaluation framework (`backend/controlled_experiment.py`) was conducted to evaluate:
1. Whether dataset origins and simulated outcomes are transparently characterized.
2. How counterfactual payment outcomes are generated and whether evaluation introduces selection bias.
3. Whether the simulation encodes realistic payment dynamics (bank downtime, diurnal rhythms, retry fatigue).
4. Whether baseline strategies represent authentic production benchmarks or artificially favor the ML policy.
5. How economic assumptions (merchant margin, action costs, net expected value) impact decision policy outcomes.

### Core Audit Verdict
* **Data Origin:** **100% Synthetic.** The data in `ml/data.csv` is generated via parametric distributions in `simulator/`. There is zero real cardholder PII or live merchant banking data.
* **Counterfactual Methodology:** **Scientifically Valid.** The simulator employs **Common Random Numbers (CRN)** seeded with `f"{payment_id}:{action}"`, guaranteeing that all competing strategies are evaluated against identical counterfactual outcomes without observational selection bias.
* **Baseline Fairness Defect Identified:** The "Rule-Based" baseline hardcodes `"BANK_TIMEOUT": "RETRY_NOW"` (yielding $+0.15$ probability) and `"LIMIT_EXCEEDED": "RETRY_NOW"` (yielding $-0.10$ penalty), whereas the simulator rewards `RETRY_LATER` ($+0.35$ and $+0.10$ respectively). The ML engine's $+8.03\%$ lift over the rule baseline is partly driven by comparing against a suboptimal rule configuration rather than an optimized domain-expert rule set.
* **Realism Gaps Documented:** Timestamps are uniformly distributed without diurnal transaction surges; bank downtime is modeled as independent Bernoulli draws rather than clustered Markovian outages; and cardholder retry fatigue does not decay with cumulative retry count.

---

## 2. Dataset & Generative Architecture Audit

### 2.1 Customer Profile Generation (`simulator/generator.py`)
Customer profiles are generated with two underlying latent variables:
* **Reliability:** Uniformly distributed over $[0.65, 0.98]$ representing the customer's baseline probability of payment success.
* **Recovery Chance:** Uniformly distributed over $[0.20, 0.80]$ representing the customer's propensity to resolve a failed transaction.

```python
reliability = random.uniform(0.65, 0.98)
total_payments = random.randint(20, 150)
for _ in range(total_payments):
    if random.random() < reliability:
        successful += 1
        continue
    failed += 1
    recovery_chance = random.uniform(0.20, 0.80)
    if random.random() < recovery_chance:
        recovered += 1
```

**Audit Observation:** This generative model creates realistic correlations between customer historical reliability (`success_rate`) and recovery potential (`recovery_rate`), preventing uninformative uniform noise.

### 2.2 Payment Generation & Transaction Features
Payments are drawn with:
* `amount`: Continuous uniform over $[\text{₹}100, \text{₹}10,000]$, rounded to 2 decimal places.
* `payment_method`: Discrete uniform over `["UPI", "CARD", "NETBANKING", "WALLET"]`.
* `bank`: Discrete uniform over `["HDFC", "ICICI", "SBI", "AXIS", "KOTAK"]`.
* `failure_code`: Assigned uniformly across `["BANK_TIMEOUT", "INSUFFICIENT_FUNDS", "CARD_EXPIRED", "NETWORK_ERROR", "LIMIT_EXCEEDED", "AUTHENTICATION_FAILED"]` whenever a failure occurs (base failure rate $\approx 30\%$).

---

## 3. Counterfactual Outcome Generation & Fairness

Evaluating payment recovery strategies on historical observational data is famously vulnerable to **confounding bias**: historical data only records the outcome of the action that was *actually taken*. 

### 3.1 Common Random Numbers (CRN) Implementation
In `backend/controlled_experiment.py`, counterfactual outcomes are evaluated using:

```python
def recovery_outcome(payment_id: str, action: str, probability: float) -> bool:
    rng = random.Random(f"{payment_id}:{action}")
    return rng.random() < probability
```

### 3.2 Methodological Strengths
1. **Deterministic Equivalence:** If Strategy A (Rule-Based) and Strategy B (AI Engine) both select `RETRY_LATER` for payment `pay_001`, they observe the **exact same boolean outcome**. Strategy B cannot claim an artificial win on an identical decision.
2. **Action Independence:** The random seed `f"{payment_id}:{action}"` ensures that an action's counterfactual outcome does not leak into an alternate action's outcome for the same payment.
3. **Variance Reduction:** By reusing the identical random seed per (payment, action) pair across strategies, the variance of the difference $\Delta = \text{Revenue}_{AI} - \text{Revenue}_{Rule}$ is minimized, enabling statistically rigorous comparisons across fewer seeds.

---

## 4. Simulator Limitations & Real-World Realism Gaps

| Payment Behavior | Real-World Payment System (Razorpay / UPI) | Current Simulator Implementation | Impact on Model Evaluation |
| :--- | :--- | :--- | :--- |
| **Diurnal Patterns** | Heavy transaction peaks during business hours and evening surges (8 PM - 10 PM IST). | Timestamps are drawn uniformly across 90 days (`random.randint(0, 90*24*60*60)`). | The model's `hour` feature provides marginal predictive signal since failure rates are uniform across time. |
| **Bank Outages** | Core Banking Systems (CBS) experience bursty, clustered downtimes lasting 15–60 minutes. | Failure codes are selected independently per transaction (`random.choice(FAILURE_CODES)`). | Downstream circuit breakers and retry policies are tested against static Bernoulli noise rather than correlated outage spikes. |
| **Retry Fatigue** | Success probability decreases exponentially with each successive retry attempt: $P(k) = P_0 \cdot e^{-\lambda k}$. | `recovery_probablity` calculates static probability independent of attempt history. | The simulator underestimates the cost of burning unnecessary retries. |
| **Amount Distribution** | Highly skewed log-normal / Pareto distribution (thousands of ₹50 micro-transactions, few ₹50,000 corporate transfers). | Uniform distribution over $[\text{₹}100, \text{₹}10,000]$. | Equal weighting across amounts can distort expected value maximization relative to high-value transactions. |

---

## 5. Baseline Integrity & The "In-Domain Oracle" Effect

### 5.1 Baseline Comparison
The 3-way evaluation compares three strategies:
1. **Always Retry Now (`baseline`):** Naively fires `RETRY_NOW` on every failed payment regardless of error code.
2. **Rule-Based Heuristic (`rule_based`):** Statically maps failure codes to recovery actions.
3. **AI Decision Engine (`ai`):** Predicts recovery probabilities using Random Forest, optimizes Expected Value ($EV = P \cdot \text{Amount} \cdot \text{Margin} - \text{Cost}$), and enforces deterministic safety policies.

### 5.2 The Rule Configuration Defect
In `backend/rule_baseline.py`:
```python
RULE_BASELINE = {
    "BANK_TIMEOUT": "RETRY_NOW",        # Simulator rewards RETRY_LATER (+0.35) vs RETRY_NOW (+0.15)
    "NETWORK_ERROR": "RETRY_NOW",
    "INSUFFICIENT_FUNDS": "SEND_REMINDER",
    "CARD_EXPIRED": "SEND_REMINDER",
    "LIMIT_EXCEEDED": "RETRY_NOW",       # Simulator penalizes RETRY_NOW (-0.10) vs RETRY_LATER (+0.10)
    "AUTHENTICATION_FAILED": "SEND_REMINDER",
}
```

In `simulator/recovery.py`:
```python
if payment.failure_code == "BANK_TIMEOUT":
    if action == "RETRY_LATER":
        probability += 0.35
    elif action == "RETRY_NOW":
        probability += 0.15
elif payment.failure_code == "LIMIT_EXCEEDED":
    if action == "RETRY_LATER":
        probability += 0.10
    elif action == "RETRY_NOW":
        probability -= 0.10
```

### 5.3 Audit Finding
* A seasoned payments engineer would naturally map `BANK_TIMEOUT` and `LIMIT_EXCEEDED` to `RETRY_LATER` (allowing core banking systems to recover or daily limits to reset).
* Because the rule baseline was configured with `RETRY_NOW` for these codes, it suffers significant probability penalties in the simulator.
* The ML model was trained on `data.csv`, which was generated by this exact simulator logic. The Random Forest easily learned that `RETRY_LATER` is superior for these failure codes.
* **Conclusion:** The AI model's $+8.03\%$ lift over the rule baseline is genuine within the code as written, but it partially reflects an **un-optimized rule baseline** rather than purely model superiority. An optimized rule set (`BANK_TIMEOUT` $\rightarrow$ `RETRY_LATER`, `LIMIT_EXCEEDED` $\rightarrow$ `RETRY_LATER`) would narrow the AI engine's performance advantage.

---

## 6. Action Economics & Merchant Margin Formulation

The decision engine maximizes net expected value:
$$\text{EV}(A) = P(A \mid X) \times \text{Amount} \times \text{Margin} - \text{Cost}(A)$$

### 6.1 Action Cost Schedule
* `RETRY_NOW`: ₹2.00 (Gateway API invocation fee)
* `RETRY_LATER`: ₹3.00 (Delayed queuing, scheduler state storage, and secondary API invocation)
* `SEND_REMINDER`: ₹1.50 (SMS / WhatsApp notification fee)
* `NO_ACTION`: ₹0.00 (Zero cost)

### 6.2 Merchant Margin Impact
When evaluating payment recovery at scale, recovering a ₹10,000 transaction does not yield ₹10,000 in net revenue for the payment orchestrator. The merchant retains the transaction capital, while the orchestrator or merchant operates on a Merchant Discount Rate (MDR) margin (typically $1.5\% - 3.0\%$).

* At $\text{Margin} = 1.0$ (Gross Revenue Mode), every recovery is profitable if $P \times \text{Amount} > \text{Cost}$.
* At $\text{Margin} = 0.02$ (2% MDR Net Margin Mode), a ₹100 transaction yields only ₹2.00 in gross margin. Spending ₹2.00 on `RETRY_NOW` or ₹3.00 on `RETRY_LATER` results in negative net economic return.
* The AI policy's margin awareness allows it to intelligently route micro-transactions to `NO_ACTION`, protecting merchant economics where naive baselines burn cash.

---

## 7. Audit Recommendations & Technical Action Items

1. **Explicitly Label All Metrics as Synthetic:**
   All portfolio reports, README summaries, and API endpoints must continue to distinguish synthetic simulation metrics from real-world telemetry (already completed via `status="SIMULATED"` in API contracts).
2. **Implement an Optimized Rule Baseline Benchmark:**
   Add a second baseline (`OptimizedRuleBaseline`) mapping `BANK_TIMEOUT` and `LIMIT_EXCEEDED` to `RETRY_LATER`. This provides an honest, rigorous measurement of the pure ML contribution (e.g. contextual customer history and amount conditioning) over expert domain rules.
3. **Incorporate Correlated Bank Downtime:**
   Upgrade `simulator/generator.py` with a 2-state Markov chain (Normal vs Outage) per bank, producing realistic bursty failure spikes to challenge the Go executor's circuit breakers.
4. **Model Retry Fatigue Decay:**
   Add attempt-dependent probability dampening in `simulator/recovery.py`:
   $$\text{Probability}(k) = \max\left(0, \text{Probability}_0 - 0.15 \times (k - 1)\right)$$
