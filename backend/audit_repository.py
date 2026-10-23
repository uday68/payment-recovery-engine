import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import psycopg

logger = logging.getLogger(__name__)


class AuditRepository:
    _shared_in_memory_audit = {}
    _shared_payment_claims = set()
    _shared_command_claims = set()

    def __init__(
        self,
        database_url: str = "postgresql://recovery:recovery@localhost:5432/recovery_engine",
        es_url: Optional[str] = None,
    ):
        self.database_url = database_url
        self._in_memory_audit = self._shared_in_memory_audit
        self._in_memory_payment_claims = self._shared_payment_claims
        self._in_memory_command_claims = self._shared_command_claims
        self.db_available = False

        try:
            from backend.elasticsearch_client import ElasticsearchAuditStore
            self.es_store = ElasticsearchAuditStore(es_url=es_url)
        except Exception as e:
            logger.debug(f"Elasticsearch store deferred: {e}")
            self.es_store = None

        if database_url and database_url != "memory://":
            try:
                self._create_table()
                self.db_available = True
            except Exception:
                self.db_available = False

    def _connect(self):
        # Enforce a 1-second connect timeout to prevent test hangs when DB is unreachable
        return psycopg.connect(self.database_url, connect_timeout=1)

    def _create_table(self):
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS recovery_audit (
                        id BIGSERIAL PRIMARY KEY,
                        payment_id TEXT NOT NULL,
                        customer_id TEXT NOT NULL,
                        amount DOUBLE PRECISION NOT NULL,
                        failure_code TEXT,

                        probabilities JSONB NOT NULL,

                        recommended_action TEXT NOT NULL,
                        expected_value DOUBLE PRECISION NOT NULL,

                        policy_allowed BOOLEAN NOT NULL,
                        policy_reason TEXT NOT NULL,

                        executed_action TEXT NOT NULL,

                        outcome TEXT,
                        attempts INTEGER,
                        recovered BOOLEAN,
                        retryable BOOLEAN,

                        timestamp TIMESTAMPTZ NOT NULL
                    );
                    """
                )
                cursor.execute(
                    """
                    ALTER TABLE recovery_audit
                    ADD COLUMN IF NOT EXISTS outcome TEXT,
                    ADD COLUMN IF NOT EXISTS attempts INTEGER,
                    ADD COLUMN IF NOT EXISTS recovered BOOLEAN,
                    ADD COLUMN IF NOT EXISTS retryable BOOLEAN,
                    ADD COLUMN IF NOT EXISTS bank TEXT,
                    ADD COLUMN IF NOT EXISTS payment_method TEXT,
                    ADD COLUMN IF NOT EXISTS event_id TEXT
                    """
                )
                cursor.execute(
                    """
                    DELETE FROM recovery_audit duplicate
                    USING recovery_audit keeper
                    WHERE duplicate.payment_id = keeper.payment_id
                      AND duplicate.id < keeper.id
                    """
                )
                cursor.execute(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS recovery_audit_payment_id_uidx
                    ON recovery_audit (payment_id)
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS recovery_idempotency (
                        payment_id TEXT PRIMARY KEY,
                        claimed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    );
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS command_idempotency (
                        command_id TEXT PRIMARY KEY,
                        claimed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    );
                    """
                )

    def save(self, event: Dict[str, Any]):
        if not self.db_available:
            self._in_memory_audit[event["payment_id"]] = dict(event)
        else:
            try:
                with self._connect() as connection:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            """
                            INSERT INTO recovery_audit (
                                payment_id,
                                customer_id,
                                amount,
                                failure_code,
                                probabilities,
                                recommended_action,
                                expected_value,
                                policy_allowed,
                                policy_reason,
                                executed_action,
                                outcome,
                                attempts,
                                recovered,
                                retryable,
                                timestamp,
                                bank,
                                payment_method,
                                event_id
                            )
                            VALUES (
                                %s, %s, %s, %s, %s,
                                %s, %s, %s, %s, %s,
                                %s, %s, %s, %s, %s,
                                %s, %s, %s
                            )
                            ON CONFLICT (payment_id)
                            DO NOTHING
                            """,
                            (
                                event["payment_id"],
                                event["customer_id"],
                                event["amount"],
                                event["failure_code"],
                                json.dumps(event["probabilities"]),
                                event["recommended_action"],
                                event["expected_value"],
                                event["policy_allowed"],
                                event["policy_reason"],
                                event["executed_action"],
                                event.get("outcome"),
                                event.get("attempts"),
                                event.get("recovered"),
                                event.get("retryable"),
                                event["timestamp"],
                                event.get("bank"),
                                event.get("payment_method"),
                                event.get("event_id"),
                            ),
                        )
            except Exception:
                self.db_available = False
                self._in_memory_audit[event["payment_id"]] = dict(event)

        # Index decision into Elasticsearch if store available
        if self.es_store is not None:
            try:
                self.es_store.index_decision(event)
            except Exception as e:
                logger.debug(f"Elasticsearch index call failed: {e}")

    def get_by_payment_id(self, payment_id: str) -> Optional[Dict[str, Any]]:
        if not self.db_available:
            return self._in_memory_audit.get(payment_id)

        try:
            with self._connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT
                            payment_id,
                            customer_id,
                            amount,
                            failure_code,
                            probabilities,
                            recommended_action,
                            expected_value,
                            policy_allowed,
                            policy_reason,
                            executed_action,
                            outcome,
                            attempts,
                            recovered,
                            retryable,
                            timestamp,
                            bank,
                            payment_method,
                            event_id
                        FROM recovery_audit
                        WHERE payment_id = %s
                        ORDER BY id DESC
                        LIMIT 1
                        """,
                        (payment_id,),
                    )

                    row = cursor.fetchone()

                    if row is None:
                        return None

                    return {
                        "payment_id": row[0],
                        "customer_id": row[1],
                        "amount": row[2],
                        "failure_code": row[3],
                        "probabilities": row[4],
                        "recommended_action": row[5],
                        "expected_value": row[6],
                        "policy_allowed": row[7],
                        "policy_reason": row[8],
                        "executed_action": row[9],
                        "outcome": row[10],
                        "attempts": row[11],
                        "recovered": row[12],
                        "retryable": row[13],
                        "timestamp": row[14].isoformat() if hasattr(row[14], "isoformat") else str(row[14]),
                        "bank": row[15] if len(row) > 15 else None,
                        "payment_method": row[16] if len(row) > 16 else None,
                        "event_id": row[17] if len(row) > 17 else None,
                    }
        except Exception:
            self.db_available = False
            return self._in_memory_audit.get(payment_id)

    def count_by_payment_id(self, payment_id: str) -> int:
        if not self.db_available:
            return 1 if payment_id in self._in_memory_audit else 0

        try:
            with self._connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT COUNT(*)
                        FROM recovery_audit
                        WHERE payment_id = %s
                        """,
                        (payment_id,),
                    )

                    return cursor.fetchone()[0]
        except Exception:
            self.db_available = False
            return 1 if payment_id in self._in_memory_audit else 0

    def claim_payment(self, payment_id: str) -> bool:
        if not self.db_available:
            if payment_id in self._in_memory_payment_claims:
                return False
            self._in_memory_payment_claims.add(payment_id)
            return True

        try:
            with self._connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO recovery_idempotency (
                            payment_id
                        )
                        VALUES (%s)
                        ON CONFLICT (payment_id)
                        DO NOTHING
                        RETURNING payment_id
                        """,
                        (payment_id,),
                    )

                    row = cursor.fetchone()

                    return row is not None
        except Exception:
            self.db_available = False
            if payment_id in self._in_memory_payment_claims:
                return False
            self._in_memory_payment_claims.add(payment_id)
            return True

    def claim_command(self, command_id: str) -> bool:
        if not self.db_available:
            if command_id in self._in_memory_command_claims:
                return False
            self._in_memory_command_claims.add(command_id)
            return True

        try:
            with self._connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO command_idempotency (command_id)
                        VALUES (%s)
                        ON CONFLICT (command_id)
                        DO NOTHING
                        RETURNING command_id
                        """,
                        (command_id,),
                    )

                    return cursor.fetchone() is not None
        except Exception:
            self.db_available = False
            if command_id in self._in_memory_command_claims:
                return False
            self._in_memory_command_claims.add(command_id)
            return True

    def search_decisions(
        self,
        q: Optional[str] = None,
        failure_code: Optional[str] = None,
        action: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """
        Search decision audits across Elasticsearch with automatic fallback to
        Postgres and in-memory audit store.
        """
        # 1. Try Elasticsearch
        if self.es_store is not None:
            try:
                es_result = self.es_store.search(
                    q=q,
                    failure_code=failure_code,
                    action=action,
                    from_date=from_date,
                    to_date=to_date,
                    limit=limit,
                    offset=offset,
                )
                if es_result is not None:
                    return es_result
            except Exception as e:
                logger.debug(f"Elasticsearch search attempt encountered exception: {e}")

        # 2. Try PostgreSQL
        if self.db_available:
            try:
                where_clauses = []
                params: List[Any] = []

                if q and q.strip():
                    pattern = f"%{q.strip()}%"
                    where_clauses.append(
                        "(payment_id ILIKE %s OR customer_id ILIKE %s OR policy_reason ILIKE %s OR failure_code ILIKE %s)"
                    )
                    params.extend([pattern, pattern, pattern, pattern])

                if failure_code and failure_code.strip():
                    where_clauses.append("UPPER(failure_code) = %s")
                    params.append(failure_code.strip().upper())

                if action and action.strip():
                    action_val = action.strip().upper()
                    where_clauses.append("(UPPER(executed_action) = %s OR UPPER(recommended_action) = %s)")
                    params.extend([action_val, action_val])

                if from_date:
                    where_clauses.append("timestamp >= %s")
                    params.append(from_date)

                if to_date:
                    where_clauses.append("timestamp <= %s")
                    params.append(to_date)

                where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

                with self._connect() as connection:
                    with connection.cursor() as cursor:
                        # Total count
                        cursor.execute(f"SELECT COUNT(*) FROM recovery_audit {where_sql}", tuple(params))
                        total = cursor.fetchone()[0]

                        # Aggregations by action
                        cursor.execute(
                            f"SELECT COALESCE(executed_action, recommended_action, 'NO_ACTION'), COUNT(*) FROM recovery_audit {where_sql} GROUP BY 1",
                            tuple(params),
                        )
                        by_action = {r[0]: r[1] for r in cursor.fetchall()}

                        # Aggregations by outcome
                        cursor.execute(
                            f"""
                            SELECT
                                COALESCE(outcome, CASE WHEN recovered IS TRUE THEN 'RECOVERED' WHEN recovered IS FALSE THEN 'FAILED' ELSE 'PENDING' END),
                                COUNT(*)
                            FROM recovery_audit {where_sql}
                            GROUP BY 1
                            """,
                            tuple(params),
                        )
                        by_outcome = {r[0]: r[1] for r in cursor.fetchall()}

                        # Records
                        fetch_params = list(params) + [max(1, limit), max(0, offset)]
                        cursor.execute(
                            f"""
                            SELECT
                                payment_id, customer_id, amount, failure_code,
                                recommended_action, expected_value, policy_allowed,
                                policy_reason, executed_action, outcome, recovered,
                                timestamp, bank, payment_method
                            FROM recovery_audit {where_sql}
                            ORDER BY timestamp DESC
                            LIMIT %s OFFSET %s
                            """,
                            tuple(fetch_params),
                        )

                        results = []
                        for row in cursor.fetchall():
                            results.append(
                                {
                                    "payment_id": row[0],
                                    "customer_id": row[1],
                                    "amount": row[2],
                                    "failure_code": row[3],
                                    "recommended_action": row[4],
                                    "expected_value": row[5],
                                    "policy_allowed": row[6],
                                    "policy_reason": row[7],
                                    "executed_action": row[8],
                                    "chosen_action": row[8] or row[4],
                                    "outcome": row[9],
                                    "recovered": row[10],
                                    "execution_result": row[9] or ("RECOVERED" if row[10] is True else "FAILED" if row[10] is False else "PENDING"),
                                    "policy_outcome": "ALLOWED" if row[6] else "BLOCKED",
                                    "timestamp": row[11].isoformat() if hasattr(row[11], "isoformat") else str(row[11]),
                                    "bank": row[12],
                                    "payment_method": row[13],
                                }
                            )

                        return {
                            "total": total,
                            "results": results,
                            "aggregations": {
                                "by_action": by_action,
                                "by_outcome": by_outcome,
                            },
                            "source": "postgres",
                        }
            except Exception as e:
                logger.warning(f"PostgreSQL search failed, falling back to in-memory: {e}")
                self.db_available = False

        # 3. Fallback: In-Memory Search
        filtered = []
        q_clean = q.strip().lower() if q and q.strip() else None
        fc_clean = failure_code.strip().upper() if failure_code and failure_code.strip() else None
        act_clean = action.strip().upper() if action and action.strip() else None

        for item in self._in_memory_audit.values():
            if fc_clean and str(item.get("failure_code", "")).upper() != fc_clean:
                continue

            if act_clean:
                rec = str(item.get("recommended_action", "")).upper()
                exe = str(item.get("executed_action", "")).upper()
                if act_clean not in (rec, exe):
                    continue

            if from_date and str(item.get("timestamp", "")) < from_date:
                continue
            if to_date and str(item.get("timestamp", "")) > to_date:
                continue

            if q_clean:
                combined_text = (
                    f"{item.get('payment_id', '')} "
                    f"{item.get('customer_id', '')} "
                    f"{item.get('failure_code', '')} "
                    f"{item.get('policy_reason', '')} "
                    f"{item.get('bank', '')}"
                ).lower()
                if q_clean not in combined_text:
                    continue

            filtered.append(item)

        # Sort descending by timestamp
        filtered.sort(key=lambda x: str(x.get("timestamp", "")), reverse=True)

        # Aggregations
        by_action: Dict[str, int] = {}
        by_outcome: Dict[str, int] = {}
        for it in filtered:
            act = str(it.get("executed_action") or it.get("recommended_action") or "NO_ACTION")
            by_action[act] = by_action.get(act, 0) + 1

            out = it.get("outcome")
            if not out:
                recov = it.get("recovered")
                out = "RECOVERED" if recov is True else "FAILED" if recov is False else "PENDING"
            by_outcome[str(out)] = by_outcome.get(str(out), 0) + 1

        paged_items = filtered[offset : offset + limit]
        formatted_results = []
        for r in paged_items:
            recov = r.get("recovered")
            formatted_results.append(
                {
                    "payment_id": r.get("payment_id"),
                    "customer_id": r.get("customer_id"),
                    "amount": float(r.get("amount", 0.0) or 0.0),
                    "failure_code": r.get("failure_code"),
                    "recommended_action": r.get("recommended_action"),
                    "expected_value": float(r.get("expected_value", 0.0) or 0.0),
                    "policy_allowed": bool(r.get("policy_allowed", False)),
                    "policy_reason": r.get("policy_reason"),
                    "executed_action": r.get("executed_action"),
                    "chosen_action": r.get("executed_action") or r.get("recommended_action"),
                    "outcome": r.get("outcome"),
                    "recovered": recov,
                    "execution_result": r.get("outcome") or ("RECOVERED" if recov is True else "FAILED" if recov is False else "PENDING"),
                    "policy_outcome": "ALLOWED" if r.get("policy_allowed") else "BLOCKED",
                    "timestamp": str(r.get("timestamp", "")),
                    "bank": r.get("bank"),
                    "payment_method": r.get("payment_method"),
                }
            )

        return {
            "total": len(filtered),
            "results": formatted_results,
            "aggregations": {
                "by_action": by_action,
                "by_outcome": by_outcome,
            },
            "source": "in_memory",
        }
