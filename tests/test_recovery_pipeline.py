from backend.recovery_pipeline import RecoveryPipeline


def test_pipeline_processes_payment_and_persists_audit():
    pipeline = RecoveryPipeline(
        database_url=(
            "postgresql://recovery:recovery"
            "@localhost:5432/recovery_engine"
        )
    )

    import uuid
    payment_id = f"pipeline-test-{uuid.uuid4()}"

    result = pipeline.process_payment(
        payment_id=payment_id,
        customer_id="customer-test-001",
        amount=5000.0,
        failure_code="BANK_TIMEOUT",
        success_rate=0.90,
        recovery_rate=0.60,
        payment_method="UPI",
        bank="HDFC",
        hour=14,
    )

    assert result["payment_id"] == payment_id
    assert result["recommended_action"] in {
        "RETRY_NOW",
        "RETRY_LATER",
        "SEND_REMINDER",
        "NO_ACTION",
    }

    assert "probabilities" in result
    assert "expected_value" in result
    assert "policy_allowed" in result
    assert "executed_action" in result

    count = pipeline.audit_repository.count_by_payment_id(
        payment_id
    )
    assert count == 1

    stored = pipeline.audit_repository.get_by_payment_id(
        payment_id
    )

    assert stored is not None
    assert stored["payment_id"] == payment_id
    assert stored["executed_action"] == result["executed_action"]


def test_pipeline_persists_execution_result_in_audit(monkeypatch):
    pipeline = RecoveryPipeline(
        go_executor_url="http://localhost:8080",
    )

    monkeypatch.setattr(
        pipeline.audit_repository,
        "claim_payment",
        lambda payment_id: True,
    )

    saved_events = []

    monkeypatch.setattr(
        pipeline.audit_repository,
        "save",
        lambda event: saved_events.append(event),
    )

    monkeypatch.setattr(
        pipeline.go_executor,
        "execute",
        lambda command: {
            "status": "SUCCESS",
            "action": "RETRY_LATER",
            "outcome": "EXECUTED",
            "attempts": 2,
            "recovered": True,
            "retryable": False,
        },
    )

    result = pipeline.process_payment(
        payment_id="audit-pipeline-001",
        customer_id="customer-123",
        amount=5000,
        failure_code="BANK_TIMEOUT",
        success_rate=0.8,
        recovery_rate=0.6,
        payment_method="UPI",
        bank="HDFC",
    )

    assert result["recovered"] is True

    assert len(saved_events) == 1

    event = saved_events[0]

    assert event["outcome"] == "EXECUTED"
    assert event["attempts"] == 2
    assert event["recovered"] is True
    assert event["retryable"] is False


def test_pipeline_executor_failure_records_audit_and_preserves_consistency(monkeypatch):
    """
    Regression test: When the Go executor service raises a network timeout or connection error,
    the pipeline must NOT crash unhandled. It must record outcome=EXECUTOR_ERROR, retryable=True,
    and persist the audit event so the payment is not left in an inconsistent ghost-duplicate state.
    """
    import requests

    pipeline = RecoveryPipeline(
        go_executor_url="http://localhost:8080",
    )

    monkeypatch.setattr(
        pipeline.audit_repository,
        "claim_payment",
        lambda payment_id: True,
    )

    saved_events = []
    monkeypatch.setattr(
        pipeline.audit_repository,
        "save",
        lambda event: saved_events.append(event),
    )

    def fail_execute(command):
        raise requests.exceptions.ConnectTimeout("Connection to Go executor timed out after 5s")

    monkeypatch.setattr(
        pipeline.go_executor,
        "execute",
        fail_execute,
    )

    result = pipeline.process_payment(
        payment_id="pay-fail-timeout-001",
        customer_id="cust-timeout",
        amount=5000,
        failure_code="BANK_TIMEOUT",
        success_rate=0.8,
        recovery_rate=0.6,
        payment_method="UPI",
        bank="HDFC",
    )

    assert result["recovered"] is False
    assert result["execution_result"]["outcome"] == "EXECUTOR_ERROR"
    assert result["execution_result"]["retryable"] is True
    assert "timed out" in result["execution_result"]["error"].lower()

    # Invariant: An audit record MUST be persisted even on executor failure
    assert len(saved_events) == 1
    assert saved_events[0]["payment_id"] == "pay-fail-timeout-001"
    assert saved_events[0]["outcome"] == "EXECUTOR_ERROR"