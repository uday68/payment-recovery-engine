import pytest
from backend.decision.engine import expected_value, choose_action


def test_no_action_ev_is_always_zero():
    # Even if an uncalibrated model outputs a positive probability for NO_ACTION
    assert expected_value(probability=0.8, amount=10000.0, action="NO_ACTION") == 0.0
    assert expected_value(probability=0.0, amount=5000.0, action="NO_ACTION") == 0.0


def test_choose_action_selects_no_action_when_all_ev_negative():
    # Very small amount ₹2, retry costs ₹2, probability 0.1
    # RETRY_NOW: 0.1 * 2 - 2 = -1.8
    # RETRY_LATER: 0.1 * 2 - 2 = -1.8
    # SEND_REMINDER: 0.1 * 2 - 1 = -0.8
    # NO_ACTION: 0.0
    probabilities = {
        "RETRY_NOW": 0.1,
        "RETRY_LATER": 0.1,
        "SEND_REMINDER": 0.1,
        "NO_ACTION": 0.0,
    }
    decision = choose_action(amount=2.0, probabilities=probabilities)
    assert decision["action"] == "NO_ACTION"
    assert decision["expected_value"] == 0.0


def test_choose_action_with_margin():
    probabilities = {
        "RETRY_NOW": 0.60,
        "RETRY_LATER": 0.70,
        "SEND_REMINDER": 0.50,
        "NO_ACTION": 0.0,
    }
    # With 2% MDR fee on ₹1,000 transaction: gross recovered margin = ₹20
    # RETRY_LATER: 0.70 * 20 - 2 = 14 - 2 = 12
    # SEND_REMINDER: 0.50 * 20 - 1 = 10 - 1 = 9
    decision = choose_action(amount=1000.0, probabilities=probabilities, margin=0.02)
    assert decision["action"] == "RETRY_LATER"
    assert pytest.approx(decision["expected_value"], 0.01) == 12.0
