<div align="center">

# ⚡ Razorpay AI Revenue Recovery Engine

### *Turn payment failures into recovered revenue — intelligently, reliably, and verifiably.*

<br/>

[![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Go](https://img.shields.io/badge/Go-1.22-00ADD8?style=for-the-badge&logo=go&logoColor=white)](https://go.dev)
[![React](https://img.shields.io/badge/React-18-61DAFB?style=for-the-badge&logo=react&logoColor=black)](https://react.dev)
[![Kafka](https://img.shields.io/badge/Apache_Kafka-231F20?style=for-the-badge&logo=apache-kafka&logoColor=white)](https://kafka.apache.org)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)](https://postgresql.org)
[![Redis](https://img.shields.io/badge/Redis-7-DC382D?style=for-the-badge&logo=redis&logoColor=white)](https://redis.io)

<br/>

> **Razorpay AI Buildathon — Track 03: AI Revenue Recovery**

</div>

---

## The Core Insight

Payment failures are not simply failed transactions — they are **revenue at risk**.

A naive system retries everything. That wastes recovery budget on payments that will never succeed and misses high-value opportunities that needed a different intervention.

This system asks a more precise question for every failure:

> **Which recovery action has the highest expected economic value — and is it safe to execute?**

The answer emerges from a layered pipeline:

```
AI Prediction  →  Economic Optimization  →  Thompson Sampling  →  Policy Gate  →  Reliable Execution
```

The AI never controls execution directly. The policy layer always has the final word.

---

## Mathematical Decision Model

The recovery engine combines **supervised probability estimation** with
**expected-value optimization**.

The key idea is:

> Predict the probability of recovery for every possible action, then choose the
> action that maximizes expected recovered value after accounting for
> intervention cost.

### 1. Problem Formulation

For a failed payment, let:

- $X$ = payment/customer context
- $A$ = candidate recovery action
- $Y \in \{0,1\}$ = recovery outcome
- $Y = 1$ = recovery succeeded
- $Y = 0$ = recovery failed

The system models:

$$
P(Y=1 \mid X,A)
$$

This is the probability that action $A$ successfully recovers a payment with
context $X$.

### 2. Context $X$

The context contains information such as:

$$
X = (\mathrm{success\_rate},\ \mathrm{recovery\_rate},\ \mathrm{amount},\
\mathrm{payment\_method},\ \mathrm{bank},\ \mathrm{failure\_code},\ \mathrm{hour})
$$

The action is included as an input feature because the same payment can have
different recovery probabilities depending on the intervention.

For example, the model evaluates each candidate action separately:

```text
Payment Context
     + RETRY_NOW
     -> P(recovery | context, RETRY_NOW)

Payment Context
     + RETRY_LATER
     -> P(recovery | context, RETRY_LATER)

Payment Context
     + SEND_REMINDER
     -> P(recovery | context, SEND_REMINDER)
```

### 3. Expected-Value Optimization

For each candidate recovery action, the engine estimates the net economic recovery value, explicitly accounting for intervention costs and merchant recovery margins:

$$
EV(a) = \begin{cases} 
0.0 & \text{if } a = \text{NO\_ACTION} \\ 
P(Y=1 \mid X, a) \cdot (\text{Margin} \times \text{Amount}) - \text{Cost}(a) & \text{otherwise} 
\end{cases}
$$

Where intervention costs reflect actual payment gateway and customer messaging tariffs:
* `RETRY_NOW`: ₹2.00
* `RETRY_LATER`: ₹2.00
* `SEND_REMINDER`: ₹1.00
* `NO_ACTION`: ₹0.00

If all active actions yield negative expected value (e.g. high retry cost on micro-transactions with low recovery probabilities, or zero merchant margin), the system mathematically selects:

$$
a^* = \arg\max_{a \in A} EV(a) = \text{NO\_ACTION}
$$

The selected action is then passed to Contextual Thompson Sampling and the deterministic policy gate. The policy gate has final authority and can replace the model's recommendation with `NO_ACTION` whenever confidence or margin conditions are violated.

---

## Verified Results

### 1. Leak-Free ML Benchmark (5-Fold GroupKFold Cross-Validation)

Evaluated via `python run_ml_audit.py` on `ml/data.csv` (61,520 samples across 3,076 unique payments). Partitioned strictly by `payment_id` ($TrainGroups \cap ValGroups = \emptyset$) to eliminate counterfactual leakage across trials:

| Model Architecture | ROC-AUC | PR-AUC | Brier Score Loss | Log Loss | ECE | Status |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Dummy (Prior Classifier)** | $0.5000 \pm 0.0000$ | $0.3310 \pm 0.0048$ | $0.2214 \pm 0.0016$ | $0.6349 \pm 0.0033$ | $0.0045 \pm 0.0039$ | Baseline |
| **Logistic Regression (L2)** | $0.7697 \pm 0.0029$ | $0.5654 \pm 0.0067$ | $0.1749 \pm 0.0007$ | $0.4937 \pm 0.0015$ | $0.0080 \pm 0.0023$ | Linear Baseline |
| **Random Forest (Raw)** | **$0.7897 \pm 0.0029$** | **$0.6036 \pm 0.0071$** | **$0.1699 \pm 0.0011$** | **$0.4836 \pm 0.0025$** | **$0.0124 \pm 0.0021$** | **Production Preferred** |
| **Random Forest (Calibrated - Sigmoid)** | $0.7913 \pm 0.0033$ | $0.6062 \pm 0.0074$ | $0.1826 \pm 0.0012$ | $0.5416 \pm 0.0036$ | $0.0975 \pm 0.0029$ | Degraded Calibration |
| **Random Forest (Calibrated - Isotonic)** | $0.7884 \pm 0.0028$ | $0.6028 \pm 0.0073$ | $0.1706 \pm 0.0011$ | $0.4901 \pm 0.0026$ | $0.0163 \pm 0.0024$ | Sub-fold Overfitting |

> **Key Calibration Finding:** Platt/Sigmoid scaling artificially pushes predictions toward the class prior ($0.33$), severely degrading probability quality (Brier score +7.5%, ECE ~8x increase). **Raw Random Forest is chosen as the production model** because it produces genuine, well-calibrated ensemble probabilities with the lowest proper scoring rule losses.

### 2. Controlled Experiment & Net Economics (10,000 Payments, Seed 42)

Counterfactual outcomes generated using Common Random Numbers (CRN) variance reduction (`random.Random(f"{payment_id}:{action}")`):

| Strategy | Recovered | Rate | Gross Revenue | Intervention Cost | Net Recovered Revenue | Net Revenue / Failure |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| 🔴 **Naive Always-Retry** | 1,173 | 39.39% | ₹6.03M | ₹5,956 | ₹6,025,252 | ₹2,023.25 |
| 🟡 **Rule-Based Heuristic** | 1,529 | 51.34% | ₹7.74M | ₹4,297 | ₹7,739,508 | ₹2,598.89 |
| 🟢 **AI EV Engine** | **1,616** | **54.26%** | **₹8.26M** | **₹4,013** | **₹8,251,900** | **₹2,770.95** |

* **AI Net Lift vs Rule-Based:** **+6.62% (+₹512,392 net revenue)** while spending **6.6% less** on intervention fees.
* **AI Action Distribution:** `SEND_REMINDER` (45.8%), `RETRY_LATER` (40.1%), `NO_ACTION` (11.7%), `RETRY_NOW` (2.4%). Avoids 57% of unnecessary gateway load compared to naive retry.
* Across 5 independent seeds: mean lift **+6.85% ± 1.05 pp**, positive on all 5 runs.

> *Note:* These are **local simulator / controlled experiment results under CRN assumptions** — not real-world live traffic claims.

---

## Architecture

### Decision Pipeline

```
┌──────────────────────────────────────────────────────────────────┐
│                         PAYMENT FAILURE                          │
└─────────────────────────────┬────────────────────────────────────┘
                              │
                              ▼
          ┌───────────────────────────────────┐
          │           Apache Kafka            │
          │     topic: recovery.payment.failed│
          └─────────────────┬─────────────────┘
                            │ at-least-once delivery
                            ▼
          ┌───────────────────────────────────┐
          │         Recovery Worker           │
          │  ✓ Event idempotency check        │
          │  ✓ Distributed rate limit (Redis) │
          └─────────────────┬─────────────────┘
                            │
                            ▼
          ┌───────────────────────────────────┐
          │      Python AI Decision Engine    │
          │                                   │
          │  Random Forest                    │
          │    → P(success | context, action) │
          │                                   │
          │  Expected Value                   │
          │    → EV(a) = P × Amount − Cost(a) │
          │    → argmax EV(a)                 │
          │                                   │
          │  Thompson Sampling                │
          │    → Beta(α,β) per action         │
          │    → exploration–exploitation     │
          │                                   │
          │  Policy Gate  ← deterministic     │
          │    → P < 0.50 → NO_ACTION         │
          └─────────────────┬─────────────────┘
                            │  Recovery Command
                            ▼
          ┌───────────────────────────────────┐
          │         Go Recovery Executor      │
          │  ✓ Command idempotency            │
          │  ✓ Bounded retries                │
          │  ✓ Circuit breaker (per gateway)  │
          │  ✓ Gateway execution              │
          └──────┬────────────────────────────┘
                 │
        ┌────────┴────────┐
        ▼                 ▼
    SUCCESS           FAILURE
        │                 │
        ▼                 ▼
  PostgreSQL         Kafka DLQ
  Audit + Merkle     recovery.payment
  Bandit reward      .failed.dlq
  update
```

---

### Failure & DLQ Path

```
Primary Topic
      │
      ▼
  Recovery Worker
      │
      ├─► [success]  ──► commit offset
      │
      └─► [failure]
              │
              ▼
         bounded retry
              │
              ▼
         DLQ Publisher ──► recovery.payment.failed.dlq
              │
              ▼
         commit original offset
              ↑
         (never commit before DLQ ACK)
```

---

### Audit Integrity — RFC 6962 Merkle Tree

```
           ┌─── Root Hash ───┐
           │                 │
        H(01)             H(23)
       /      \          /      \
    H(0)     H(1)     H(2)     H(3)
      │        │        │        │
   Audit0   Audit1   Audit2   Audit3

Leaf hash:  SHA256(0x00 ‖ data)
Node hash:  SHA256(0x01 ‖ H_left ‖ H_right)
```

Individual inclusion proofs are generated and independently verifiable.

---

## Feature Status

| Capability | Status | Notes |
|---|:---:|---|
| Random Forest decision model | ✅ Implemented | `ml/model.pkl`, 59K training rows |
| Expected Value optimization | ✅ Implemented | `EV(a) = P × amount − cost` |
| Thompson Sampling (Beta-Bernoulli) | ✅ Implemented | Context-segmented Beta posteriors per failure code |
| Leak-free ML Cross-Validation | ✅ GroupKFold | Grouped by payment_id (Train ∩ Test = ∅) |
| Python Offline Test Suite | ✅ 103 passing | 0 failures, 100% offline isolated (126s) |
| Go Microservices Test Suite | ✅ 100% passing | recovery-executor, worker, events |
| SHAP model explanations | ✅ Implemented | `shap.TreeExplainer` on real RF model |
| Deterministic policy gate | ✅ Implemented | `P < 0.50` → NO_ACTION |
| Kafka event processing | ✅ Implemented | `recovery.payment.failed` topic |
| Kafka Dead Letter Queue | ✅ Implemented | `recovery.payment.failed.dlq`, acks=all |
| Event idempotency | ✅ Implemented | PostgreSQL `processed_events` |
| Command idempotency | ✅ Implemented | PostgreSQL `executed_commands` |
| Distributed rate limiting | ✅ Implemented | Redis atomic Lua token bucket |
| Go execution service | ✅ Implemented | Bounded retry + circuit breaker |
| RFC 6962 Merkle audit proofs | ✅ Implemented | SHA-256, 0x00/0x01 prefix, verifiable |
| PostgreSQL audit layer | ✅ Implemented | `recovery_audit` table, WAL-logged |
| React Control Tower | ✅ Implemented | 8 live-data pages |
| Controlled 3-way experiment | ✅ Implemented | Deterministic, seed-reproducible |
| Real gateway integration | 🔬 Simulated | Local deterministic simulator |
| Production deployment | 🔮 Future | Requires production infrastructure |

---

## Documentation

### Primary Portfolio & Architecture Reports

- **[Portfolio Applied ML & Systems Architecture Report](docs/PORTFOLIO_APPLIED_ML_SYSTEMS_REPORT.md)** — Comprehensive technical evaluation report detailing leakage elimination, 5-fold GroupKFold benchmarking, the calibration discrepancy resolution, contextual bandit regret tracking, net economic modeling, and distributed systems hardening.
- **[Backend System and Model Performance Report](docs/BACKEND_SYSTEM_AND_MODEL_PERFORMANCE_REPORT.md)** — Historical metrics lineage reconciliation, Go microservice latency benchmarks, and resilience verification.

### Architecture and Product

- [Autonomous Payment Recovery Control Tower](Razorpay%20Autonomous%20Payment%20Recovery%20Control%20Tower.md) — product overview, system architecture, workflows, and operating model.
- [V2 Architecture Roadmap](docs/V2_ARCHITECTURE_ROADMAP.md) — event-driven platform evolution and future architecture phases.
- [Implemented Features](docs/IMPLEMENTED_FEATURES.md) — verified feature inventory with implementation and provenance references.
- [Benchmarks](docs/BENCHMARKS.md) — recovery strategy comparisons, performance metrics, and multi-seed stability results.

### Dashboards and Integration

- [Dashboard Guide](docs/DASHBOARD_GUIDE.md) — purpose, APIs, data sources, and runtime requirements for all eight control-tower dashboards.
- [Frontend/Backend Compatibility Report](docs/FRONTEND_BACKEND_COMPATIBILITY_REPORT.md) — frontend data contracts, endpoint mappings, and integration gaps.
- [Full-Stack Integration Report](docs/FULL_STACK_INTEGRATION_PHASES_COMPLETE.md) — completed frontend, backend, database, and service integration phases.
- [Zero Static Content and Full-Stack Integration Report](docs/ZERO_STATIC_CONTENT_AND_FULL_STACK_INTEGRATION_REPORT.md) — telemetry provenance and live-data verification.

### Reliability and Event Processing

- [Event Idempotency](docs/V2_5_EVENT_IDEMPOTENCY.md) — at-least-once Kafka delivery, duplicate prevention, and idempotent processing.
- [Backend System and Model Performance Report](docs/BACKEND_SYSTEM_AND_MODEL_PERFORMANCE_REPORT.md) — backend services, model behavior, latency, and performance evidence.

### Engineering History

- [V1 Go Execution Day Report](docs/2026-09-02-v1-go-execution-day-report.md) — Go execution service, reliability controls, and the V1 boundary.
- [September 3 Session Report](docs/2026-09-03-session-report.md) — executor evolution, audit boundary migration, experimentation, and model retraining.
- [September 4 Session Report](docs/2026-09-04-session-report.md) — Kafka streaming, distributed idempotency, worker services, and frontend integration.

---

## Technical Deep Dives

<details>
<summary><strong>📐 Expected Value Decision Model</strong></summary>

For each candidate recovery action, the model estimates `P(Y=1 | X, a)` — the probability of successful recovery given payment context X and action a.

This is converted to economic value:

```
EV(a) = P(success | X, a) × Amount − Cost(a)
a*    = argmax EV(a)
```

**Example — pay_123, ₹5,000, BANK_TIMEOUT:**

| Action | P(success) | Cost | EV |
|---|---:|---:|---:|
| RETRY_NOW | 0.42 | ₹2 | ₹2,098 |
| **RETRY_LATER** | **0.71** | **₹2** | **₹3,548** ✓ |
| SEND_REMINDER | 0.38 | ₹1 | ₹1,899 |
| NO_ACTION | 0.03 | ₹0 | ₹0 |

The policy gate then authorizes or blocks the selected action before any execution occurs.

</details>

<details>
<summary><strong>🎲 Thompson Sampling (Beta-Bernoulli)</strong></summary>

Thompson Sampling addresses exploration vs. exploitation across recovery action strategies. Each action maintains a Beta conjugate posterior:

```
θ_a ~ Beta(α_a, β_a)      (prior: α = β = 1)

Successful recovery → α ← α + 1
Failed recovery     → β ← β + 1
```

Posteriors are persisted in PostgreSQL `bandit_posterior` so state survives restarts.

**Safety invariant:** Thompson Sampling informs selection but **always passes through the Policy Gate** before execution.

</details>

<details>
<summary><strong>🔍 SHAP Explainability</strong></summary>

For any prediction, the system decomposes the model output into per-feature contributions:

```
f(x) = φ₀ + Σᵢ φᵢ
```

**Example — RETRY_LATER selected (P = 0.73):**

```
Base value:          0.44

Positive factors:
  success_rate    +0.09
  amount          +0.07
  hour            +0.03

Negative factors:
  failure_code    −0.05
  recovery_rate   −0.02

Final output:        0.73
```

SHAP values are per-prediction explanations — distinct from Random Forest MDI feature importance, which is a global model property.

</details>

<details>
<summary><strong>🔐 RFC 6962 Merkle Audit Proofs</strong></summary>

Audit records are organized into a Merkle tree following the RFC 6962 Certificate Transparency specification:

```
Leaf hash:  SHA256(0x00 ‖ leaf_data)
Node hash:  SHA256(0x01 ‖ H_left ‖ H_right)
```

For any audit record the system generates an inclusion proof: `Leaf → siblings → Root`.

The proof can be independently verified without trusting the issuer. This provides cryptographic integrity detection — not immutable storage, which requires separate infrastructure.

</details>

<details>
<summary><strong>⚡ Distributed Rate Limiting (Redis)</strong></summary>

Without distributed rate limiting each worker tracks its own counter — the global limit can be exceeded.

With Redis atomic Lua scripting all workers share one quota with zero race conditions:

```
Worker A ─┐
Worker B ─┤── Redis Atomic Token Bucket ──► shared quota
Worker C ─┘
```

**Failure policy: FAIL-CLOSED.** If Redis is unreachable, requests are rejected rather than silently bypassing the limit.

</details>

---

## Data Provenance

All dashboards and metrics explicitly label their source:

| Label | Meaning |
|---|---|
| `LIVE` | Fetched from a running service at request time |
| `SIMULATED BENCHMARK` | Controlled experiment on synthetic data |
| `EVALUATION DATASET` | Offline model evaluation on `ml/data.csv` |
| `UNAVAILABLE` | Dependency unreachable — never fabricated |

---

## Tech Stack

```
┌──────────────────────────────────────────────────────────┐
│                     Control Tower                        │
│          React 18  •  TypeScript  •  Vite  •  Tailwind   │
└─────────────────────────┬────────────────────────────────┘
                          │ REST API
┌─────────────────────────▼────────────────────────────────┐
│                  Python AI Engine                        │
│        FastAPI  •  scikit-learn  •  SHAP  •  Redis       │
└──────┬───────────────────────────────────┬───────────────┘
       │ Recovery Command                  │ Audit / State
┌──────▼──────────┐             ┌──────────▼───────────────┐
│  Go Executor    │             │       PostgreSQL          │
│  Retry + CB     │             │  Audit • Idempotency      │
│  Kafka DLQ      │             │  Bandit Posteriors        │
└──────┬──────────┘             └──────────────────────────┘
       │
┌──────▼──────────┐   ┌────────────────────────────────────┐
│  Apache Kafka   │   │             Redis                  │
│  Event Bus      │   │  Distributed Rate Limiter          │
└─────────────────┘   └────────────────────────────────────┘
```

---

## Quick Start

### Prerequisites

- Python 3.10 or newer
- Docker Desktop or Docker Engine with Docker Compose
- Go 1.22 or newer
- Node.js 18 or newer and npm

The Compose services use Linux images (`postgres:16`, `redis:7-alpine`, and
`apache/kafka:4.0.0`). On Windows or macOS, Docker Desktop must be using
**Linux containers**. The setup script can start Docker Desktop when it is
installed, but Docker itself must be installed first.

### Automated Setup

Run these commands from any directory after cloning. The script resolves paths
relative to itself, so the repository does not need to be installed in a
specific location:

```powershell
python path\to\razorpay-recovery-engine\setup_and_run.py
```

The runner checks Python and Docker, installs missing Python packages from
`requirements.txt`, validates the Compose file, checks the configured images,
pulls missing images, starts PostgreSQL, Redis, and Kafka, generates the
dataset, trains the model, runs tests, and executes the inference smoke test.

Useful modes:

```powershell
# Start only Docker infrastructure
python setup_and_run.py --docker

# Stop Docker infrastructure
python setup_and_run.py --stop-docker

# Generate data and train the model
python setup_and_run.py --train

# Run dependency checks and tests
python setup_and_run.py --test

# Start Docker, FastAPI, Go, React, the live injector, and proof stream
python setup_and_run.py --launch
```

`--launch` keeps the terminal attached and stops all application processes
together when you press `Ctrl+C`. FastAPI runs on `http://localhost:8000`, the
Go executor on `http://localhost:8080`, and Vite normally uses
`http://localhost:5173`.

If Docker is not installed, the normal setup continues with local Python
steps. If Docker is installed but its engine is stopped, the runner attempts
to start it; use `--docker` to require infrastructure startup and report any
failure. Python itself must be installed before running the script.

### Manual Setup

#### 1 — Infrastructure

```bash
docker compose up -d
# starts PostgreSQL · Kafka · Redis
```

#### 2 — Python Environment

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

#### 3 — Services

```bash
# Python AI Decision API
uvicorn backend.api.app:app --host 0.0.0.0 --port 8000

# Go Executor + Recovery Worker
cd backend/go-executor
go run .

# React Control Tower
cd frontend && npm install && npm run dev
```

---

## Testing & ML Auditing

```bash
# 1. Python unit tests (103 passing, zero network dependencies, 100% offline)
python -m pytest -m "not integration"

# 2. Reproducible ML Benchmark Audit (5-Fold GroupKFold cross-validation)
python run_ml_audit.py

# 3. Go test suite — unit + integration + backpressure + circuit breaker (100% passing)
cd backend/go-executor && go test ./... && cd ../..

# 4. Contextual bandit simulation & regret verification
python -m pytest tests/test_contextual_bandit.py -v

# 5. Controlled experiment net economics verification
python -m pytest tests/test_controlled_experiment.py -v

# 6. Read the complete audit report:
# See docs/PORTFOLIO_APPLIED_ML_SYSTEMS_REPORT.md
```

---

## Repository Structure

```
razorpay-recovery-engine/
├── backend/
│   ├── api/
│   │   ├── app.py                      # FastAPI endpoints
│   │   └── schemas.py                  # Pydantic models
│   ├── bandit.py                       # Thompson Sampling
│   ├── bandit_repository.py            # PostgreSQL posteriors
│   ├── ml_explainer.py                 # SHAP TreeExplainer
│   ├── crypto_merkle.py                # RFC 6962 Merkle tree
│   ├── rate_limiter.py                 # Redis Lua token bucket
│   ├── decision/engine.py              # EV decision engine
│   ├── policy/engine.py                # Deterministic policy gate
│   ├── audit_repository.py             # PostgreSQL audit layer
│   ├── recovery_pipeline.py            # End-to-end pipeline
│   └── go-executor/
│       ├── main.go                     # Go service entrypoint
│       ├── retry.go                    # Bounded retry logic
│       ├── circuit_breaker.go          # Per-gateway circuit breaker
│       ├── distributed_rate_limiter.go # Redis Lua token bucket (Go)
│       └── events/
│           ├── kafka_dlq_publisher.go  # DLQ producer (acks=all)
│           └── kafka_dlq_consumer.go   # DLQ consumer
├── ml/
│   ├── train.py                        # Model training script
│   ├── model.pkl                       # Trained RF pipeline
│   └── data.csv                        # 59K synthetic training rows
├── frontend/
│   └── src/
│       ├── pages/                      # 8 dashboard pages
│       ├── components/                 # Charts · UI · system cards
│       └── api/index.ts                # Typed API clients
├── tests/                              # Python pytest suite
├── docs/
├── docker-compose.yml
└── README.md
```

---

## Design Principles

**AI does not equal authority** — The model recommends. The policy gate authorizes.

**Probability does not equal value** — A 90% chance of recovering ₹100 is not always better than a 40% chance of recovering ₹1,000. Expected Value decides.

**Failure is expected** — Duplicate events, network timeouts, and gateway errors are normal distributed-system conditions. The system is designed around them.

**Every decision must be traceable** — Input → Prediction → EV → Policy → Execution → Outcome → Audit → Proof.

**Never fake telemetry** — When real data is unavailable, say `UNAVAILABLE`. When data is simulated, say `SIMULATED`.

---

## Limitations

This is a hackathon system. Important scope boundaries:

- Payment gateway behavior is **locally simulated** — not real bank integrations
- Controlled experiment results use **synthetic data** — not production traffic
- Benchmark numbers are **environment-specific**
- Production deployment requires authentication, authorization, TLS, secret management, compliance controls, and observability infrastructure

These limitations are documented intentionally, not hidden.

---

<div align="center">

**The strongest claim of this project is not that it contains the most components.**

**It is that the components it claims to have are implemented, testable, traceable, and tied to measurable revenue recovery.**

---

*Built for Razorpay AI Buildathon · Track 03: AI Revenue Recovery*

</div>
