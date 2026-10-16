import random
import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).parent.parent))
from simulator.generator import generate_payments,generate_customers
from simulator.recovery import recovery_probablity
from ml.model_store import load_model
from backend.decision.engine import choose_action, ACTION_COSTS
from backend.experiment import build_context,predict_actions

from backend.policy.engine import apply_policy
from backend.rule_baseline import choose_rule_action, choose_expert_rule_action

from backend.audit import create_audit_event



ACTIONS = [
    "RETRY_NOW",
    "RETRY_LATER",
    "SEND_REMINDER",
    "NO_ACTION",
]
def evaluate_strategy(payment, customer, action):
    probability = recovery_probablity(
        customer,
        payment,
        action,
    )

    recovered = recovery_outcome(
        payment.id,
        action,
        probability,
    )

    cost = ACTION_COSTS.get(action, 0.0)

    return {
        "action": action,
        "probability": probability,
        "recovered": recovered,
        "recovered_revenue": payment.amount if recovered else 0.0,
        "cost": cost,
    }
def recovery_outcome(payment_id,action, probability):
    """
    generate a deterministic recovery outcome.
    the same payment + action always produces the same outcome,
    allowing baseline and AI startegies  to be compared fairly
    """
    rng = random.Random(f"{payment_id}:{action}")
    return rng.random() < probability


