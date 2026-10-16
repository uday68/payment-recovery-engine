import sys
from pathlib import Path
import statistics

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from backend.controlled_experiment import run_controlled_experiment
    from ml.model_store import load_model
except ImportError:
    from controlled_experiment import run_controlled_experiment
    from ml.model_store import load_model


def main():
    print("Running Recovery Policy Stability Experiment across 5 random seeds...", flush=True)

    seeds = [1, 2, 3, 4, 5]
    model = load_model()

    print()
    print("=" * 96)
    print("             4-WAY RECOVERY POLICY STABILITY & STATISTICAL SIGNIFICANCE")
    print("=" * 96)
    print(
        f"{'Seed':<6}"
        f"{'Baseline':>15}"
        f"{'Naive Rule':>15}"
        f"{'Expert Rule':>15}"
        f"{'AI Engine':>15}"
        f"{'AI vs Naive':>13}"
        f"{'AI vs Expert':>14}"
    )
    print("-" * 96)

    baseline_revs = []
    rule_revs = []
    expert_revs = []
    ai_revs = []

    baseline_rates = []
    rule_rates = []
    expert_rates = []
    ai_rates = []

    ai_vs_base_pcts = []
    ai_vs_naive_pcts = []
    ai_vs_expert_pcts = []

    seed_details = []

    for seed in seeds:
        result = run_controlled_experiment(
            customer_count=1000,
            payment_count=10000,
            seed=seed,
            model=model,
        )

        b_rev = result["baseline"]["recovered_revenue"]
        r_rev = result["rule_based"]["recovered_revenue"]
        e_rev = result["expert_rule"]["recovered_revenue"]
        a_rev = result["ai"]["recovered_revenue"]

        b_rate = result["baseline"]["recovery_rate"]
        r_rate = result["rule_based"]["recovery_rate"]
        e_rate = result["expert_rule"]["recovery_rate"]
        a_rate = result["ai"]["recovery_rate"]

        baseline_revs.append(b_rev)
        rule_revs.append(r_rev)
        expert_revs.append(e_rev)
        ai_revs.append(a_rev)

        baseline_rates.append(b_rate)
        rule_rates.append(r_rate)
        expert_rates.append(e_rate)
        ai_rates.append(a_rate)

        ai_vs_base = ((a_rev - b_rev) / b_rev * 100) if b_rev else 0.0
        ai_vs_naive = ((a_rev - r_rev) / r_rev * 100) if r_rev else 0.0
        ai_vs_expert = ((a_rev - e_rev) / e_rev * 100) if e_rev else 0.0

        ai_vs_base_pcts.append(ai_vs_base)
        ai_vs_naive_pcts.append(ai_vs_naive)
        ai_vs_expert_pcts.append(ai_vs_expert)

        print(
            f"{seed:<6}"
            f"{b_rev:>15,.2f}"
            f"{r_rev:>15,.2f}"
            f"{e_rev:>15,.2f}"
            f"{a_rev:>15,.2f}"
            f"{ai_vs_naive:>12.2f}%"
            f"{ai_vs_expert:>13.2f}%"
        )

        seed_details.append({
            "seed": seed,
            "failed_payments": result["failed_payments"],
            "at_risk_revenue": result["at_risk_revenue"],
            "baseline_revenue": b_rev,
            "rule_revenue": r_rev,
            "expert_revenue": e_rev,
            "ai_revenue": a_rev,
            "baseline_recovery_rate": b_rate,
            "rule_recovery_rate": r_rate,
            "expert_recovery_rate": e_rate,
            "ai_recovery_rate": a_rate,
            "ai_vs_base": ai_vs_base,
            "ai_vs_naive": ai_vs_naive,
            "ai_vs_expert": ai_vs_expert,
            "action_counts": result["action_counts"],
            "policy_blocked": result.get("policy_blocked", 0),
        })

    print("-" * 96)

    # Statistical Aggregations
    n = len(seeds)
    import math

    def stats_summary(arr):
        mean = statistics.mean(arr)
        stdev = statistics.stdev(arr) if n > 1 else 0.0
        se = stdev / math.sqrt(n) if n > 1 else 0.0
        # t_crit for df=4, 95% two-tailed = 2.776
        ci95_low = mean - 2.776 * se
        ci95_high = mean + 2.776 * se
        return mean, stdev, se, ci95_low, ci95_high

    b_m, b_s, b_se, b_cil, b_cih = stats_summary(baseline_revs)
    r_m, r_s, r_se, r_cil, r_cih = stats_summary(rule_revs)
    e_m, e_s, e_se, e_cil, e_cih = stats_summary(expert_revs)
    a_m, a_s, a_se, a_cil, a_cih = stats_summary(ai_revs)

    # Paired Student's t-tests
    try:
        from scipy import stats
        t_base, p_base = stats.ttest_rel(ai_revs, baseline_revs)
        t_naive, p_naive = stats.ttest_rel(ai_revs, rule_revs)
        t_expert, p_expert = stats.ttest_rel(ai_revs, expert_revs)
    except Exception:
        t_base, p_base = 0.0, 1.0
        t_naive, p_naive = 0.0, 1.0
        t_expert, p_expert = 0.0, 1.0

    print()
    print("=" * 96)
    print("                      AGGREGATE REVENUE STATISTICS (Rs.)")
    print("=" * 96)
    print(f"{'Strategy':<18} {'Mean':>14} {'Std Dev':>12} {'Std Error':>12} {'95% CI Lower':>16} {'95% CI Upper':>16}")
    print("-" * 96)
    print(f"{'Always Retry':<18} {b_m:>14,.2f} {b_s:>12,.2f} {b_se:>12,.2f} {b_cil:>16,.2f} {b_cih:>16,.2f}")
    print(f"{'Naive Rule':<18} {r_m:>14,.2f} {r_s:>12,.2f} {r_se:>12,.2f} {r_cil:>16,.2f} {r_cih:>16,.2f}")
    print(f"{'Expert Rule':<18} {e_m:>14,.2f} {e_s:>12,.2f} {e_se:>12,.2f} {e_cil:>16,.2f} {e_cih:>16,.2f}")
    print(f"{'AI Engine':<18} {a_m:>14,.2f} {a_s:>12,.2f} {a_se:>12,.2f} {a_cil:>16,.2f} {a_cih:>16,.2f}")
    print("-" * 96)

    print()
    print("=" * 96)
    print("                      RECOVERY RATE STATISTICS (%)")
    print("=" * 96)
    print(f"{'Strategy':<18} {'Mean Rate':>12} {'Std Dev':>12} {'Std Error':>12}")
    print("-" * 96)
    print(f"{'Always Retry':<18} {statistics.mean(baseline_rates)*100:>11.2f}% {statistics.stdev(baseline_rates)*100:>11.2f}% {statistics.stdev(baseline_rates)/math.sqrt(n)*100:>11.2f}%")
    print(f"{'Naive Rule':<18} {statistics.mean(rule_rates)*100:>11.2f}% {statistics.stdev(rule_rates)*100:>11.2f}% {statistics.stdev(rule_rates)/math.sqrt(n)*100:>11.2f}%")
    print(f"{'Expert Rule':<18} {statistics.mean(expert_rates)*100:>11.2f}% {statistics.stdev(expert_rates)*100:>11.2f}% {statistics.stdev(expert_rates)/math.sqrt(n)*100:>11.2f}%")
    print(f"{'AI Engine':<18} {statistics.mean(ai_rates)*100:>11.2f}% {statistics.stdev(ai_rates)*100:>11.2f}% {statistics.stdev(ai_rates)/math.sqrt(n)*100:>11.2f}%")
    print("-" * 96)

    print()
    print("=" * 96)
    print("                PAIRED STATISTICAL HYPOTHESIS TESTS (df = 4)")
    print("=" * 96)
    print(f"1. AI Engine vs Always Retry:")
    print(f"   Mean Lift:       {statistics.mean(ai_vs_base_pcts):+.2f}% ± {statistics.stdev(ai_vs_base_pcts):.2f}%")
    print(f"   Paired t-stat:   {t_base:.4f}")
    print(f"   p-value:         {p_base:.4e} {'(Statistically Significant, p < 0.001)' if p_base < 0.001 else ''}")
    print()
    print(f"2. AI Engine vs Naive Rule-Based:")
    print(f"   Mean Lift:       {statistics.mean(ai_vs_naive_pcts):+.2f}% ± {statistics.stdev(ai_vs_naive_pcts):.2f}%")
    print(f"   Paired t-stat:   {t_naive:.4f}")
    print(f"   p-value:         {p_naive:.4e} {'(Statistically Significant, p < 0.001)' if p_naive < 0.001 else ''}")
    print(f"   Consistency:     {sum(v > 0 for v in ai_vs_naive_pcts)}/5 seeds positive")
    print()
    print(f"3. AI Engine vs Expert Rule-Based:")
    print(f"   Mean Lift:       {statistics.mean(ai_vs_expert_pcts):+.2f}% ± {statistics.stdev(ai_vs_expert_pcts):.2f}%")
    print(f"   Paired t-stat:   {t_expert:.4f}")
    print(f"   p-value:         {p_expert:.4e} {'(Statistically Significant, p < 0.001)' if p_expert < 0.001 else ''}")
    print(f"   Consistency:     {sum(v > 0 for v in ai_vs_expert_pcts)}/5 seeds positive for AI")
    print("=" * 96)


if __name__ == "__main__":
    main()