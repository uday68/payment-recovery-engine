package events

import (
	"context"
	"database/sql"
	"fmt"
	"time"

	_ "github.com/lib/pq"
)

type PostgresEventStore struct {
	db *sql.DB
}

func NewPostgresEventStore(databaseURL string) (*PostgresEventStore, error) {
	db, err := sql.Open("postgres", databaseURL)
	if err != nil {
		return nil, err
	}

	if err := db.Ping(); err != nil {
		db.Close()
		return nil, err
	}

	// Schema initialization with stateful lease columns
	_, err = db.Exec(`
		CREATE TABLE IF NOT EXISTS event_idempotency (
			event_id TEXT PRIMARY KEY,
			status TEXT NOT NULL DEFAULT 'PROCESSING',
			worker_id TEXT NOT NULL DEFAULT '',
			lease_expires_at TIMESTAMPTZ NOT NULL DEFAULT NOW() + INTERVAL '30 seconds',
			retry_count INT NOT NULL DEFAULT 0,
			max_retries INT NOT NULL DEFAULT 3,
			last_error TEXT,
			claimed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
			completed_at TIMESTAMPTZ
		);

		ALTER TABLE event_idempotency ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'PROCESSING';
		ALTER TABLE event_idempotency ADD COLUMN IF NOT EXISTS worker_id TEXT NOT NULL DEFAULT '';
		ALTER TABLE event_idempotency ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMPTZ NOT NULL DEFAULT NOW() + INTERVAL '30 seconds';
		ALTER TABLE event_idempotency ADD COLUMN IF NOT EXISTS retry_count INT NOT NULL DEFAULT 0;
		ALTER TABLE event_idempotency ADD COLUMN IF NOT EXISTS max_retries INT NOT NULL DEFAULT 3;
		ALTER TABLE event_idempotency ADD COLUMN IF NOT EXISTS last_error TEXT;
		ALTER TABLE event_idempotency ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ;
	`)
	if err != nil {
		db.Close()
		return nil, fmt.Errorf("initialize event_idempotency table: %w", err)
	}

	return &PostgresEventStore{db: db}, nil
}

// Claim provides backward compatibility with legacy EventStoreClaimer
func (s *PostgresEventStore) Claim(eventID string) (bool, error) {
	res, err := s.ClaimOrRenew(context.Background(), eventID, "default-postgres-worker", 30*time.Second, 3)
	if err != nil {
		return false, err
	}
	return res.Claimed, nil
}

