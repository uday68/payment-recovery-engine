import json

import psycopg


class AuditRepository:
    def __init__(self, database_url="postgresql://recovery:recovery@localhost:5432/recovery_engine"):
        self.database_url = database_url
        self._in_memory_audit = {}
        self._in_memory_payment_claims = set()
        self._in_memory_command_claims = set()
        self.db_available = False

        if database_url and database_url != "memory://":
            try:
                self._create_table()
                self.db_available = True
            except Exception:
                self.db_available = False

    def _connect(self):
        # Enforce a 1-second connect timeout to prevent test hangs when DB is unreachable
        return psycopg.connect(self.database_url, connect_timeout=1)

    def _create_table(self,):
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
    def save(self, event):
        if not self.db_available:
            self._in_memory_audit[event["payment_id"]] = dict(event)
            return

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

    def get_by_payment_id(self, payment_id):
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

    def count_by_payment_id(self, payment_id):
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

    def claim_payment(self, payment_id):
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

    def claim_command(self, command_id):
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