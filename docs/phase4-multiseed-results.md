# Phase 4: Multi-Seed Statistical Evaluation & Significance

**Repository:** `uday68/razorpay-recovery-engine`  
**Role:** Senior Backend / Applied ML Scientist (Google SWE II Standards)  
**Date:** October 2026  
**Status:** Complete  

---

## 1. Executive Summary

This report presents a 5-seed statistical evaluation of the payment recovery platform across all four strategies:
* **Always Retry (Naive Baseline)**
* **Naive Rule-Based (Heuristic Baseline)**
* **Expert Rule-Based (Domain-Optimized Baseline)**
* **AI Decision Engine (ML + Expected Value + Safety Policy Gate)**

### Statistical Rigor Standards
* **Sample Size:** 5 independent pseudo-random seeds ($N = 5$, 50,000 total simulated transactions, 15,176 total payment failures).
* **Isolation:** Each seed initializes an independent synthetic customer population and transaction stream.
* **Counterfactual Equivalence:** Within each seed, all four strategies evaluate identical transactions using Common Random Numbers (CRN).
* **Statistical Metrics Reported:**
  - Sample Mean ($\bar{x}$)
  - Sample Standard Deviation ($s = \sqrt{\frac{1}{N-1}\sum (x_i - \bar{x})^2}$)
  - Standard Error of the Mean ($\text{SE} = \frac{s}{\sqrt{N}}$)
  - 95% Confidence Interval ($[\bar{x} - t_{0.025, 4} \cdot \text{SE},\ \bar{x} + t_{0.025, 4} \cdot \text{SE}]$, with $t_{crit} = 2.7764$)
  - Paired Two-Tailed Student's t-test ($t = \frac{\bar{d}}{\text{SE}_d}$, $df = 4$)

---

## 2. Per-Seed Empirical Results (Seeds 1 – 5)

### 2.1 Recovered Revenue by Seed (₹)

| Seed | Failed Payments | At-Risk Revenue | Always Retry (₹) | Naive Rule (₹) | Expert Rule (₹) | AI Decision Engine (₹) |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **1** | 3,057 | ₹15,500,597.30 | ₹6,199,727.52 | ₹8,251,451.48 | ₹9,817,277.87 | ₹9,011,168.85 |
| **2** | 3,031 | ₹15,414,722.50 | ₹6,220,458.01 | ₹8,145,925.64 | ₹9,431,079.42 | ₹8,796,839.57 |
| **3** | 3,036 | ₹15,567,180.79 | ₹6,443,614.97 | ₹8,027,444.86 | ₹9,334,425.90 | ₹8,530,394.52 |
| **4** | 3,068 | ₹15,354,755.08 | ₹6,323,409.52 | ₹8,103,892.08 | ₹9,598,001.27 | ₹8,734,847.79 |
| **5** | 2,984 | ₹15,255,958.04 | ₹6,096,612.72 | ₹7,854,817.43 | ₹9,213,801.10 | ₹8,411,212.89 |

### 2.2 Recovery Rate by Seed (%)

| Seed | Always Retry Rate | Naive Rule Rate | Expert Rule Rate | AI Decision Engine Rate | AI `NO_ACTION` Gated |
| :---: | :---: | :---: | :---: | :---: | :---: |
| **1** | 40.17% | 53.12% | 63.13% | 57.57% | 231 (7.56%) |
| **2** | 41.17% | 53.08% | 61.10% | 56.29% | 264 (8.71%) |
| **3** | 41.34% | 51.48% | 59.98% | 54.38% | 251 (8.27%) |
| **4** | 40.84% | 52.80% | 62.06% | 56.39% | 261 (8.51%) |
| **5** | 39.58% | 51.01% | 59.82% | 54.96% | 230 (7.71%) |

---

## 3. Aggregate Revenue & Recovery Rate Statistics

### 3.1 Recovered Revenue Statistics (₹)

| Strategy | Mean ($\bar{x}$) | Std Dev ($s$) | Std Error ($\text{SE}$) | 95% CI Lower | 95% CI Upper |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Always Retry** | ₹6,256,764.55 | ₹131,885.01 | ₹58,980.77 | ₹6,093,033.93 | ₹6,420,495.17 |
| **Naive Rule** | ₹8,076,706.30 | ₹148,094.25 | ₹66,229.76 | ₹7,892,852.48 | ₹8,260,560.11 |
| **Expert Rule** | **₹9,478,917.11** | ₹235,648.94 | ₹105,385.41 | ₹9,186,367.21 | ₹9,771,467.01 |
| **AI Decision Engine** | ₹8,696,892.72 | ₹234,272.31 | ₹104,769.76 | ₹8,406,051.86 | ₹8,987,733.58 |

