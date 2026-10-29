# Engineering Audit: Data Infrastructure & Reliability Systems (Rippling Target)

**Auditor:** Senior Infrastructure & Distributed Systems Reviewer  
**Target Role:** Software Engineer I — Data Infrastructure (Rippling)  
**Target Codebases:** `payment-recovery-engine`, `flarehouse`, `db-lifecycle`  
**Date:** October 29, 2026  

---

## 1. Executive Summary

This audit assesses the state of data infrastructure, distributed event processing, telemetry ingestion, and database lifecycle management across our repositories. Our goal is to identify and resolve critical correctness defects, eliminate silent data loss failure modes, fix CI quality-gate bypasses, and construct a production-grade database lifecycle migration system matching Rippling's Data Infrastructure engineering standards.

---

## 2. Verified Architectural Defects & Findings

### Finding 1: False Idempotency & Premature Offset Commitment in Event Processing
* **Location:** `payment-recovery-engine/backend/go-executor/events/recovery_flow.go`, `postgres_event_store.go`, `kafka_consumer.go`
* **Severity:** **CRITICAL (Data Loss / Incomplete State Silently Masked)**
* **Evidence:**
  1. `PostgresEventStore.Claim(eventID)` executes an `INSERT INTO event_idempotency (event_id) VALUES ($1) ON CONFLICT DO NOTHING`.
  2. If the insertion succeeds, it returns `true, nil`.
  3. If downstream processing in `RecoveryFlow.Process(event)` fails (e.g., `processor.Process()` decision error or `executionWorker.Execute()` timeout), an error is returned and Kafka redelivers the event.
  4. On redelivery, `f.eventStore.Claim(event.EventID)` queries the existing row, returning `false, nil`.
  5. In `recovery_flow.go` (line 38):
     ```go
     if !claimed {
         return RecoveryFlowResult{}, nil
     }
     ```
     The flow interprets `!claimed` as "already completed", returning `nil` error!
  6. In `kafka_consumer.go` (line 46-52):
     ```go
     if err := c.handler.Handle(event); err != nil {
         return fmt.Errorf("handle payment failed event: %w", err)
     }
     if err := c.reader.CommitMessages(ctx, message); err != nil {
         return fmt.Errorf("commit kafka message: %w", err)
     }
     ```
     Because `Handle()` returns `nil`, the consumer commits the Kafka offset!
  7. **Impact:** Incomplete recovery flows are never retried. Failed transactions are permanently lost while being falsely reported as successful.
* **Proposed Fix:**
  - Transition from a binary "claimed" presence check to an explicit **Lease & State Lifecycle**:
    `PROCESSING` (with worker lease & expiration timestamp), `COMPLETED` (durably finalized), and `FAILED` (with retry counts and dead-letter boundaries).
  - Add `ClaimOrRenew`, `MarkCompleted`, and `MarkFailed`.
  - Expired leases must be automatically reclaimable by other active workers.
  - An event in `PROCESSING` status must return an explicit `ErrEventInProgress` (or `ErrLeaseActive`) so that Kafka DOES NOT commit the offset prematurely.
  - Kafka offset is committed ONLY when processing is durably marked `COMPLETED` or when maximum retries are exhausted and routed to DLQ.
* **Required Tests:**
  - `TestDuplicateEvents_SuppressionWhenCompleted`
  - `TestConcurrentWorkers_SingleLeaseWinner`
  - `TestWorkerFailureAfterClaim_ReclaimAfterLeaseExpiration`
  - `TestRetryAfterRecoverableFailure`
  - `TestKafkaOffsetCommit_OnlyOnCompletionOrDLQ`
  - `TestExhaustedRetries_DeadLetterQuarantine`

---

### Finding 2: Silent Batch Loss on Downstream Storage Failures & Unsafe Shutdown
* **Location:** `flarehouse/internal/ingest/batcher.go`, `cmd/gateway/main.go`
* **Severity:** **HIGH (Silent Ingestion Data Loss)**
* **Evidence:**
  1. In `flarehouse/internal/ingest/batcher.go` (lines 127-133):
     ```go
     batchCopy := make([]model.TelemetryEvent, len(buffer))
     copy(batchCopy, buffer)
     buffer = buffer[:0] // reset slice header

     if err := e.chClient.InsertBatch(e.ctx, batchCopy); err != nil {
         fmt.Printf("[Worker %d] ClickHouse batch insert failed: %v\n", workerID, err)
     }
     ```
     The slice buffer is cleared *before* the write is confirmed. If ClickHouse experiences a transient network blip or connection timeout, the error is printed to stdout and `batchCopy` is garbage collected.
  2. In `IngestionEngine.Stop()` (lines 240-244):
     ```go
     func (e *IngestionEngine) Stop() {
         e.cancel()
         close(e.eventChan)
         e.wg.Wait()
     }
     ```
     `e.cancel()` cancels `e.ctx` immediately. Workers waiting on `select { case <-e.ctx.Done(): flush() }` call `InsertBatch(e.ctx, batchCopy)` with an already-canceled context! The final flush immediately fails, discarding all in-flight events.
