# Phase 1: Test Baseline & Reproducibility Report

**Repository:** `uday68/razorpay-recovery-engine`  
**Execution Timestamp:** 2026-10-16T19:35:00+05:30  
**Host Environment:** Windows 11, Python 3.12.6, Go 1.22, pytest 9.1.1  
**Docker Daemon Status:** Inactive (`open //./pipe/dockerDesktopLinuxEngine: system cannot find file specified`)

---

## 1. Test Execution Baseline Matrix

All commands were executed in the local repository environment. No results or counts have been fabricated.

| Test Group | Exact Command | Execution Result | Tests Passed | Tests Failed | Blocker / Empirical Evidence |
| :--- | :--- | :--- | :---: | :---: | :--- |
| **Static Checks (Python)** | `python -m compileall -q backend ml simulator tests` | **PASS** | — | — | Exit code 0. Zero syntax or bytecode compilation errors across all modules. |
| **Static Checks (Go)** | `cd backend/go-executor && go vet ./... && go test -run=^$ ./...` | **PASS** | — | — | Exit code 0. Zero compiler errors, zero `go vet` issues across `recovery-executor`, `cmd/recovery-worker`, and `events`. |
| **Python Unit Tests** | `python -m pytest -m "not integration"` | **PASS** | **103** | **0** | 103 passed, 23 deselected in 126.68s. Completely decoupled from external databases and networks. |
| **Go Test Suite** | `cd backend/go-executor && go test -count=1 ./...` | **PASS** | **112** | **0** | All 112 tests passed across 3 packages (`recovery-executor`: 84, `worker`: 1, `events`: 27) in 15.12s. |
| **Integration Tests** | `python -m pytest -m "integration" -v` | **FAIL (BLOCKED)** | **13** | **10** | 10 failed, 13 passed, 103 deselected. Failures caused by offline dependencies: PostgreSQL (:5432), Redis (:6379), Go server (:8080). |
| **End-to-End Tests** | `python -m pytest tests/test_real_e2e.py -v` | **FAIL (BLOCKED)** | **0** | **2** | 2 failed. Both tests require active Go HTTP server on `http://localhost:8080` and live PostgreSQL. |

---

## 2. Detailed Diagnostic Evidence for Failed Integration Tests

When running integration tests without Docker services active, the following exact errors were captured:

### A. Python-to-Go HTTP Linkage
* **Test:** `tests/test_go_executor_client.py::test_go_executor_client_executes_command`
* **Test:** `tests/test_pipeline_go_execution.py::test_pipeline_executes_recovery_through_go`
* **Test:** `tests/test_real_e2e.py::test_real_python_to_go_end_to_end`
* **Test:** `tests/test_real_e2e.py::test_real_go_executor_rejects_duplicate_command`
* **Failure Message:** `requests.exceptions.HTTPError: 404 Client Error: Not Found for url: http://localhost:8080/v1/recovery/execute`
* **Root Cause:** No process was listening on port 8080.

### B. Redis Distributed Rate Limiter
* **Test:** `tests/test_rate_limiter.py::test_rate_limiter_allowed_within_quota`
* **Failure Message:** `AssertionError: assert 'UNAVAILABLE' == 'LIVE'`
* **Test:** `tests/test_rate_limiter.py::test_rate_limiter_multithreaded_concurrency`
* **Failure Message:** `AssertionError: assert 0 == 20 (where 0 = len(allowed_results))`
* **Root Cause:** Redis is not running on `localhost:6379`. The rate limiter successfully and correctly triggered its fail-closed fallback (`status: "UNAVAILABLE"`), but the integration assertions strictly expected a live Redis connection.

### C. PostgreSQL Live Endpoints
* **Test:** `backend/api/test_full_endpoints.py::test_get_recovery_transactions`
* **Test:** `backend/api/test_full_endpoints.py::test_get_audit_detail`
* **Test:** `backend/api/test_full_endpoints.py::test_get_audit_ledger`
* **Test:** `backend/api/test_full_endpoints.py::test_get_merkle_proof`
* **Failure Message:** `Database query note: connection timeout expired. Multiple connection attempts failed: localhost:5432`
* **Root Cause:** PostgreSQL container is not running on `localhost:5432`.

---

## 3. Environment & Prerequisites for Full Integration Testing

To run the full suite including integration and end-to-end tests:

1. **Start Infrastructure Services:**
   ```bash
   docker compose up -d postgres redis kafka
   ```
2. **Launch Go Recovery Executor:**
   ```bash
   cd backend/go-executor
   go run .
   ```
3. **Execute Full Test Suite (Unit + Integration):**
   ```bash
   python -m pytest -v
   ```