def run_controlled_experiment(
        customer_count = 1000,
        payment_count =10000,
        seed=42,
        model=None,
        return_audit_events=False,
        margin: float = 1.0,
):
    random.seed(seed)
    customers = generate_customers(customer_count)
    payments = generate_payments(customers,payment_count)

    customer_map = {
        customer.id:customer
        for customer in customers
    }

    failed_payments = [payment for payment in payments if payment.status == "FAILED"]

    at_risk_revenue = sum(payment.amount for payment in failed_payments)

    if model is None:
        model = load_model()
    baseline_recoveries = 0
    baseline_revenue = 0.0
    baseline_cost = 0.0

    rule_recoveries = 0
    rule_revenue = 0.0
    rule_cost = 0.0

    expert_recoveries = 0
    expert_revenue = 0.0
    expert_cost = 0.0

    ai_recoveries = 0
    ai_revenue = 0.0
    ai_cost = 0.0
    ai_action =0
    audit_events =[]

    policy_allowed =0
    policy_blocked = 0
    ai_selected_no_action =0


    action_counts = {
        action:0
        for action in ACTIONS   
    }
    recommended_action_counts = {
        action : 0
        for action in ACTIONS
    }

    if failed_payments:
        contexts = [
            build_context(customer_map[payment.customer_id], payment)
            for payment in failed_payments
        ]
        all_rows = [
            {**ctx, "action": action}
            for ctx in contexts
            for action in ACTIONS
        ]
        df = pd.DataFrame(all_rows)
        all_probs = model.predict_proba(df)[:, 1]
        n_actions = len(ACTIONS)

    for i, payment in enumerate(failed_payments):
        customer = customer_map[payment.customer_id]
        #------------------------------
        #baseline
        #------------------------------

        baseline_probablity =  recovery_probablity(customer,payment,"RETRY_NOW")
        baseline_success = recovery_outcome(payment.id,"RETRY_NOW",baseline_probablity)
        baseline_cost += ACTION_COSTS.get("RETRY_NOW", 2.0)

        if baseline_success:
            baseline_recoveries+=1
            baseline_revenue+=payment.amount

        # -----------------------------------
        # RULE-BASED DECISION
        # -----------------------------------
        rule_action = choose_rule_action(payment.failure_code)
        rule_result = evaluate_strategy(
            payment,
            customer,
            rule_action,
        )
        rule_cost += rule_result["cost"]

        if rule_result["recovered"]:
            rule_recoveries += 1
            rule_revenue += payment.amount

        # -----------------------------------
        # EXPERT RULE-BASED DECISION
        # -----------------------------------
        expert_action = choose_expert_rule_action(payment.failure_code)
        expert_result = evaluate_strategy(
            payment,
            customer,
            expert_action,
        )
        expert_cost += expert_result["cost"]

        if expert_result["recovered"]:
            expert_recoveries += 1
            expert_revenue += payment.amount

        #-----------------------------------
        # AI DECISION
        #-----------------------------------
        start_idx = i * n_actions
        probs = all_probs[start_idx : start_idx + n_actions]
        probabilities = {
            action: float(prob)
            for action, prob in zip(ACTIONS, probs)
        }

        decision = choose_action(
            payment.amount,
            probabilities,
            margin=margin,
        )

        selected_action = decision["action"]
        recommended_action_counts[selected_action]+=1

        selected_probability = probabilities[selected_action]

        policy = apply_policy(
            action=selected_action,
            amount=payment.amount,
            probability=selected_probability,
        )
        approved_action = policy["action"]
        if selected_action == "NO_ACTION":
            ai_selected_no_action+=1

        audit_event = create_audit_event(
            payment_id=payment.id,
            customer_id=customer.id,
            amount=payment.amount,
            failure_code=payment.failure_code,
            probabilities=probabilities,
            recommended_action=selected_action,
            expected_value=decision["expected_value"],
            policy_allowed=policy["allowed"],
            policy_reason=policy["reason"],
            executed_action=approved_action,
        )

        if return_audit_events:
            audit_events.append(audit_event)

        if policy["allowed"]:
            policy_allowed += 1
        else:
            policy_blocked += 1

        action_counts[approved_action] += 1
        ai_cost += ACTION_COSTS.get(approved_action, 0.0)

        ai_probability = recovery_probablity(
            customer,
            payment,
            approved_action,
        )

        ai_success = recovery_outcome(
            payment.id,
            approved_action,
            ai_probability,
        )

        if ai_success:
            ai_recoveries += 1
            ai_revenue += payment.amount

    failed_count = len(failed_payments)

    baseline_recovery_rate = (baseline_recoveries/failed_count if failed_count else 0.0)

    rule_recovery_rate = (
        rule_recoveries / failed_count
        if failed_count
        else 0.0
    )

    ai_recovery_rate = (ai_recoveries/failed_count if failed_count else 0.0)

    baseline_revenue_per_failure = (baseline_revenue/ failed_count if failed_count else 0.0)

    rule_revenue_per_failure = (
        rule_revenue / failed_count
        if failed_count
        else 0.0
    )

    ai_revenue_per_failure = ( ai_revenue / failed_count
        if failed_count
        else 0.0
    )

    expert_recovery_rate = (
        expert_recoveries / failed_count
        if failed_count
        else 0.0
    )
    expert_revenue_per_failure = (
        expert_revenue / failed_count
        if failed_count
        else 0.0
    )

    # Net economics accounting for intervention costs and merchant margin
    baseline_net_revenue = (baseline_revenue * margin) - baseline_cost
    rule_net_revenue = (rule_revenue * margin) - rule_cost
    expert_net_revenue = (expert_revenue * margin) - expert_cost
    ai_net_revenue = (ai_revenue * margin) - ai_cost

    baseline_net_per_failure = (baseline_net_revenue / failed_count if failed_count else 0.0)
    rule_net_per_failure = (rule_net_revenue / failed_count if failed_count else 0.0)
    expert_net_per_failure = (expert_net_revenue / failed_count if failed_count else 0.0)
    ai_net_per_failure = (ai_net_revenue / failed_count if failed_count else 0.0)

    revenue_difference = (ai_revenue - baseline_revenue)
    revenue_improvement = (revenue_difference / baseline_revenue * 100 if baseline_revenue else 0.0)
    recovery_improvement = ((ai_recovery_rate - baseline_recovery_rate)/ baseline_recovery_rate* 100
        if baseline_recovery_rate
        else 0.0)

    net_revenue_difference = ai_net_revenue - baseline_net_revenue
    net_revenue_improvement = (
        (net_revenue_difference / abs(baseline_net_revenue) * 100)
        if baseline_net_revenue != 0
        else 0.0
    )
    
    result = {
        "customers": customer_count,
        "payments": payment_count,
        "failed_payments": failed_count,
        "at_risk_revenue": at_risk_revenue,
        "margin": margin,

        "baseline": {
            "failed_payments": failed_count,
            "recoveries": baseline_recoveries,
            "recovery_rate": baseline_recovery_rate,
            "recovered_revenue": baseline_revenue,
            "revenue_per_failure": baseline_revenue_per_failure,
            "intervention_cost": baseline_cost,
            "net_recovered_revenue": baseline_net_revenue,
            "net_revenue_per_failure": baseline_net_per_failure,
        },

        "rule_based": {
            "failed_payments": failed_count,
            "recoveries": rule_recoveries,
            "recovery_rate": rule_recovery_rate,
            "recovered_revenue": rule_revenue,
            "revenue_per_failure": rule_revenue_per_failure,
            "intervention_cost": rule_cost,
            "net_recovered_revenue": rule_net_revenue,
            "net_revenue_per_failure": rule_net_per_failure,
        },

        "expert_rule": {
            "failed_payments": failed_count,
            "recoveries": expert_recoveries,
            "recovery_rate": expert_recovery_rate,
            "recovered_revenue": expert_revenue,
            "revenue_per_failure": expert_revenue_per_failure,
            "intervention_cost": expert_cost,
            "net_recovered_revenue": expert_net_revenue,
            "net_revenue_per_failure": expert_net_per_failure,
        },

        "ai": {
            "failed_payments": failed_count,
            "recoveries": ai_recoveries,
            "recovery_rate": ai_recovery_rate,
            "recovered_revenue": ai_revenue,
            "revenue_per_failure": ai_revenue_per_failure,
            "intervention_cost": ai_cost,
            "net_recovered_revenue": ai_net_revenue,
            "net_revenue_per_failure": ai_net_per_failure,
        },

        "revenue_difference": revenue_difference,
        "revenue_improvement": revenue_improvement,
        "recovery_improvement": recovery_improvement,
        "net_revenue_difference": net_revenue_difference,
        "net_revenue_improvement": net_revenue_improvement,
        "vs_expert_rule": {
            "revenue_difference": ai_revenue - expert_revenue,
            "revenue_improvement": ((ai_revenue - expert_revenue) / expert_revenue * 100) if expert_revenue else 0.0,
            "recovery_improvement": ((ai_recovery_rate - expert_recovery_rate) / expert_recovery_rate * 100) if expert_recovery_rate else 0.0,
            "net_revenue_difference": ai_net_revenue - expert_net_revenue,
        },

        "action_counts": action_counts,
        "recommended_action_counts":recommended_action_counts,
        "policy_allowed": policy_allowed,
        "policy_blocked": policy_blocked,
        "ai_selected_no_action": ai_selected_no_action,
    }
    if return_audit_events:
        result["audit_events"] = audit_events

    return result