* **Proposed Fix:**
  - Introduce testable `BatchWriter` interface.
  - Implement bounded retry loop with exponential backoff and randomized jitter for transient ClickHouse errors.
  - Retain the batch if retries fail; divert to an in-memory/durable dead-letter spool if retries are permanently exhausted, and update Prometheus failure metrics (`BatchFlushFailuresTotal`, `EventsDroppedTotal`).
  - Decouple engine shutdown from the write context: `Stop()` drains the channel, flushes buffered events using a bounded shutdown timeout context (`time.Second * 5`), and halts safely without dropping data.
* **Required Tests:**
  - `TestBatchFlush_Success`
  - `TestBatchFlush_TransientFailure_ExponentialBackoffRetry`
  - `TestBatchFlush_PersistentFailure_BoundedRetryAndDLQ`
  - `TestGracefulShutdown_FlushesBufferedEvents`
  - `TestCancellationDuringRetry`
  - `TestConcurrentIngestionAndShutdown`

---

### Finding 3: CI Quality Gate Concealment (`|| true` Antipattern)
* **Location:** `payment-recovery-engine/.github/workflows/ci.yml`
* **Severity:** **MEDIUM (False-Positive CI Passing Checks)**
* **Evidence:**
  - Line 97: `timeout 60s bash -c 'until docker compose ps | grep -q "healthy.*healthy"; do sleep 2; done' || true`
  - Line 107: `python -m pytest -m "integration" || true`
  - If infrastructure fails to boot or Python integration tests fail with catastrophic errors, the `|| true` mask suppresses the exit code, returning 0 to GitHub Actions.
* **Proposed Fix:**
  - Remove all `|| true` masks.
  - Replace ambiguous greps with deterministic readiness checks (`pg_isready -h localhost -p 5432 -U recovery`, `redis-cli ping`, etc.).
  - Fail the CI run immediately if required test suites fail.

---

### Finding 4: Absence of Automated Database Lifecycle & Schema Migration System
* **Location:** Entire workspace
* **Severity:** **HIGH (Architectural Gap for Data Infrastructure Role)**
* **Evidence:**
  - Rippling’s Data Infrastructure team manages 500+ production database resources across 10+ datastore types.
  - Currently, schema migrations in our repositories rely on ad-hoc scripts or raw SQL executions without concurrency safety, rollback tracking, advisory locking, or expand-and-contract zero-downtime workflows.
* **Proposed Implementation (`db-lifecycle`):**
  - Construct a standalone, robust **PostgreSQL Schema Migration Manager in Go**.
  - Features:
    - CLI commands: `status`, `plan`, `up`, `validate`, `version`.
    - PostgreSQL session-level advisory locks (`pg_advisory_lock(int64)`) with configurable acquisition timeout to prevent concurrent migration race conditions.
    - Deterministic ordering with versioned SQL migrations (`001_initial_schema.up.sql`).
    - Cryptographic SHA-256 checksums to detect file tampering after application.
    - Transactional DDL execution with automatic rollback on error.
    - Support for non-transactional statements (`CREATE INDEX CONCURRENTLY`) via `-- +migrate no-transaction`.
    - Full expand-and-contract zero-downtime migration example and automated test harness.

---

## 3. Implementation Schedule

1. **Phase 2A:** Implement durable lease/state event store & recovery flow in `payment-recovery-engine`. Add unit and concurrency tests.
2. **Phase 2B:** Implement bounded retry, backoff, and graceful flush in `flarehouse/internal/ingest/batcher.go`. Add comprehensive tests.
3. **Phase 2C:** Remediate `.github/workflows/ci.yml` in `payment-recovery-engine`.
4. **Phase 3:** Build `db-lifecycle` Go project with full CLI, locking, transactions, checksums, and tests.
5. **Phase 4 & 5:** Execute benchmarks and verify security invariants.
6. **Phase 6 & 7:** Update documentation and compile final 1-page LaTeX resume.
