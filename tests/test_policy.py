from backend.policy.engine import validate_action


def test_no_action_is_alway_allowed():
    result = validate_action(
            action ="NO_ACTION",amount=5000,probability=0.01
    )
    assert result["allowed"] is True


def test_retry_requires_minimum_confidence():
    result = validate_action(
        action ="RETRY_NOW",
        amount =5000,
        probability=0.20

    )
    assert result["allowed"] is False

def test_high_confidence_retry_is_allowed():
    result = validate_action(
        action = "RETRY_LATER",
        amount = 5000,
        probability =0.75
    )
    assert result["allowed"] is True


def test_retry_blocked_when_below_ev_floor():
    result = validate_action(
        action="RETRY_NOW",
        amount=5000,
        probability=0.75,
        expected_value=30.0,  # Below default ev_floor of 50.0
    )
    assert result["allowed"] is False
    assert "Expected value below configured EV floor" in result["reason"]


def test_send_reminder_allowed_with_lower_confidence():
    # Reminders are non-invasive notifications, not subject to the 50% hard retry floor
    result = validate_action(
        action="SEND_REMINDER",
        amount=5000,
        probability=0.35,
    )
    assert result["allowed"] is True

    