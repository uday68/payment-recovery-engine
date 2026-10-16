import pytest
import psycopg

from backend.recovery_pipeline import RecoveryPipeline

pytestmark = pytest.mark.integration


DATABASE_URL = (
    "postgresql://recovery:recovery@localhost:5432/recovery_engine"
)


def test_real_python_to_go_end_to_end():
    import uuid
    payment_id = f"real-e2e-{uuid.uuid4()}"

    pipeline = RecoveryPipeline(
        database_url=DATABASE_URL,
        go_executor_url="http://localhost:8080",
    )

    result = pipeline.process_payment(
        payment_id=payment_id,
        customer_id="customer-e2e-001",
        amount=5000,
        failure_code="BANK_TIMEOUT",
        success_rate=0.8,
        recovery_rate=0.6,
        payment_method="UPI",
        bank="HDFC",
    )

    assert result["payment_id"] == payment_id
    assert result["duplicate"] is False

    execution = result["execution_result"]

    assert execution["outcome"] in (
        "EXECUTED",
        "FAILED_RETRYABLE",
        "FAILED_PERMANENT",
        "EXECUTOR_ERROR",
    )

    assert "attempts" in execution

    with psycopg.connect(DATABASE_URL) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    outcome,
                    attempts,
                    recovered,
                    retryable
                FROM recovery_audit
                WHERE payment_id = %s
                """,
                (payment_id,),
            )

            row = cursor.fetchone()

    assert row is not None

    outcome, attempts, recovered, retryable = row

    assert outcome == execution["outcome"]
    assert attempts == execution["attempts"]
    assert recovered == execution["recovered"]
    assert retryable == execution["retryable"]

def test_real_go_executor_rejects_duplicate_command():
    import requests
    import uuid

    command = {
        "command_id": f"real-idempotency-{uuid.uuid4()}",
        "payment_id": f"real-idempotency-payment-{uuid.uuid4()}",
        "action": "RETRY_NOW",
        "amount": 5000,
    }

    first = requests.post(
        "http://localhost:8080/v1/recovery/execute",
        json=command,
        timeout=5,
    )

    second = requests.post(
        "http://localhost:8080/v1/recovery/execute",
        json=command,
        timeout=5,
    )

    assert first.status_code == 200
    assert second.status_code == 200

    first_result = first.json()
    second_result = second.json()

    assert first_result["status"] in ("SUCCESS", "FAILED", "EXECUTED")
    assert second_result["status"] == "DUPLICATE"