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
