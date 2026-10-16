import pytest
from backend.bandit import ThompsonSamplingBandit
from backend.bandit_repository import BanditRepository


def test_bandit_no_action_has_zero_probability_and_ev():
    bandit = ThompsonSamplingBandit(database_url="memory://", random_state=42)
    res = bandit.sample_arm(
        eligible_actions=["RETRY_NOW", "NO_ACTION"],
        amount=5000.0,
    )
    assert res["sampled_probabilities"]["NO_ACTION"] == 0.0
    assert res["sampled_expected_values"]["NO_ACTION"] == 0.0
    assert res["posterior_means"]["NO_ACTION"] == 0.0


def test_contextual_bandit_segregates_failure_contexts():
    repo = BanditRepository(database_url="memory://")
    bandit = ThompsonSamplingBandit(repository=repo, random_state=42)

    context_expired = {"failure_code": "CARD_EXPIRED"}
    context_timeout = {"failure_code": "BANK_TIMEOUT"}

    # Simulate 10 failures for RETRY_NOW under CARD_EXPIRED
    for _ in range(10):
        bandit.update("RETRY_NOW", success=False, context=context_expired)

    # Simulate 10 successes for RETRY_NOW under BANK_TIMEOUT
    for _ in range(10):
        bandit.update("RETRY_NOW", success=True, context=context_timeout)

    # Sample under CARD_EXPIRED context
    sample_expired = bandit.sample_arm(
        eligible_actions=["RETRY_NOW", "SEND_REMINDER", "NO_ACTION"],
        amount=1000.0,
        context=context_expired,
    )

    # Sample under BANK_TIMEOUT context
    sample_timeout = bandit.sample_arm(
        eligible_actions=["RETRY_NOW", "SEND_REMINDER", "NO_ACTION"],
        amount=1000.0,
        context=context_timeout,
    )

    # Under CARD_EXPIRED, RETRY_NOW probability should be significantly lower than under BANK_TIMEOUT
    prob_expired = sample_expired["sampled_probabilities"]["RETRY_NOW"]
    prob_timeout = sample_timeout["sampled_probabilities"]["RETRY_NOW"]

    assert prob_expired < prob_timeout


def test_bandit_determinism_under_fixed_seed():
    """Verify that bandits with identical seeds yield identical sample sequences."""
    b1 = ThompsonSamplingBandit(database_url="memory://", random_state=999)
    b2 = ThompsonSamplingBandit(database_url="memory://", random_state=999)

    actions = ["RETRY_NOW", "RETRY_LATER", "SEND_REMINDER", "NO_ACTION"]
    r1 = b1.sample_arm(eligible_actions=actions, amount=1500.0)
    r2 = b2.sample_arm(eligible_actions=actions, amount=1500.0)

    assert r1["selected_action"] == r2["selected_action"]
    assert r1["sampled_probabilities"] == r2["sampled_probabilities"]
    assert r1["sampled_expected_values"] == r2["sampled_expected_values"]


def test_bandit_empty_eligible_actions_returns_no_action():
    bandit = ThompsonSamplingBandit(database_url="memory://")
    res = bandit.sample_arm(eligible_actions=[], amount=1000.0)
    assert res["selected_action"] == "NO_ACTION"


def test_bandit_negative_ev_chooses_no_action():
    """When amount is ₹1 and retry cost is ₹2, sampled EV is negative, so NO_ACTION (EV=0) is chosen."""
    bandit = ThompsonSamplingBandit(database_url="memory://", random_state=42)
    res = bandit.sample_arm(
        eligible_actions=["RETRY_NOW", "NO_ACTION"],
        amount=1.0,  # ₹1 recovery vs ₹2 cost
    )
    assert res["selected_action"] == "NO_ACTION"
    assert res["sampled_expected_values"]["NO_ACTION"] == 0.0


def test_bandit_zero_margin_chooses_no_action():
    """With 0 margin, any intervention yields 0 revenue - cost < 0, so NO_ACTION is chosen."""
    bandit = ThompsonSamplingBandit(database_url="memory://", random_state=42)
    res = bandit.sample_arm(
        eligible_actions=["RETRY_NOW", "SEND_REMINDER", "NO_ACTION"],
        amount=5000.0,
        margin=0.0,
    )
    assert res["selected_action"] == "NO_ACTION"


def test_bandit_online_simulation_tracks_reward_and_regret():
    """
    Simulates an online sequence of 100 payments, tracking cumulative net reward,
    oracle regret, action distributions, and costs for the contextual bandit.
    """
    from simulator.models import Customer, Payment
    from simulator.recovery import recovery_probablity
    from backend.controlled_experiment import recovery_outcome
    from backend.decision.engine import ACTION_COSTS
    from datetime import datetime

    bandit = ThompsonSamplingBandit(database_url="memory://", random_state=42)

    customer = Customer(
        id="c-sim",
        successful_payments=50,
        failed_payments=10,
        recovered_payments=5,
    )

    failure_types = ["BANK_TIMEOUT", "INSUFFICIENT_FUNDS", "CARD_EXPIRED"]
    actions = ["RETRY_NOW", "RETRY_LATER", "SEND_REMINDER", "NO_ACTION"]

    bandit_net_rewards = 0.0
    oracle_net_rewards = 0.0
    bandit_recoveries = 0
    bandit_costs = 0.0
    action_counts = {a: 0 for a in actions}

    for i in range(100):
        fc = failure_types[i % len(failure_types)]
        payment = Payment(
            id=f"sim-p-{i}",
            customer_id=customer.id,
            amount=2000.0,
            payment_method="UPI",
            bank="HDFC",
            failure_code=fc,
            timestamp=datetime(2026, 1, 1),
            status="FAILED",
        )
        ctx = {"failure_code": fc}

        # Bandit selects action
        bandit_decision = bandit.sample_arm(
            eligible_actions=actions,
            amount=payment.amount,
            context=ctx,
            margin=1.0,
        )
        chosen_action = bandit_decision["selected_action"]
        action_counts[chosen_action] += 1

        cost = ACTION_COSTS.get(chosen_action, 0.0)
        bandit_costs += cost

        # Outcome
        prob = recovery_probablity(customer, payment, chosen_action)
        success = recovery_outcome(payment.id, chosen_action, prob)
        if success:
            bandit_recoveries += 1
            bandit_net_rewards += payment.amount - cost
        else:
            bandit_net_rewards -= cost

        # Update posterior
        if chosen_action != "NO_ACTION":
            bandit.update(chosen_action, success=success, context=ctx)

        # Oracle action: the action with max true EV in simulator
        true_evs = {
            a: (recovery_probablity(customer, payment, a) * payment.amount) - ACTION_COSTS.get(a, 0.0)
            for a in actions
        }
        oracle_action = max(true_evs, key=true_evs.get)
        oracle_cost = ACTION_COSTS.get(oracle_action, 0.0)
        oracle_prob = recovery_probablity(customer, payment, oracle_action)
        oracle_success = recovery_outcome(payment.id, oracle_action, oracle_prob)
        if oracle_success:
            oracle_net_rewards += payment.amount - oracle_cost
        else:
            oracle_net_rewards -= oracle_cost

    cumulative_regret = oracle_net_rewards - bandit_net_rewards
    recovery_rate = bandit_recoveries / 100.0

    assert recovery_rate > 0.0
    assert bandit_costs > 0.0
    assert sum(action_counts.values()) == 100
    # Regret should be finite
    assert isinstance(cumulative_regret, float)

