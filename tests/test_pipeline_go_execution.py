import pytest
from backend.recovery_pipeline import RecoveryPipeline
import uuid

pytestmark = pytest.mark.integration


def test_pipeline_executes_recovery_through_go():
    pipeline = RecoveryPipeline(
        database_url="postgresql://recovery:recovery@localhost:5432/recovery_engine",
        go_executor_url="http://localhost:8080",
    )

    payment_id = f"pipeline-go-{uuid.uuid4()}"

    result = pipeline.process_payment(
        payment_id=payment_id,
        customer_id="customer-go-001",
        amount=5000,
        success_rate=0.9,
        recovery_rate=0.5,
        payment_method="UPI",
        bank="HDFC",
        failure_code="BANK_TIMEOUT",
    )

    assert result["duplicate"] is False
    assert result["execution_result"]["payment_id"] == payment_id
    assert result["execution_result"]["status"] in ("EXECUTED", "FAILED")