func (s *PostgresEventStore) ClaimOrRenew(
	ctx context.Context,
	eventID string,
	workerID string,
	leaseDuration time.Duration,
	maxRetries int,
) (EventClaimResult, error) {
	tx, err := s.db.BeginTx(ctx, &sql.TxOptions{Isolation: sql.LevelReadCommitted})
	if err != nil {
		return EventClaimResult{}, fmt.Errorf("begin tx: %w", err)
	}
	defer tx.Rollback()

	// Try inserting new processing record
	var insertedID string
	err = tx.QueryRowContext(ctx, `
		INSERT INTO event_idempotency (
			event_id, status, worker_id, lease_expires_at, retry_count, max_retries, claimed_at
		) VALUES (
			$1, 'PROCESSING', $2, NOW() + $3::interval, 0, $4, NOW()
		)
		ON CONFLICT (event_id) DO NOTHING
		RETURNING event_id
	`, eventID, workerID, fmt.Sprintf("%d seconds", int(leaseDuration.Seconds())), maxRetries).Scan(&insertedID)

	if err == nil {
		if err := tx.Commit(); err != nil {
			return EventClaimResult{}, fmt.Errorf("commit insert: %w", err)
		}
		return EventClaimResult{Claimed: true, RetryCount: 0}, nil
	} else if err != sql.ErrNoRows {
		return EventClaimResult{}, fmt.Errorf("insert event claim: %w", err)
	}

	// Record exists, fetch current row with FOR UPDATE lock
	var (
		status         string
		existingWorker string
		leaseExpiresAt time.Time
		retryCount     int
		currMaxRetries int
	)

	err = tx.QueryRowContext(ctx, `
		SELECT status, worker_id, lease_expires_at, retry_count, max_retries
		FROM event_idempotency
		WHERE event_id = $1
		FOR UPDATE
	`, eventID).Scan(&status, &existingWorker, &leaseExpiresAt, &retryCount, &currMaxRetries)
	if err != nil {
		return EventClaimResult{}, fmt.Errorf("lock existing event: %w", err)
	}

	now := time.Now()

	// 1. If already completed, safe to commit
	if status == string(StatusCompleted) {
		tx.Commit()
		return EventClaimResult{Claimed: false, AlreadyCompleted: true}, nil
	}

	// 2. If actively being processed with valid lease
	if status == string(StatusProcessing) && now.Before(leaseExpiresAt) {
		tx.Commit()
		return EventClaimResult{Claimed: false, InProgress: true}, nil
	}

	// 3. Expired lease or retryable failure
	if retryCount >= currMaxRetries {
		// Exhausted retries -> mark failed / dead-letter
		_, _ = tx.ExecContext(ctx, `
			UPDATE event_idempotency
			SET status = 'FAILED', last_error = 'max retries exceeded'
			WHERE event_id = $1
		`, eventID)
		tx.Commit()
		return EventClaimResult{Claimed: false, DeadLettered: true, RetryCount: retryCount}, nil
	}

	// Reclaim expired lease or retry failed state
	_, err = tx.ExecContext(ctx, `
		UPDATE event_idempotency
		SET status = 'PROCESSING',
			worker_id = $2,
			lease_expires_at = NOW() + $3::interval,
			retry_count = retry_count + 1
		WHERE event_id = $1
	`, eventID, workerID, fmt.Sprintf("%d seconds", int(leaseDuration.Seconds())))
	if err != nil {
		return EventClaimResult{}, fmt.Errorf("reclaim event lease: %w", err)
	}

	if err := tx.Commit(); err != nil {
		return EventClaimResult{}, fmt.Errorf("commit reclaim tx: %w", err)
	}

	return EventClaimResult{Claimed: true, RetryCount: retryCount + 1}, nil
}

func (s *PostgresEventStore) MarkCompleted(ctx context.Context, eventID string, workerID string) error {
	res, err := s.db.ExecContext(ctx, `
		UPDATE event_idempotency
		SET status = 'COMPLETED', completed_at = NOW(), last_error = NULL
		WHERE event_id = $1 AND worker_id = $2 AND status = 'PROCESSING'
	`, eventID, workerID)
	if err != nil {
		return err
	}
	rows, err := res.RowsAffected()
	if err != nil {
		return err
	}
	if rows == 0 {
		return ErrLeaseLost
	}
	return nil
}

func (s *PostgresEventStore) MarkFailed(ctx context.Context, eventID string, workerID string, errMsg string) error {
	res, err := s.db.ExecContext(ctx, `
		UPDATE event_idempotency
		SET status = 'FAILED', last_error = $3, lease_expires_at = NOW()
		WHERE event_id = $1 AND worker_id = $2 AND status = 'PROCESSING'
	`, eventID, workerID, errMsg)
	if err != nil {
		return err
	}
	rows, err := res.RowsAffected()
	if err != nil {
		return err
	}
	if rows == 0 {
		return ErrLeaseLost
	}
	return nil
}

func (s *PostgresEventStore) GetStatus(ctx context.Context, eventID string) (EventProcessingStatus, error) {
	var status string
	err := s.db.QueryRowContext(ctx, `
		SELECT status FROM event_idempotency WHERE event_id = $1
	`, eventID).Scan(&status)
	if err != nil {
		return "", err
	}
	return EventProcessingStatus(status), nil
}

func (s *PostgresEventStore) Delete(eventID string) error {
	_, err := s.db.Exec(`DELETE FROM event_idempotency WHERE event_id = $1`, eventID)
	return err
}

func (s *PostgresEventStore) Close() error {
	return s.db.Close()
}
