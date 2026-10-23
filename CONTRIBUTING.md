# Contributing to Autonomous Payment Revenue Recovery Engine

Thank you for your interest in contributing. We hold our codebase to rigorous production-engineering standards for correctness, fault tolerance, test isolation, and documentation integrity.

---

## 1. Code of Conduct

All contributors are expected to uphold a professional, respectful, and collaborative environment free from harassment.

---

## 2. Development Workflow & Git Etiquette

### Trunk-Based Development
* The `main` branch is always kept in a deployable, passing state.
* Feature branches should branch off `main` and use descriptive names:
  * `feat/short-description`
  * `fix/short-description`
  * `perf/short-description`
  * `chore/short-description`

### Conventional Commits
All commit messages must adhere to the [Conventional Commits specification](https://www.conventionalcommits.org/):
```
<type>(<scope>): <short imperative summary>

[optional body explaining motivation and trade-offs]

[optional footer(s)]
```
Examples:
* `feat(audit-search): add Elasticsearch query builder with fallback`
* `fix(go-executor): resolve race condition in token bucket refill`
* `ci(workflow): enable Go race detector on Linux runners`

---

## 3. Engineering Quality Gates

Before opening a pull request, verify all local quality gates pass:

### Go Subsystem
```bash
cd backend/go-executor
gofmt -s -l .          # Must return 0 unformatted files
go vet ./...           # Must return 0 warnings
go test -count=1 ./... # Standalone unit suite must pass 100%
```

### Python Subsystem
```bash
python -m pytest -m "not integration"     # Must pass 100% offline
python -m pytest tests/test_audit_search.py
python -m pytest tests/test_policy_replay.py
```

### Frontend Subsystem
```bash
cd frontend
npm run build          # TypeScript strict mode and Vite bundle must succeed
```

---

## 4. Architectural Invariants

When contributing changes, respect the core architectural boundaries:
1. **Separation of Authority:** Machine learning components may recommend; deterministic policy engines and idempotent execution workers decide and execute. Never allow an ML model to move money directly.
2. **Deterministic Reproducibility:** Counterfactual simulations must use Common Random Numbers (CRN) with explicit seeds.
3. **Graceful Degradation:** Distributed external services (Kafka, PostgreSQL, Redis, Elasticsearch) must degrade gracefully with in-memory fallbacks during local testing and network partitioning.
4. **Zero Untested Code:** Every public API endpoint, policy branch, and query builder must have corresponding automated regression tests.
