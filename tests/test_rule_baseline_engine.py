from backend.rule_baseline import choose_rule_action, choose_expert_rule_action


def test_rule_baseline_selects_action_by_failure_code():
    assert choose_rule_action("BANK_TIMEOUT") == "RETRY_NOW"
    assert choose_rule_action("NETWORK_ERROR") == "RETRY_NOW"
    assert choose_rule_action("INSUFFICIENT_FUNDS") == "SEND_REMINDER"
    assert choose_rule_action("CARD_EXPIRED") == "SEND_REMINDER"
    assert choose_rule_action("LIMIT_EXCEEDED") == "RETRY_NOW"
    assert choose_rule_action("AUTHENTICATION_FAILED") == "SEND_REMINDER"


def test_rule_baseline_falls_back_to_no_action():
    assert choose_rule_action("UNKNOWN_FAILURE") == "NO_ACTION"


def test_expert_rule_baseline_selects_domain_optimized_action():
    assert choose_expert_rule_action("BANK_TIMEOUT") == "RETRY_LATER"
    assert choose_expert_rule_action("NETWORK_ERROR") == "RETRY_LATER"
    assert choose_expert_rule_action("INSUFFICIENT_FUNDS") == "SEND_REMINDER"
    assert choose_expert_rule_action("CARD_EXPIRED") == "SEND_REMINDER"
    assert choose_expert_rule_action("LIMIT_EXCEEDED") == "RETRY_LATER"
    assert choose_expert_rule_action("AUTHENTICATION_FAILED") == "SEND_REMINDER"
    assert choose_expert_rule_action("UNKNOWN_FAILURE") == "NO_ACTION"