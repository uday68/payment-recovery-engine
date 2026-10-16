# Phase 1: Repository Discovery and Engineering Audit

**Repository:** `uday68/razorpay-recovery-engine`  
**Date:** October 2026  
**Reviewer:** Senior Backend / Infrastructure Engineer  
**Status:** Audit & Baseline Phase (Phase A & B)

---

## 1. Repository Architecture Overview

The **Razorpay Autonomous Payment Recovery Engine** is a polyglot, event-driven recovery platform composed of:
1. **Python FastAPI Decision Service (`backend/api/app.py`):** Serves real-time inference, economic expected-value (EV) decisioning, contextual bandit exploration, and RFC 6962 Merkle tree audit proofs.
2. **Go High-Throughput Execution Service (`backend/go-executor/`):** Implements bounded retry loops, exponential backoff with jitter, per-gateway circuit breakers (`HDFC`, `ICICI`, `SBI`, `Axis`), and Kafka backpressure stream consumption.
3. **Apache Kafka Event Bus:** Carries payment failure events on topic `recovery.payment.failed` and routes unrecoverable poison pills to `recovery.payment.failed.dlq`.
4. **PostgreSQL 16 Database:** Stores append-only audit records (`recovery_audit`), atomic payment idempotency claims (`recovery_idempotency`), command claims (`command_idempotency`), and Bayesian bandit posteriors (`bandit_posterior`).
5. **Redis 7 Distributed Rate Limiter:** Enforces global token-bucket rate limits across concurrent worker threads and processes via atomic Lua scripts.
6. **Machine Learning Pipeline (`ml/`):** ColumnTransformer pipeline with a 100-tree `RandomForestClassifier` evaluating recovery probabilities across four actions (`RETRY_NOW`, `RETRY_LATER`, `SEND_REMINDER`, `NO_ACTION`).
7. **Control Tower Frontend (`frontend/`):** React 18, Vite, TypeScript, and Tailwind CSS telemetry dashboard.

```
                              [ Kafka Topic: recovery.payment.failed ]
                                                 │
                                                 ▼
                                     [ Go Recovery Worker ]
                           (Backpressure Consumer & Circuit Breaker)
                                                 │
                               HTTP POST /v1/recovery/execute (or direct API)
                                                 ▼
                                    [ Python Decision Engine ]
                     ┌────────────────────────────────────────────────────────┐
                     │ 1. Feature Preprocessing (StandardScaler + OneHot)     │
                     │ 2. Probability Estimation (RandomForestClassifier)     │
                     │ 3. EV Engine: EV(a) = P(a) * (Margin * Amount) - C(a) │
                     │ 4. Contextual Thompson Sampling (Beta Posteriors)      │
                     │ 5. Deterministic Policy Gate (Guardrails)              │
                     └───────────────────────────┬────────────────────────────┘
                                                 │
                                 ┌───────────────┴───────────────┐
                                 ▼                               ▼
                     [ PostgreSQL Database ]           [ Redis Rate Limiter ]
                   (Audit Ledger & Idempotency)          (Atomic Lua Script)
```

---

## 2. Service Responsibilities

| Service / Module | Tech Stack | Primary Responsibilities |
| :--- | :--- | :--- |
| **Python Decision API** (`backend/api/app.py`) | Python 3.12, FastAPI, Pydantic | Ingests payment failure contexts, executes ML model inference, selects optimal actions via expected value and Thompson sampling, enforces policy guardrails, serves telemetry endpoints. |
| **Go Recovery Executor** (`backend/go-executor/main.go`) | Go 1.22, HTTP net/http | HTTP daemon exposing `/v1/recovery/execute`, `/metrics`, and `/v1/system/circuit-breakers`. Enforces command idempotency, invokes payment gateways, manages circuit states. |
| **Go Kafka Consumer Worker** (`backend/go-executor/events/`) | Go 1.22, segmentio/kafka-go | Backpressure-aware Kafka consumer that halts consumption when the internal `ExecutionQueue` fills, retries transient failures, and routes dead letters to DLQ with `acks=all`. |
| **Recovery Pipeline** (`backend/recovery_pipeline.py`) | Python | Orchestrates the end-to-end payment processing workflow: claim payment $\rightarrow$ model prediction $\rightarrow$ EV action selection $\rightarrow$ Thompson Sampling $\rightarrow$ policy gate $\rightarrow$ executor $\rightarrow$ audit persist. |
| **Audit Repository** (`backend/audit_repository.py`) | Python, psycopg 3 | Manages database transactions for idempotency claims and audit event recording, with non-blocking in-memory fallback when PostgreSQL is unreachable. |
| **Distributed Rate Limiter** (`backend/rate_limiter.py`) | Python, redis-py | Shared rate limiter executing an atomic Lua token bucket script with fail-closed safety guards. |

---

