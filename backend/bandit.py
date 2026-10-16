"""
Beta-Bernoulli Thompson Sampling Engine for Revenue Recovery Action Selection.
Maintains conjugate Beta priors, draws posterior samples, weights by Expected Value,
and persists posterior updates directly to PostgreSQL.
"""
import numpy as np
from typing import Dict, Any, List, Optional, Tuple
from scipy.stats import beta as beta_dist

from backend.bandit_repository import BanditRepository, DEFAULT_ACTIONS

ACTION_COSTS = {
    "RETRY_NOW": 2.0,
    "RETRY_LATER": 2.0,
    "SEND_REMINDER": 1.0,
    "NO_ACTION": 0.0,
}


class ThompsonSamplingBandit:
    def __init__(
        self,
        database_url: str = "postgresql://recovery:recovery@localhost:5432/recovery_engine",
        repository: Optional[BanditRepository] = None,
        random_state: Optional[int] = None,
    ):
        self.repository = repository or BanditRepository(database_url)
        self.rng = np.random.RandomState(random_state)

    def sample_arm(
        self,
        eligible_actions: List[str],
        amount: float = 0.0,
        model_probabilities: Optional[Dict[str, float]] = None,
        action_costs: Optional[Dict[str, float]] = None,
        context: Optional[Dict[str, Any]] = None,
        margin: float = 1.0,
    ) -> Dict[str, Any]:
        """
        Samples an action using Thompson Sampling over Beta posteriors,
        weighted by Expected Value (Sampled Prob * Margin * Amount - Cost).
        NO_ACTION strictly evaluates to 0 recovery probability and 0 Expected Value.
        
        Strict constraint: The returned action MUST be within eligible_actions.
        """
        if not eligible_actions:
            return {
                "selected_action": "NO_ACTION",
                "sampled_probabilities": {},
                "sampled_expected_values": {},
                "posterior_means": {},
            }

        arms = self.repository.get_all_arms()
        costs = action_costs or ACTION_COSTS

        sampled_probs: Dict[str, float] = {}
        sampled_evs: Dict[str, float] = {}
        posterior_means: Dict[str, float] = {}

        for action in eligible_actions:
            if action == "NO_ACTION":
                sampled_probs[action] = 0.0
                posterior_means[action] = 0.0
                sampled_evs[action] = 0.0
                continue

            arm_key = action
            if context and "failure_code" in context:
                candidate_key = f"{context['failure_code']}:{action}"
                if candidate_key in arms:
                    arm_key = candidate_key

            arm_data = arms.get(arm_key, arms.get(action, {"alpha": 1.0, "beta": 1.0}))
            alpha = max(arm_data.get("alpha", 1.0), 0.01)
            beta_param = max(arm_data.get("beta", 1.0), 0.01)

            # Draw a sample from Beta(alpha, beta)
            sampled_theta = float(self.rng.beta(alpha, beta_param))
            
            # If model probabilities are supplied, optionally blend as informed prior
            if model_probabilities and action in model_probabilities:
                model_p = model_probabilities[action]
                effective_prob = 0.7 * sampled_theta + 0.3 * model_p
            else:
                effective_prob = sampled_theta

            sampled_probs[action] = round(effective_prob, 4)
            posterior_means[action] = round(alpha / (alpha + beta_param), 4)

            # Compute sampled Expected Value: P(recovery) * (margin * amount) - cost
            cost = costs.get(action, 0.0)
            sampled_ev = (effective_prob * amount * margin) - cost
            sampled_evs[action] = round(sampled_ev, 2)

        # Select action with maximum sampled Expected Value
        best_action = max(sampled_evs, key=sampled_evs.get)

        return {
            "selected_action": best_action,
            "sampled_probabilities": sampled_probs,
            "sampled_expected_values": sampled_evs,
            "posterior_means": posterior_means,
            "all_arms": arms,
        }

    def update(
        self,
        action: str,
        success: bool,
        context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Records the real recovery outcome into the posterior distribution.
        success=True  -> reward = 1.0 (recovery succeeded)
        success=False -> reward = 0.0 (recovery failed)
        """
        reward = 1.0 if success else 0.0
        res = self.repository.update_posterior(action, reward)
        if context and "failure_code" in context:
            ctx_key = f"{context['failure_code']}:{action}"
            self.repository.update_posterior(ctx_key, reward)
        return res

    def get_state(self) -> Dict[str, Any]:
        """
        Returns the full statistical state of all arms with Bayesian credible intervals.
        """
        arms = self.repository.get_all_arms()
        stats = []

        for action, data in arms.items():
            a = data["alpha"]
            b = data["beta"]
            mean = a / (a + b)
            variance = (a * b) / (((a + b) ** 2) * (a + b + 1))
            # 95% Bayesian Credible Interval via Beta percent point function
            ci_low = float(beta_dist.ppf(0.025, a, b))
            ci_high = float(beta_dist.ppf(0.975, a, b))

            stats.append({
                "action": action,
                "alpha": round(a, 3),
                "beta": round(b, 3),
                "mean_reward": round(mean, 4),
                "variance": round(variance, 6),
                "credible_interval_95": [round(ci_low, 4), round(ci_high, 4)],
                "successes": data["successes"],
                "failures": data["failures"],
                "total_pulls": data["total_pulls"],
                "updated_at": data.get("updated_at"),
            })

        return {
            "status": "LIVE" if self.repository.db_available else "IN_MEMORY",
            "algorithm": "Beta-Bernoulli Thompson Sampling",
            "priors": "Beta(1.0, 1.0) Uniform",
            "arms": stats,
            "total_decisions": sum(s["total_pulls"] for s in stats),
        }
