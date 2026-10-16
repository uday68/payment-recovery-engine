# Razorpay Autonomous Payment Recovery Control Tower
## System Architecture & Verified Production Feature Status

This document provides a comprehensive, verified inventory of all features, services, and components currently implemented across the **Razorpay Recovery Engine** repository.

---

## 1. Verified Architecture & Reality Matrix

| Feature / Capability | Status | Actual Implementation Reality | Data Source / Provenance |
| :--- | :--- | :--- | :--- |
| **Beta-Bernoulli Thompson Sampling** | **IMPLEMENTED (PRODUCTION)** | Failure-code context-segmented action exploration over Expected Value. Conjugate Beta posteriors $(\alpha, \beta)$ tracked per error context. Inviolable policy gate guardrails ($P < 0.50 \rightarrow \text{NO\_ACTION}$). | `backend/bandit.py`, `backend/bandit_repository.py`, `tests/test_contextual_bandit.py` |
| **SHAP Model Explanations** | **IMPLEMENTED (PRODUCTION)** | Real `TreeExplainer` computed on Random Forest pipeline (`ml/model.pkl`). Calculates exact Shapley feature attributions, base values, and direction (`POSITIVE`/`NEGATIVE`) with strict efficiency identity ($E[f(x)] + \sum \phi_j = f(x)$). | `backend/ml_explainer.py`, `tests/test_shap_explainer.py`, `GET /v1/ai/explain/{payment_id}` |
| **RFC 6962 Merkle Audit Proofs** | **IMPLEMENTED (PRODUCTION)** | Cryptographically strict $0x00$ leaf prefix, $0x01$ node prefix, power-of-2 split decomposition ($k = 2^{\lfloor \log_2(n - 1) \rfloor}$). Generates inclusion proofs over PostgreSQL-ordered audit sequence and standalone verification. | `backend/crypto_merkle.py`, `tests/test_rfc6962_merkle.py`, `GET /v1/audit/rfc6962-proof/{id}`, `POST /v1/audit/verify-proof` |
| **Distributed Global Rate Limiting** | **IMPLEMENTED (PRODUCTION)** | Redis-backed atomic token bucket/sliding window Lua script shared across concurrent Go workers and Python API workers. Fail-closed financial safety semantics when Redis is unreachable. | `backend/go-executor/distributed_rate_limiter.go`, `backend/rate_limiter.py`, `tests/test_rate_limiter.py` |
| **Production Kafka Dead Letter Queue (DLQ)** | **IMPLEMENTED (PRODUCTION)** | Durable topic `recovery.payment.failed.dlq` on `:9092` with structured DLQ envelope, bounded retries (3 attempts), and strict at-least-once message commit ordering (no commit if DLQ write fails). | `backend/go-executor/events/kafka_dlq_publisher.go`, `kafka_dlq_consumer.go`, `kafka_dlq_integration_test.go` |
| **Recovery Decision Pipeline** | **IMPLEMENTED** | Python pipeline evaluating recovery actions, computing Expected Value (EV), and enforcing policy rules | `backend/recovery_pipeline.py`, `backend/decision/engine.py` |
| **ML Predictive Model** | **IMPLEMENTED** | `RandomForestClassifier` (100 trees) evaluated via leak-free 5-Fold `GroupKFold` on `payment_id` | `ml/model.pkl` (72.07% accuracy, 0.7897 ROC-AUC, 0.6036 PR-AUC, 0.1699 Brier) |
| **Go Recovery Executor** | **IMPLEMENTED** | High-throughput Go HTTP service on `:8080` with bounded retries, backoff, and metrics | `backend/go-executor/main.go` |
| **Execution Idempotency** | **IMPLEMENTED** | Dual-layer idempotency (atomic PostgreSQL store & in-memory map) preventing duplicate recovery | `backend/audit_repository.py`, `backend/go-executor/main.go` |
| **Gateway Circuit Breakers** | **IMPLEMENTED** | Per-gateway state machine (CLOSED, HALF_OPEN, OPEN) with trip/reset API | `backend/go-executor/circuit_breaker.go` |
| **PostgreSQL Audit Ledger** | **IMPLEMENTED** | ACID WAL storage of all decisions, executions, attempts, and SHA-256 record digests | `recovery_audit` table in PostgreSQL |
| **3-Way Strategy Evaluation** | **SIMULATED** | Offline deterministic benchmark comparing Naive Retry, Rule-Based Heuristic, and AI Engine on 10,000 synthetic payments (Seed 42) | `backend/controlled_experiment.py` (+36.89% revenue over Naive, +6.61% over Rule) |
| **Kafka Event Ingestion** | **LIVE & INSTRUMENTED** | Apache Kafka broker on `:9092` with topic `recovery.payment.failed` (3 partitions) and `recovery.payment.failed.dlq`. Robust consumer with bounded retries and DLQ routing | Apache Kafka 4.0.0 local Docker |