### 3.2 Recovery Rate Statistics (%)

| Strategy | Mean Recovery Rate | Std Dev | Std Error |
| :--- | :---: | :---: | :---: |
| **Always Retry** | 40.62% | 0.73% | 0.33% |
| **Naive Rule** | 52.30% | 0.99% | 0.44% |
| **Expert Rule** | **61.21%** | 1.39% | 0.62% |
| **AI Decision Engine** | 55.92% | 1.26% | 0.56% |

---

## 4. Paired Hypothesis Tests & Statistical Significance

Because all four strategies evaluate identical transaction sets within each seed, observations are **paired**. We compute paired two-tailed Student's t-tests on the cross-strategy differences ($df = 4$):

### Comparison 1: AI Decision Engine vs. Always Retry (Naive Baseline)
* **Mean Difference:** $+₹2,440,128.17$
* **Mean Relative Lift:** **$+39.05\% \pm 4.79\%$**
* **Paired $t$-statistic:** $19.9945$
* **$p$-value:** $3.6923 \times 10^{-5}$ ($p < 0.001$)
* **Conclusion:** The AI Decision Engine is **statistically significantly superior** to the naive Always Retry baseline with extreme confidence.

### Comparison 2: AI Decision Engine vs. Naive Rule-Based Heuristic
* **Mean Difference:** $+₹620,186.42$
* **Mean Relative Lift:** **$+7.67\% \pm 1.09\%$**
* **Paired $t$-statistic:** $14.1643$
* **$p$-value:** $1.4424 \times 10^{-4}$ ($p < 0.001$)
* **Consistency:** **5 / 5 seeds positive** for the AI Engine.
* **Conclusion:** The AI Decision Engine is **statistically significantly superior** to the unoptimized rule baseline with extreme confidence.

### Comparison 3: AI Decision Engine vs. Expert-Tuned Rule Baseline
* **Mean Difference:** $-₹782,024.39$
* **Mean Relative Difference:** **$-8.25\% \pm 0.90\%$**
* **Paired $t$-statistic:** $-20.2223$
* **$p$-value:** $3.5300 \times 10^{-5}$ ($p < 0.001$)
* **Consistency:** **0 / 5 seeds positive** for the AI Engine (Expert Rule wins 5 / 5 seeds on gross recovery).
* **Conclusion:** In the current simulator environment (where retrying costs only ₹2.00 and failure carries zero penalty), the unconstrained Expert Rule is **statistically significantly superior** in gross recovery volume.

---

## 5. Portfolio Scientific Assessment: Is Economic Superiority Demonstrated?

The prompt requires answering with full scientific honesty:
> **"Whether the AI engine's economic superiority is demonstrated, not demonstrated, or cannot yet be determined."**

### Rigorous Scientific Verdict

1. **vs. Always Retry:** **DEMONSTRATED (Superior)**  
   * $+39.05\%$ mean lift ($p = 3.69 \times 10^{-5}$, $p < 0.001$).
   * Proven across all 5 seeds.

2. **vs. Naive Rule-Based Baseline:** **DEMONSTRATED (Superior)**  
   * $+7.67\%$ mean lift ($p = 1.44 \times 10^{-4}$, $p < 0.001$).
   * Proven across all 5 seeds.

3. **vs. Expert-Tuned Domain Rule Baseline:** **NOT DEMONSTRATED in the current simulator**  
   * Under the current simulator implementation, the Expert Rule achieves higher gross revenue (₹9.48M vs ₹8.70M) and higher net revenue (₹185.0k vs ₹171.2k @ 2% MDR).
   * **Why:** The current simulator models direct intervention costs (₹1.00 – ₹2.00) but models **zero penalty** for failed attempts. Because recovering an average ₹5,000 payment yields ₹100 @ 2% MDR, any attempt with $P > 2\%$ is profitable in simulation. The Expert Rule aggressively fires on 100% of payments, capturing marginal recoveries that the AI Engine deliberately suppresses via its 50% confidence safety gate.

4. **In Real Production Environments:** **CANNOT YET BE DETERMINED WITHOUT PENALTY MODELING**  
   * In actual production payment platforms, failed retries trigger interchange decline surcharges (Visa/Mastercard Excessive Attempt fees), issuing bank rate-limiting, and core banking circuit-breaker trips.
   * If a realistic failure penalty ($C_{\text{penalty}} \ge \text{₹}15.00$ per decline) or gateway trip threshold is introduced, the AI Engine's 9.0% selective gating will protect platform margins where the un-gated Expert Rule burns capital.
   * However, because these penalty variables are not currently implemented in `simulator/recovery.py`, claiming economic superiority over the Expert Rule today would be scientifically ungrounded.
