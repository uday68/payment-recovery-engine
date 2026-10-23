from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient

from backend.elasticsearch_client import build_elasticsearch_query, ElasticsearchAuditStore
from backend.audit_repository import AuditRepository
from backend.api.app import app

client = TestClient(app)


def test_build_elasticsearch_query_defaults():
    q = build_elasticsearch_query()
    assert q["from"] == 0
    assert q["size"] == 50
    assert "query" in q
    assert "bool" in q["query"]
    assert q["query"]["bool"]["must"] == [{"match_all": {}}]
    assert "aggs" in q
    assert "by_action" in q["aggs"]
    assert "by_outcome" in q["aggs"]


def test_build_elasticsearch_query_with_filters():
    q = build_elasticsearch_query(
        q="timeout",
        failure_code="BANK_TIMEOUT",
        action="RETRY_NOW",
        from_date="2026-09-01T00:00:00Z",
        to_date="2026-09-02T00:00:00Z",
        limit=25,
        offset=10,
    )
    assert q["from"] == 10
    assert q["size"] == 25

    # Check text query
    must = q["query"]["bool"]["must"]
    assert len(must) == 1
    assert "multi_match" in must[0]
    assert must[0]["multi_match"]["query"] == "timeout"

    # Check filters
    filters = q["query"]["bool"]["filter"]
    assert any("term" in f and f["term"].get("failure_code.keyword") == "BANK_TIMEOUT" for f in filters)
    assert any("bool" in f and "should" in f["bool"] for f in filters)
    assert any("range" in f and "timestamp" in f["range"] for f in filters)


def test_audit_repository_fallback_in_memory():
    # Force memory mode to verify in-memory fallback behavior
    repo = AuditRepository(database_url="memory://")
    repo.db_available = False
    if repo.es_store:
        repo.es_store.is_healthy = lambda: False
        repo.es_store.search = lambda **kwargs: None

    # Clear in-memory state
    repo._in_memory_audit.clear()

    # Seed 3 distinct decisions
    repo.save({
        "payment_id": "pay_test_001",
        "customer_id": "cust_1",
        "amount": 2500.0,
        "failure_code": "BANK_TIMEOUT",
        "probabilities": {"RETRY_NOW": 0.8},
        "recommended_action": "RETRY_NOW",
        "expected_value": 150.0,
        "policy_allowed": True,
        "policy_reason": "PASS",
        "executed_action": "RETRY_NOW",
        "outcome": "RECOVERED",
        "recovered": True,
        "timestamp": "2026-09-01T10:00:00Z",
    })
    repo.save({
        "payment_id": "pay_test_002",
        "customer_id": "cust_2",
        "amount": 5000.0,
        "failure_code": "LIMIT_EXCEEDED",
        "probabilities": {"SEND_REMINDER": 0.6},
        "recommended_action": "SEND_REMINDER",
        "expected_value": 75.0,
        "policy_allowed": True,
        "policy_reason": "PASS",
        "executed_action": "SEND_REMINDER",
        "outcome": "FAILED",
        "recovered": False,
        "timestamp": "2026-09-01T11:00:00Z",
    })
    repo.save({
        "payment_id": "pay_test_003",
        "customer_id": "cust_3",
        "amount": 1000.0,
        "failure_code": "BANK_TIMEOUT",
        "probabilities": {"RETRY_LATER": 0.3},
        "recommended_action": "RETRY_LATER",
        "expected_value": -10.0,
        "policy_allowed": False,
        "policy_reason": "LOW_EV",
        "executed_action": "NO_ACTION",
        "outcome": "NO_ACTION",
        "recovered": False,
        "timestamp": "2026-09-01T12:00:00Z",
    })

    # 1. Search all
    res = repo.search_decisions()
    assert res["total"] == 3
    assert res["source"] in ("in_memory", "postgres")
    assert res["aggregations"]["by_action"]["RETRY_NOW"] == 1
    assert res["aggregations"]["by_action"]["SEND_REMINDER"] == 1
    assert res["aggregations"]["by_action"]["NO_ACTION"] == 1

    # 2. Filter by failure code
    res_fc = repo.search_decisions(failure_code="BANK_TIMEOUT")
    assert res_fc["total"] == 2
    assert all(r["failure_code"] == "BANK_TIMEOUT" for r in res_fc["results"])

    # 3. Filter by action
    res_act = repo.search_decisions(action="RETRY_NOW")
    assert res_act["total"] == 1
    assert res_act["results"][0]["payment_id"] == "pay_test_001"

    # 4. Search query q
    res_q = repo.search_decisions(q="pay_test_002")
    assert res_q["total"] == 1
    assert res_q["results"][0]["customer_id"] == "cust_2"


def test_api_audit_search_endpoint():
    response = client.get("/audit/search?limit=10")
    assert response.status_code == 200
    data = response.json()
    assert "total" in data
    assert "results" in data
    assert "aggregations" in data
    assert "by_action" in data["aggregations"]
    assert "by_outcome" in data["aggregations"]
    assert data["source"] in ("elasticsearch", "postgres", "in_memory")