## 3. Main Request & Event-Processing Flows

### Flow 1: Synchronous API Decision (`POST /v1/recovery/decide`)
1. Client POSTs `RecoveryDecisionRequest` containing payment context (`amount`, `payment_method`, `bank`, `failure_code`, `success_rate`, `recovery_rate`, `timestamp`).
2. `predict_actions(model, context)` scores probabilities for all 4 candidate actions.
3. `choose_action(amount, probabilities)` computes Expected Value for each action.
4. `apply_policy(...)` validates candidate action against deterministic safety rules (e.g. $P \ge 0.50$ for retries).
5. Returns `RecoveryDecisionResponse` with authorized action, probability, and EV.

### Flow 2: End-to-End Payment Processing (`RecoveryPipeline.process_payment`)
1. **Idempotency Claim:** Atomically claims `payment_id` in PostgreSQL table `recovery_idempotency` (`ON CONFLICT (payment_id) DO NOTHING`).
   - If already claimed: returns `duplicate: True` with previous execution outcome.
2. **Context & Scoring:** Generates context and predicts probabilities using `model.predict_proba`.
3. **Economic EV Selection:** Evaluates net EV: $EV(a) = P(a) \cdot (\text{Margin} \times \text{Amount}) - \text{Cost}(a)$.
4. **Contextual Thompson Sampling:** Samples Beta posterior for the specific failure code context.
5. **Policy Gate:** Enforces safety constraints (e.g., card expired, confidence floor, EV floor).
6. **Execution Dispatch:** Dispatches command to `GoExecutorClient` (`http://localhost:8080/v1/recovery/execute`) or local `RecoveryExecutor`.
7. **Posterior & Audit Update:** Updates bandit posterior on recovery outcome and persists immutable audit event in `recovery_audit`.

### Flow 3: Asynchronous Kafka Event Processing
1. Payment failure event published to Kafka topic `recovery.payment.failed`.
2. `BackpressureConsumer` checks `ExecutionQueue` depth: pauses partition fetch if queue is saturated.
3. Worker dequeues message, parses envelope, and calls `DecisionClient`.
4. Command dispatched through `CircuitBreakerExecutor`:
   - If gateway circuit is `OPEN`: fast-fails with `ErrCircuitOpen`.
   - If transient error: retries up to 3 times with exponential backoff + jitter.
   - If max retries exhausted: `KafkaDLQPublisher` publishes message to `recovery.payment.failed.dlq` with `acks=all`. Original message offset is committed only after successful DLQ publish.

---

## 4. External Dependencies

| Dependency | Purpose | Connection / Host | Fallback / Isolation Behavior |
| :--- | :--- | :--- | :--- |
| **PostgreSQL 16** | Audit ledger & idempotency store | `localhost:5432/recovery_engine` | 1-second connect timeout; falls back to in-memory dictionary & sets. |
| **Redis 7** | Distributed rate limiting token bucket | `localhost:6379/0` | Fail-closed policy (rejects execution if Redis unavailable to prevent gateway overload). |
| **Apache Kafka 4.0.0** | Asynchronous payment event streaming & DLQ | `localhost:9092` | Used for asynchronous stream processing; unit tests use `InMemoryDLQPublisher` and mock queues. |
| **Go Executor HTTP** | Microsecond gateway execution daemon | `http://localhost:8080` | Python client expects HTTP endpoint; falls back to local Python `RecoveryExecutor` if unconfigured. |

---

## 5. Test Suite Organization

* **Python Unit & Model Tests (`tests/`, `backend/api/`, `backend/decision/`):**
  - **Total Collected:** 126 tests across 47 test files.
  - **Offline Unit Tests (marker `not integration`):** 103 tests. Zero network/database dependencies. Fast execution (~126 seconds).
  - **Integration Tests (marker `integration`):** 23 tests requiring live Docker services (PostgreSQL on 5432, Redis on 6379, Go on 8080).
* **Go Test Suite (`backend/go-executor/`):**
  - **Total Tests:** 112 tests across 3 packages (`recovery-executor`: 84 tests + 2 benchmarks, `cmd/recovery-worker`: 1 test, `events`: 27 tests).
  - **Execution Time:** ~15 seconds uncached (`go test -count=1 ./...`). 100% PASS.

---

## 6. Current Setup and Execution Instructions

### Local Prerequisites
* Python 3.12+ with virtual environment.
* Go 1.22+.
* Docker Engine / Docker Compose (for PostgreSQL, Redis, Kafka).

### Verified Execution Commands
```powershell
# 1. Python Unit Test Suite (Offline, zero network dependencies)
python -m pytest -m "not integration"

# 2. Go Test Suite (Unit, concurrency, backpressure, circuit breaker)
cd backend/go-executor
go test ./...
cd ../..

# 3. Model Benchmark & Evaluation Audit
python run_ml_audit.py
```

