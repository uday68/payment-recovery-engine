"""
Bandit Repository: Manages PostgreSQL persistence for Beta-Bernoulli Thompson Sampling posteriors.
"""
import psycopg
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone


DEFAULT_ACTIONS = ["RETRY_NOW", "RETRY_LATER", "SEND_REMINDER", "NO_ACTION"]


class BanditRepository:
    def __init__(self, database_url: str = "postgresql://recovery:recovery@localhost:5432/recovery_engine"):
        self.database_url = database_url
        self._in_memory_fallback: Dict[str, Dict[str, Any]] = {
            a: {
                "action": a,
                "alpha": 1.0,
                "beta": 1.0,
                "successes": 0,
                "failures": 0,
                "total_pulls": 0,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            for a in DEFAULT_ACTIONS
        }
        self.db_available = False
        try:
            self._create_table()
            self.db_available = True
        except Exception:
            self.db_available = False

    def _connect(self):
        return psycopg.connect(self.database_url, connect_timeout=1)

    def _create_table(self):
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS bandit_posterior (
                        action VARCHAR(64) PRIMARY KEY,
                        alpha DOUBLE PRECISION NOT NULL DEFAULT 1.0,
                        beta DOUBLE PRECISION NOT NULL DEFAULT 1.0,
                        successes INT NOT NULL DEFAULT 0,
                        failures INT NOT NULL DEFAULT 0,
                        total_pulls INT NOT NULL DEFAULT 0,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    );
                    """
                )
                for action in DEFAULT_ACTIONS:
                    cursor.execute(
                        """
                        INSERT INTO bandit_posterior (action, alpha, beta, successes, failures, total_pulls, updated_at)
                        VALUES (%s, 1.0, 1.0, 0, 0, 0, NOW())
                        ON CONFLICT (action) DO NOTHING;
                        """,
                        (action,),
                    )
            connection.commit()

    def get_all_arms(self) -> Dict[str, Dict[str, Any]]:
        if not self.db_available:
            return self._in_memory_fallback

        try:
            with self._connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT action, alpha, beta, successes, failures, total_pulls, updated_at
                        FROM bandit_posterior
                        ORDER BY action;
                        """
                    )
                    rows = cursor.fetchall()
                    if not rows:
                        return self._in_memory_fallback
                    arms = {}
                    for row in rows:
                        arms[row[0]] = {
                            "action": row[0],
                            "alpha": float(row[1]),
                            "beta": float(row[2]),
                            "successes": int(row[3]),
                            "failures": int(row[4]),
                            "total_pulls": int(row[5]),
                            "updated_at": row[6].isoformat() if row[6] else None,
                        }
                    return arms
        except Exception:
            return self._in_memory_fallback

    def update_posterior(self, action: str, reward: float) -> bool:
        """
        Updates the posterior Beta distribution with outcome reward:
        reward = 1.0 (success) -> alpha += 1.0, successes += 1
        reward = 0.0 (failure) -> beta += 1.0, failures += 1
        """
        reward = 1.0 if reward > 0.5 else 0.0
        succ = 1 if reward == 1.0 else 0
        fail = 1 if reward == 0.0 else 0

        # Always update in-memory
        if action in self._in_memory_fallback:
            arm = self._in_memory_fallback[action]
            arm["alpha"] += reward
            arm["beta"] += (1.0 - reward)
            arm["successes"] += succ
            arm["failures"] += fail
            arm["total_pulls"] += 1
            arm["updated_at"] = datetime.now(timezone.utc).isoformat()
        else:
            self._in_memory_fallback[action] = {
                "action": action,
                "alpha": 1.0 + reward,
                "beta": 1.0 + (1.0 - reward),
                "successes": succ,
                "failures": fail,
                "total_pulls": 1,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }

        if not self.db_available:
            return True

        try:
            with self._connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO bandit_posterior (action, alpha, beta, successes, failures, total_pulls, updated_at)
                        VALUES (%s, 1.0 + %s, 1.0 + %s, %s, %s, 1, NOW())
                        ON CONFLICT (action) DO UPDATE SET
                            alpha = bandit_posterior.alpha + EXCLUDED.alpha - 1.0,
                            beta = bandit_posterior.beta + EXCLUDED.beta - 1.0,
                            successes = bandit_posterior.successes + EXCLUDED.successes,
                            failures = bandit_posterior.failures + EXCLUDED.failures,
                            total_pulls = bandit_posterior.total_pulls + 1,
                            updated_at = NOW();
                        """,
                        (action, reward, 1.0 - reward, succ, fail),
                    )
                connection.commit()
            return True
        except Exception:
            return False
