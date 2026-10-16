import pytest
from fastapi.testclient import TestClient
from backend.api.app import app
from backend.audit_repository import AuditRepository
from backend.audit import create_audit_event

pytestmark = pytest.mark.integration

client = TestClient(app)
DB_URL = "postgres://recovery:recovery@localhost:5432/recovery_engine?sslmode=disable"

def _ensure_test_payment() -> str:
    pid = "pay_test_honest_001"
    try:
        repo = AuditRepository(DB_URL)
        event = create_audit_event(
            payment_id=pid,
            customer_id="cust_test_001",
            amount=5000.0,
            failure_code="BANK_TIMEOUT",
            probabilities={"RETRY_NOW": 0.82, "RETRY_LATER": 0.10, "SEND_REMINDER": 0.05, "NO_ACTION": 0.03},
            recommended_action="RETRY_NOW",
            expected_value=4100.0,
            policy_allowed=True,
            policy_reason="Safety constraints verified",
            executed_action="RETRY_NOW",
            bank="HDFC",
            payment_method="UPI",
        )
        repo.save(event)
    except Exception as e:
        print(f"Seed note: {e}")
    return pid

def test_get_recovery_transactions():
    _ensure_test_payment()
    res = client.get("/v1/recovery/transactions?limit=10")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert "payment_id" in data[0]
    assert "amount" in data[0]

def test_get_recovery_transactions_filter_gateway():
    _ensure_test_payment()
    res = client.get("/v1/recovery/transactions?gateway=HDFC")
    assert res.status_code == 200
    data = res.json()
    for item in data:
        assert item["bank"].upper() == "HDFC"

def test_get_audit_detail():
    pid = _ensure_test_payment()
    res = client.get(f"/v1/recovery/audit/{pid}")
    assert res.status_code == 200
    data = res.json()
    assert data["payment_id"] == pid
    assert "probabilities" in data
    assert "merkle_leaf_hash" in data
    assert data["status"] == "LIVE"

def test_get_overview_summary():
    res = client.get("/v1/analytics/overview-summary")
    assert res.status_code == 200
    data = res.json()
    assert "at_risk_revenue" in data
    assert "recovered_revenue" in data
    assert "recovery_rate" in data
    assert "circuit_breakers" in data
    assert len(data["circuit_breakers"]) == 4

def test_get_mab_experiments():
    res = client.get("/v1/experiments/mab")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "SIMULATED_EXPERIMENT"
    assert len(data["arms"]) == 3
    assert data["winning_arm"] == "arm-ai-engine"

def test_get_ai_model_health():
    res = client.get("/v1/ai/model-health")
    assert res.status_code == 200
    data = res.json()
    assert data["accuracy"] > 0.70
    assert data["roc_auc"] > 0.80
    assert "calibration_curve" in data
    assert len(data["calibration_curve"]) > 0

def test_get_policies():
    res = client.get("/v1/policies")
    assert res.status_code == 200
    data = res.json()
    assert len(data) >= 4
    assert data[0]["tier"] == "P0"

def test_post_policies_simulate():
    payload = {
        "recovery_target": 65.0,
        "gateway_trip_rate": 12.0,
        "ev_floor": 40.0,
        "max_hops": 3,
        "auto_recovery_enabled": True
    }
    res = client.post("/v1/policies/simulate", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert "simulated_recovery_rate" in data
    assert "simulated_recovered_revenue" in data
    assert "gateway_protection_score" in data

def test_get_audit_ledger():
    res = client.get("/v1/audit/ledger?limit=10")
    assert res.status_code == 200
    data = res.json()
    assert "merkle_root" in data
    assert len(data["entries"]) > 0
    assert data["active_wal_replicas"] == 1

def test_get_merkle_proof():
    pid = _ensure_test_payment()
    res = client.get(f"/v1/audit/proof/{pid}")
    assert res.status_code == 200
    data = res.json()
    assert data["payment_id"] == pid
    assert data["verified"] is True


def test_get_bandit_state():
    res = client.get("/v1/ai/bandit")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] in ("LIVE", "IN_MEMORY")
    assert data["algorithm"] == "Beta-Bernoulli Thompson Sampling"
    assert len(data["arms"]) >= 4
    for arm in data["arms"]:
        assert "alpha" in arm
        assert "beta" in arm
        assert "mean_reward" in arm
        assert len(arm["credible_interval_95"]) == 2


def test_get_shap_explanation():
    pid = _ensure_test_payment()
    res = client.get(f"/v1/ai/explain/{pid}")
    assert res.status_code == 200
    data = res.json()
    assert "RandomForestClassifier" in data["model_name"]
    assert "base_value" in data
    assert "output_probability" in data
    assert len(data["attributions"]) > 0
    assert data["attributions"][0]["direction"] in ("POSITIVE", "NEGATIVE")


def test_get_rfc6962_merkle_root():
    res = client.get("/v1/audit/merkle-root")
    assert res.status_code == 200
    data = res.json()
    assert data["root_hash"].startswith("0x")
    assert data["tree_size"] >= 1
    assert data["algorithm"] == "RFC 6962 SHA-256 Merkle Tree"


def test_get_rfc6962_proof_and_verify():
    pid = _ensure_test_payment()
    res = client.get(f"/v1/audit/rfc6962-proof/{pid}")
    assert res.status_code == 200
    proof_data = res.json()
    assert proof_data["verified"] is True
    assert proof_data["leaf_hash"].startswith("0x")
    assert proof_data["root_hash"].startswith("0x")

    # Now verify via standalone verification endpoint
    verify_req = {
        "leaf_hash": proof_data["leaf_hash"],
        "leaf_index": proof_data["leaf_index"],
        "tree_size": proof_data["tree_size"],
        "audit_path": proof_data["audit_path"],
        "expected_root": proof_data["root_hash"],
    }
    verify_res = client.post("/v1/audit/verify-proof", json=verify_req)
    assert verify_res.status_code == 200
    vdata = verify_res.json()
    assert vdata["valid"] is True


def test_get_rate_limiter_status():
    res = client.get("/v1/system/rate-limiter")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] in ("LIVE", "UNAVAILABLE")
    assert "remaining_tokens" in data
    assert "limit" in data


def test_get_dlq_stats():
    res = client.get("/v1/system/dlq")
    assert res.status_code == 200
    data = res.json()
    assert data["topic"] == "recovery.payment.failed.dlq"
    assert "total_dead_letters" in data