---

## 7. Confirmed Issues & Defect Analysis

### Defect 1: Policy-Blocked Actions Return Contradictory Expected Value (P1 Correctness)
* **Location:** `backend/api/app.py:313`
* **Evidence:** In `decide_recovery`:
  ```python
  policy = apply_policy(
      action=recommended_action,
      amount=request.amount,
      probability=selected_probability,
      expected_value=decision["expected_value"],
  )
  final_action = policy["action"]
  final_prob = probabilities.get(final_action, selected_probability)
  final_ev = decision["expected_value"]
  ```
* **Impact:** When the policy gate overrides an action to `NO_ACTION` (due to low probability or EV floor violation), `final_ev` still outputs the expected value of the *blocked* action (e.g. ₹3,500). By definition, $EV(\text{NO\_ACTION}) \equiv 0.0$. Upstream consumers receive a response asserting `action: "NO_ACTION"` with a positive expected recovery value.

### Defect 2: Unhandled Go Executor Network Failures Create "Ghost Duplicate" Payments (P0 Correctness)
* **Location:** `backend/recovery_pipeline.py:141`
* **Evidence:**
  ```python
  claimed = self.audit_repository.claim_payment(payment_id)
  if not claimed:
      ...
  ...
  if self.go_executor is not None:
      execution_result = self.go_executor.execute(command)
  ```
  `go_executor.execute(command)` invokes `requests.post()` with `response.raise_for_status()`.
* **Impact:** If the Go executor service experiences a network timeout, connection reset, or 500 error, `process_payment()` raises an unhandled exception. However, `claim_payment(payment_id)` was *already committed* to `recovery_idempotency`. No record is saved in `recovery_audit`. Subsequent attempts to retry or re-process this payment return `{"duplicate": True, "executed_action": None}`. The payment is permanently locked out without ever having been executed or recorded.

### Defect 3: Hardcoded Database Connection String in Go Server (P1 Maintainability / Reliability)
* **Location:** `backend/go-executor/main.go:288`
* **Evidence:**
  ```go
  databaseURL := "postgres://recovery:recovery@localhost:5432/recovery_engine?sslmode=disable"
  ```
* **Impact:** The Go server does not inspect `os.Getenv("DATABASE_URL")`. In containerized environments or environments where PostgreSQL runs on a different host, port, or with custom credentials, the server cannot connect unless recompiled.

### Defect 4: Excessive Socket Timeouts During Integration Tests When Services Offline (P2 Developer Experience)
* **Location:** `backend/api/test_full_endpoints.py`
* **Evidence:** Running `pytest -m "integration"` without PostgreSQL running takes ~55 minutes because 10 tests repeatedly attempt socket connections to localhost:5432 using OS-level 21s TCP timeouts.
* **Impact:** Drastically slows down test cycles when developers run integration test commands without pre-checking service availability.

---

## 8. Potential Risks Requiring Additional Investigation

1. **At-Least-Once Kafka Delivery vs. Outbox Pattern:**
   In `backend/go-executor/events/recovery_flow_handler.go`, events are processed and idempotency is checked in PostgreSQL. However, message offset commit occurs after processing without a distributed 2-phase commit or formal transactional outbox. A crash between database write and Kafka commit could cause redelivery. (Mitigated by PostgreSQL `ON CONFLICT DO NOTHING`, but should be monitored).
2. **Redis Fail-Closed Behavior Under Transient Network Blips:**
   `RedisDistributedRateLimiter` strictly defaults to `fail_closed=True`. During brief network partitions to Redis, 100% of recovery dispatches are blocked. While financially safe, high-volume recovery could be delayed.

---

## 9. Existing Capabilities That Already Work & Must Be Preserved

1. **Leak-Free ML Model Pipeline (`ml/`):** Strict `GroupKFold` partitioning on `payment_id` yielding verified ROC-AUC $0.7897 \pm 0.0029$, PR-AUC $0.6036$, Brier score $0.1699$, and ECE $0.0124$.
2. **RFC 6962 Merkle Tree Audit Ledger (`backend/crypto_merkle.py`):** Cryptographically strict Certificate Transparency hashing ($0x00$ leaf prefix, $0x01$ node prefix) with verifiable inclusion proofs.
3. **Go Circuit Breakers (`backend/go-executor/circuit_breaker.go`):** State transitions (`CLOSED` $\rightarrow$ `OPEN` $\rightarrow$ `HALF-OPEN`) protecting payment gateways.
4. **Kafka Backpressure-Aware Streaming (`backend/go-executor/events/`):** Dynamic pause/resume on saturated consumer queues and DLQ publishing with `acks=all`.
5. **Contextual Thompson Sampling (`backend/bandit.py`):** Context-segmented Beta-Bernoulli posteriors per failure category with deterministic policy overrides.