---

## 2. Five Advanced Features: Technical Architecture & Verification

### 1. Beta-Bernoulli Thompson Sampling
- **Posterior Math**: Action success probability $\theta_a \sim \text{Beta}(\alpha_a, \beta_a)$.
- **Exploration Score**: $\hat{\text{EV}}_a = \hat{\theta}_a \cdot \text{Amount} - \text{Cost}(a)$.
- **Policy Inviolability**: Deterministic safety rules (`apply_policy`) strictly filter and guard sampled actions.
- **Outcome Update**: Real recovery success increments $\alpha_a \leftarrow \alpha_a + 1$, failure increments $\beta_a \leftarrow \beta_a + 1$.
- **Storage**: Persisted atomically in PostgreSQL table `bandit_posterior`.

### 2. SHAP Model Explanations (TreeExplainer)
- **Engine**: Scikit-Learn `Pipeline` (`StandardScaler` + `OneHotEncoder` + `RandomForestClassifier`).
- **Algorithm**: TreeSHAP via `shap.TreeExplainer(rf_model)`.
- **Attribution Mapping**: Translates 24 encoded features back to core payment attributes (Customer Success Rate, Recovery Rate, Amount, Time of Day, Payment Method, Issuing Bank, Error Reason, Strategy).
- **Efficiency Validation**: Verified in unit tests that $E[f(x)] + \sum \phi_j = f(x)$ with precision $< 10^{-13}$.

### 3. RFC 6962-Compliant Merkle Audit Tree
- **Specification**:
  - Leaf Hash: $\text{SHA-256}(0x00 \mathbin{\Vert} \text{canonical\_json})$
  - Node Hash: $\text{SHA-256}(0x01 \mathbin{\Vert} \text{left\_hash} \mathbin{\Vert} \text{right\_hash})$
  - Split Rule: $k = 2^{\lfloor \log_2(n - 1) \rfloor}$
- **Ordering**: Strict ascending `id ASC` from PostgreSQL table `recovery_audit`.
- **Proof Generation & Verification**: Standalone cryptographic verifier checks bottom-up path against published Merkle root.

### 4. Distributed Global Rate Limiting
- **Engine**: Redis 7 on `localhost:6379`.
- **Atomicity**: Single-roundtrip Lua script executing `INCR` + conditional `EXPIRE` + `TTL`.
- **Concurrency Safety**: Multi-goroutine and multi-thread tested with zero race conditions.
- **Fail-Closed Semantics**: If Redis fails, rejects payment execution (`status: "UNAVAILABLE"`) to prevent upstream bank gateway cascading overloads.

### 5. Production Kafka Dead Letter Queue (DLQ)
- **Topic**: `recovery.payment.failed.dlq` on `localhost:9092` with `acks=all` (`RequiredAcks: kafka.RequireAll`).
- **Envelope**: Captures `dlq_id`, `original_topic`, `original_partition`, `original_offset`, `consumer_group`, `failure_category`, `failure_reason`, `attempt_count`, and `raw_payload`.
- **Commit Safety**: At-least-once processing guarantee. Consumer commits original message offset ONLY after DLQ acknowledgment. If DLQ publish fails, message remains uncommitted for redelivery.
