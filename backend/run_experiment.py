import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

try:
    from backend.controlled_experiment import run_controlled_experiment
except ImportError:
    from controlled_experiment import run_controlled_experiment


def main():
    print("Running Payment Recovery Experiment (1,000 customers, 10,000 payments)...", flush=True)

    result = run_controlled_experiment(
        customer_count=1000,
        payment_count=10000,
        seed=42,
    )

    failed = result["failed_payments"]
    at_risk = result.get("at_risk_revenue", 0.0)

    baseline = result["baseline"]
    rule = result.get("rule_based", {})
    expert = result.get("expert_rule", {})
    ai = result["ai"]

    print()
    print("=" * 88)
    print("                 4-WAY PAYMENT RECOVERY EXPERIMENT & BENCHMARK")
    print("=" * 88)
    print(f"Failed Payments:          {failed:,}")
    print(f"At-Risk Revenue:          Rs. {at_risk:,.2f}")
    print()

    # 4-Way Summary Table
    print("-" * 88)
    print(f"{'Metric':<18} {'Always Retry':>16} {'Naive Rule':>16} {'Expert Rule':>16} {'AI Engine':>16}")
    print("-" * 88)

    b_rec = f"{baseline['recoveries']:,}"
    r_rec = f"{rule.get('recoveries', 0):,}"
    e_rec = f"{expert.get('recoveries', 0):,}"
    a_rec = f"{ai['recoveries']:,}"
    print(f"{'Recoveries':<18} {b_rec:>16} {r_rec:>16} {e_rec:>16} {a_rec:>16}")

    b_rate = f"{baseline['recovery_rate']:.2%}"
    r_rate = f"{rule.get('recovery_rate', 0):.2%}"
    e_rate = f"{expert.get('recovery_rate', 0):.2%}"
    a_rate = f"{ai['recovery_rate']:.2%}"
    print(f"{'Recovery Rate':<18} {b_rate:>16} {r_rate:>16} {e_rate:>16} {a_rate:>16}")

    b_rev = f"Rs. {baseline['recovered_revenue']:,.2f}"
    r_rev = f"Rs. {rule.get('recovered_revenue', 0):,.2f}"
    e_rev = f"Rs. {expert.get('recovered_revenue', 0):,.2f}"
    a_rev = f"Rs. {ai['recovered_revenue']:,.2f}"
    print(f"{'Recovered Revenue':<18} {b_rev:>16} {r_rev:>16} {e_rev:>16} {a_rev:>16}")

    b_rpf = f"Rs. {baseline['revenue_per_failure']:,.2f}"
    r_rpf = f"Rs. {rule.get('revenue_per_failure', 0):,.2f}"
    e_rpf = f"Rs. {expert.get('revenue_per_failure', 0):,.2f}"
    a_rpf = f"Rs. {ai['revenue_per_failure']:,.2f}"
    print(f"{'Revenue / Failure':<18} {b_rpf:>16} {r_rpf:>16} {e_rpf:>16} {a_rpf:>16}")
    print("-" * 88)
    print()

    # Detailed Breakdowns
    print("STRATEGY PERFORMANCE")
    print("=" * 88)

    print("1. NAIVE BASELINE (Always Retry Now)")
    print(f"   Recovered Revenue:        Rs. {baseline['recovered_revenue']:,.2f}")
    print(f"   Recovery Rate:            {baseline['recovery_rate']:.2%}")
    print(f"   Revenue / Failed Payment: Rs. {baseline['revenue_per_failure']:,.2f}")
    print()

    if rule:
        print("2. NAIVE RULE-BASED (Failure Code Mapping - Unoptimized)")
        print(f"   Recovered Revenue:        Rs. {rule['recovered_revenue']:,.2f}")
        print(f"   Recovery Rate:            {rule['recovery_rate']:.2%}")
        print(f"   Revenue / Failed Payment: Rs. {rule['revenue_per_failure']:,.2f}")
        print()

    if expert:
        print("3. EXPERT-TUNED RULE-BASED (Domain-Optimized Failure Code Mapping)")
        print(f"   Recovered Revenue:        Rs. {expert['recovered_revenue']:,.2f}")
        print(f"   Recovery Rate:            {expert['recovery_rate']:.2%}")
        print(f"   Revenue / Failed Payment: Rs. {expert['revenue_per_failure']:,.2f}")
        print()

    print("4. AI DECISION ENGINE (ML + Expected Value Policy)")
    print(f"   Recovered Revenue:        Rs. {ai['recovered_revenue']:,.2f}")
    print(f"   Recovery Rate:            {ai['recovery_rate']:.2%}")
    print(f"   Revenue / Failed Payment: Rs. {ai['revenue_per_failure']:,.2f}")
    print()

    # Action Breakdown & Policy
    if "action_counts" in result:
        print("AI ACTION DISTRIBUTION")
        print("-" * 76)
        for action, count in result["action_counts"].items():
            pct = (count / failed * 100) if failed > 0 else 0
            print(f"   {action:<20} {count:>6,} ({pct:>5.1f}%)")
        print()

    if "policy_allowed" in result:
        print()
        print("AI RECOMMENDATIONS")
        print("-" * 68)

        for action, count in result["recommended_action_counts"].items():
            print(
                f"   {action:<20} "
                f"{count:>6,} "
                f"({count / result['failed_payments'] * 100:5.1f}%)"
            )

        print()
        print("AI POLICY OUTCOME")
        print("-" * 68)

        for action, count in result["action_counts"].items():
            print(
                f"   {action:<20} "
                f"{count:>6,} "
                f"({count / result['failed_payments'] * 100:5.1f}%)"
            )
        print()
    # Final Comparison
    diff_baseline = ai["recovered_revenue"] - baseline["recovered_revenue"]
    imp_baseline = (diff_baseline / baseline["recovered_revenue"] * 100) if baseline["recovered_revenue"] > 0 else 0.0

    print("COMPARISON & IMPACT")
    print("=" * 88)
    print(f"   vs Always Retry:          {'+' if diff_baseline >= 0 else ''}Rs. {diff_baseline:,.2f} ({'+' if imp_baseline >= 0 else ''}{imp_baseline:.2f}%)")

    if rule:
        diff_rule = ai["recovered_revenue"] - rule["recovered_revenue"]
        imp_rule = (diff_rule / rule["recovered_revenue"] * 100) if rule["recovered_revenue"] > 0 else 0.0
        print(f"   vs Naive Rule-Based:      {'+' if diff_rule >= 0 else ''}Rs. {diff_rule:,.2f} ({'+' if imp_rule >= 0 else ''}{imp_rule:.2f}%)")

    if expert:
        diff_expert = ai["recovered_revenue"] - expert["recovered_revenue"]
        imp_expert = (diff_expert / expert["recovered_revenue"] * 100) if expert["recovered_revenue"] > 0 else 0.0
        print(f"   vs Expert Rule-Based:     {'+' if diff_expert >= 0 else ''}Rs. {diff_expert:,.2f} ({'+' if imp_expert >= 0 else ''}{imp_expert:.2f}%)")

    print("=" * 88)


if __name__ == "__main__":
    main()