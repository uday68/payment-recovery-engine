import pytest
from backend.go_executor_client import GoExecutorClient
import uuid

pytestmark = pytest.mark.integration


def test_go_executor_client_executes_command():
    client = GoExecutorClient(
        base_url="http://localhost:8080"
    )

    command = {
        "command_id": f"python-go-{uuid.uuid4()}",
        "payment_id": f"payment-python-go-{uuid.uuid4()}",
        "action": "RETRY_LATER",
        "amount": 5000,
    }

    result = client.execute(command)

    assert result["command_id"] == command["command_id"]
    assert result["payment_id"] == command["payment_id"]
    assert result["status"] in ("EXECUTED", "FAILED")
    assert result["action"] == "RETRY_LATER"