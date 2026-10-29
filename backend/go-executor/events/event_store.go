package events

import (
	"context"
	"errors"
	"sync"
	"time"
)

var (
	ErrEventInProgress    = errors.New("event is currently being processed under an active lease")
	ErrMaxRetriesExceeded = errors.New("event processing exceeded maximum allowed retries")
	ErrLeaseLost          = errors.New("worker lease expired or acquired by another worker")
	ErrEventAlreadyDone   = errors.New("event has already completed processing")
)

type EventProcessingStatus string

const (
	StatusProcessing EventProcessingStatus = "PROCESSING"
	StatusCompleted  EventProcessingStatus = "COMPLETED"
	StatusFailed     EventProcessingStatus = "FAILED"
)

type EventClaimResult struct {
	Claimed          bool
	AlreadyCompleted bool
	InProgress       bool
	DeadLettered     bool
	RetryCount       int
}

type EventStoreClaimer interface {
	Claim(eventID string) (bool, error)
}

type DurableEventStore interface {
	EventStoreClaimer
	ClaimOrRenew(ctx context.Context, eventID string, workerID string, leaseDuration time.Duration, maxRetries int) (EventClaimResult, error)
	MarkCompleted(ctx context.Context, eventID string, workerID string) error
	MarkFailed(ctx context.Context, eventID string, workerID string, errMsg string) error
	GetStatus(ctx context.Context, eventID string) (EventProcessingStatus, error)
}

type eventRecord struct {
	status         EventProcessingStatus
	workerID       string
	leaseExpiresAt time.Time
	retryCount     int
	maxRetries     int
	lastError      string
	claimedAt      time.Time
	completedAt    time.Time
}

type EventStore struct {
	mu      sync.Mutex
	records map[string]*eventRecord
}

func NewEventStore() *EventStore {
	return &EventStore{
		records: make(map[string]*eventRecord),
	}
}

func (s *EventStore) Claim(eventID string) (bool, error) {
	res, err := s.ClaimOrRenew(context.Background(), eventID, "default-worker", 30*time.Second, 3)
	if err != nil {
		return false, err
	}
	return res.Claimed, nil
}

func (s *EventStore) ClaimOrRenew(
	ctx context.Context,
	eventID string,
	workerID string,
	leaseDuration time.Duration,
	maxRetries int,
) (EventClaimResult, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	now := time.Now()
	rec, exists := s.records[eventID]
	if !exists {
		s.records[eventID] = &eventRecord{
			status:         StatusProcessing,
			workerID:       workerID,
			leaseExpiresAt: now.Add(leaseDuration),
			retryCount:     0,
			maxRetries:     maxRetries,
			claimedAt:      now,
		}
		return EventClaimResult{Claimed: true, RetryCount: 0}, nil
	}

	if rec.status == StatusCompleted {
		return EventClaimResult{Claimed: false, AlreadyCompleted: true}, nil
	}

	if rec.status == StatusProcessing {
		if now.Before(rec.leaseExpiresAt) {
			// Active lease is still valid and held; cannot be re-claimed while in-progress
			return EventClaimResult{Claimed: false, InProgress: true}, nil
		}

		// Lease expired! Worker abandoned or crashed; eligible for reclaim
		if rec.retryCount >= rec.maxRetries {
			rec.status = StatusFailed
			rec.lastError = "max retries exceeded on lease timeout"
			return EventClaimResult{Claimed: false, DeadLettered: true, RetryCount: rec.retryCount}, nil
		}

		rec.status = StatusProcessing
		rec.workerID = workerID
		rec.leaseExpiresAt = now.Add(leaseDuration)
		rec.retryCount++
		return EventClaimResult{Claimed: true, RetryCount: rec.retryCount}, nil
	}

	if rec.status == StatusFailed {
		if rec.retryCount >= rec.maxRetries {
			return EventClaimResult{Claimed: false, DeadLettered: true, RetryCount: rec.retryCount}, nil
		}
		rec.status = StatusProcessing
		rec.workerID = workerID
		rec.leaseExpiresAt = now.Add(leaseDuration)
		rec.retryCount++
		return EventClaimResult{Claimed: true, RetryCount: rec.retryCount}, nil
	}

	return EventClaimResult{Claimed: false}, nil
}

func (s *EventStore) MarkCompleted(ctx context.Context, eventID string, workerID string) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	rec, exists := s.records[eventID]
	if !exists {
		return errors.New("event record not found")
	}

	if rec.status == StatusCompleted {
		return nil
	}

	if rec.status == StatusProcessing && rec.workerID == workerID {
		rec.status = StatusCompleted
		rec.completedAt = time.Now()
		rec.lastError = ""
		return nil
	}

	return ErrLeaseLost
}

func (s *EventStore) MarkFailed(ctx context.Context, eventID string, workerID string, errMsg string) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	rec, exists := s.records[eventID]
	if !exists {
		return errors.New("event record not found")
	}

	if rec.status == StatusCompleted {
		return ErrEventAlreadyDone
	}

	if rec.workerID == workerID {
		rec.status = StatusFailed
		rec.lastError = errMsg
		rec.leaseExpiresAt = time.Now() // Release lease immediately so it can be retried
		return nil
	}

	return ErrLeaseLost
}

func (s *EventStore) GetStatus(ctx context.Context, eventID string) (EventProcessingStatus, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	rec, exists := s.records[eventID]
	if !exists {
		return "", errors.New("event record not found")
	}
	return rec.status, nil
}
