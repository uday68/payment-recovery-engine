ACTION_COSTS = {
    "RETRY_NOW": 2.0,
    "RETRY_LATER": 2.0,
    "SEND_REMINDER": 1.0,
    "NO_ACTION": 0.0,
}


def expected_value(
    probability: float,
    amount: float,
    action: str,
    margin: float = 1.0,
) -> float:
    """
    Calculates expected net economic recovery value for an action.
    NO_ACTION produces 0 recovery, so its gross recovery is always 0.
    """
    if action == "NO_ACTION":
        return 0.0

    cost = ACTION_COSTS.get(action, 0.0)
    recovery_value = float(probability) * float(amount) * float(margin)

    return float(recovery_value - cost)


def choose_action(
    amount: float,
    probabilities: dict[str, float],
    margin: float = 1.0,
) -> dict:
    """
    Selects the action that maximizes net expected economic recovery value.
    If all active actions yield negative EV, NO_ACTION (EV = 0) is chosen.
    """
    values = {}

    for action, probability in probabilities.items():
        values[action] = expected_value(
            probability,
            amount,
            action,
            margin=margin,
        )

    best_action = max(
        values,
        key=values.get,
    )

    return {
        "action": best_action,
        "expected_value": values[best_action],
        "all_values": values,
    }