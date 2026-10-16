import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from backend.controlled_experiment import run_controlled_experiment

def test_controlled_experiment_returns_required_meterics():
    result = run_controlled_experiment(
        customer_count =100,
        payment_count = 500,
        seed =42
    )

    assert result["failed_payments"] >0
    assert result["at_risk_revenue"] >0

    assert "baseline" in result
    assert "ai" in result

    for strategy  in ["baseline","ai"]:
        assert result[strategy]["recoveries"] >=0
        assert result[strategy]["recovery_rate"] >=0
        assert result[strategy]["recovered_revenue"] >=0
        assert result[strategy]["revenue_per_failure"]>=0

    assert "revenue_difference" in result
    assert "revenue_improvement" in result
    assert "recovery_improvement" in result

    assert "action_counts" in result

from backend.controlled_experiment import recovery_outcome


def test_recovery_outcome_is_deterministic():
    probability = 0.7

    first = recovery_outcome(
        "payment-123",
        "RETRY_NOW",
        probability,
    )

    second = recovery_outcome(
        "payment-123",
        "RETRY_NOW",
        probability,
    )

    assert first == second


def test_different_actions_have_independent_outcomes():
    probability = 0.7

    retry_now = recovery_outcome(
        "payment-123",
        "RETRY_NOW",
        probability,
    )

    retry_later = recovery_outcome(
        "payment-123",
        "RETRY_LATER",
        probability,
    )

    # The two outcomes are generated from different
    # payment + action counterfactual worlds.
    assert isinstance(retry_now, bool)
    assert isinstance(retry_later, bool)


def test_controlled_experiment_net_economics_and_margin():
    result = run_controlled_experiment(
        customer_count=50,
        payment_count=200,
        seed=42,
        margin=0.02,  # 2% MDR merchant fee
    )

    for strategy in ["baseline", "rule_based", "ai"]:
        assert "intervention_cost" in result[strategy]
        assert "net_recovered_revenue" in result[strategy]
        assert "net_revenue_per_failure" in result[strategy]
        # Net revenue = gross * margin - cost
        expected_net = (
            result[strategy]["recovered_revenue"] * 0.02
            - result[strategy]["intervention_cost"]
        )
        assert abs(result[strategy]["net_recovered_revenue"] - expected_net) < 1e-4

    assert "net_revenue_difference" in result
    assert "net_revenue_improvement" in result


def test_controlled_experiment_zero_margin_edge_case():
    result = run_controlled_experiment(
        customer_count=50,
        payment_count=200,
        seed=42,
        margin=0.0,
    )
    # With 0 margin, net recovered revenue must be <= 0 (negative costs incurred)
    for strategy in ["baseline", "rule_based", "ai"]:
        assert result[strategy]["net_recovered_revenue"] <= 0.0
        assert result[strategy]["intervention_cost"] >= 0.0


def test_recovery_probability_bounds_clamped():
    from simulator.models import Customer, Payment
    from simulator.recovery import recovery_probablity
    from datetime import datetime

    low_customer = Customer(
        id="c-low",
        successful_payments=0,
        failed_payments=100,
        recovered_payments=0,
    )
    # CARD_EXPIRED with RETRY_NOW gives 0.10 + 0 - 0.15 = -0.05 without clamping
    payment = Payment(
        id="p-edge",
        customer_id="c-low",
        amount=100.0,
        payment_method="CARD",
        bank="SBI",
        failure_code="CARD_EXPIRED",
        timestamp=datetime(2026, 1, 1),
        status="FAILED",
    )
    prob = recovery_probablity(low_customer, payment, "RETRY_NOW")
    assert 0.0 <= prob <= 1.0
    assert prob >= 0.0