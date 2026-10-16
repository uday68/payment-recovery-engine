from simulator.models import Customer, Payment
from simulator.recovery import recovery_probablity, execute_recovery

import responses
from datetime import datetime

from ml.model_store import load_model

from backend.audit import create_audit_event
from backend.audit_repository import AuditRepository
from backend.decision.engine import choose_action
from backend.experiment import build_context, predict_actions
from backend.policy.engine import apply_policy
from backend.recovery_command import create_recovery_command
from backend.recovery_executor import RecoveryExecutor
from backend.go_executor_client import GoExecutorClient


from backend.bandit import ThompsonSamplingBandit


ACTIONS = [
    "RETRY_NOW",
    "RETRY_LATER",
    "SEND_REMINDER",
    "NO_ACTION",
]


class RecoveryPipeline:

    def __init__(
        self,
        database_url="postgresql://recovery:recovery@localhost:5432/recovery_engine",
        go_executor_url=None,
    ):
        self.model = load_model()
        self.audit_repository = AuditRepository(database_url)
        self.bandit = ThompsonSamplingBandit(database_url=database_url)
        self.executor = RecoveryExecutor()
        self.go_executor_url = go_executor_url
        self.go_executor = (
            GoExecutorClient(go_executor_url)
            if go_executor_url else None
        )

    def process_payment(
        self,
        payment_id,
        customer_id,
        amount,
        failure_code,
        success_rate,
        recovery_rate,
        payment_method,
        bank,
        hour=0,
    ):
        claimed = self.audit_repository.claim_payment(
            payment_id
                )

        if not claimed:
            event = self.audit_repository.get_by_payment_id(payment_id)
            return {
                "payment_id": payment_id,
                "duplicate": True,
                "executed_action": event["executed_action"] if event else None,
            }
        customer = Customer(
            id=customer_id,
            successful_payments=round(
                success_rate * 100
            ),
            failed_payments=100,
            recovered_payments=round(
                recovery_rate * 100
            ),
        )

        payment = Payment(
            id=payment_id,
            customer_id=customer_id,
            amount=amount,
            payment_method=payment_method,
            bank=bank,
            failure_code=failure_code,
            timestamp=None,
            status="FAILED",
        )

        context = {
            "success_rate": success_rate,
            "recovery_rate": recovery_rate,
            "amount": amount,
            "payment_method": payment_method,
            "bank": bank,
            "failure_code": failure_code,
            "hour": hour,
        }

        probabilities = predict_actions(
            self.model,
            context,
        )

        decision = choose_action(
            amount,
            probabilities,
        )

        # Thompson Sampling Bandit exploration bounded over eligible actions
        bandit_result = self.bandit.sample_arm(
            eligible_actions=list(probabilities.keys()),
            amount=amount,
            model_probabilities=probabilities,
            context=context,
        )
        recommended_action = bandit_result["selected_action"]

        selected_probability = probabilities[
            recommended_action
        ]

        policy = apply_policy(
            action=recommended_action,
            amount=amount,
            probability=selected_probability,
            expected_value=decision["expected_value"],
        )

        executed_action = policy["action"]

        command = create_recovery_command(
            payment_id,
            executed_action,
            amount,
        )

        if self.go_executor is not None:
            execution_result = self.go_executor.execute(command)
        else:
            execution_result = self.executor.execute(
                command=command,
                customer_success_rate=success_rate,
                customer_recovery_rate=recovery_rate,
                failure_code=failure_code,
            )

        if "retryable" not in execution_result:
            execution_result["retryable"] = False
        if "outcome" not in execution_result:
            execution_result["outcome"] = "EXECUTED" if execution_result.get("recovered") else "FAILED_PERMANENT"
        if "attempts" not in execution_result:
            execution_result["attempts"] = 1

        # Update bandit posterior on actual recovery outcome
        if executed_action != "NO_ACTION":
            self.bandit.update(
                action=executed_action,
                success=bool(execution_result.get("recovered", False)),
                context=context,
            )

        audit_event = create_audit_event(
            payment_id=payment_id,
            customer_id=customer_id,
            amount=amount,
            failure_code=failure_code,
            probabilities=probabilities,
            recommended_action=recommended_action,
            expected_value=decision["expected_value"],
            policy_allowed=policy["allowed"],
            policy_reason=policy["reason"],
            executed_action=executed_action,
            execution_result=execution_result,
            bank=bank,
            payment_method=payment_method,
        )

        self.audit_repository.save(
            audit_event
        )

        return {
            "payment_id": payment_id,
            "duplicate": False,
            "recommended_action": recommended_action,
            "probabilities": probabilities,
            "expected_value": decision["expected_value"],
            "policy_allowed": policy["allowed"],
            "policy_reason": policy["reason"],
            "executed_action": executed_action,
            "execution_probability": execution_result.get("execution_probability"),
            "recovered": execution_result.get(
                "recovered",
                execution_result.get("status") == "EXECUTED",
            ),
            "recovery_command": command,
            "execution_result": execution_result,
            "bandit_exploration": {
                "selected_action": bandit_result["selected_action"],
                "sampled_probabilities": bandit_result["sampled_probabilities"],
                "sampled_expected_values": bandit_result["sampled_expected_values"],
            },
        }
   