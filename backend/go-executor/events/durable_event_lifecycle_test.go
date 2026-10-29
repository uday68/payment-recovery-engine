package events

import (
	"context"
	"errors"
	"fmt"
	"sync"
	"testing"
	"time"
)

type failingDecisioner struct {
	shouldFail bool
}

func (d *failingDecisioner) Decide(event PaymentFailedEvent) (DecisionResult, error) {
	if d.shouldFail {
		return DecisionResult{}, errors.New("decision service downstream timeout")
	}
	return DecisionResult{
		PaymentID: event.PaymentID,
		Action:    "RETRY_NOW",
	}, nil
}

type failingExecutor struct {
	shouldFail bool
	execCount  int
	mu         sync.Mutex
}

func (e *failingExecutor) Execute(command RecoveryCommand) (ExecutionResult, error) {
	e.mu.Lock()
	defer e.mu.Unlock()
	e.execCount++
	if e.shouldFail {
		return ExecutionResult{}, errors.New("payment gateway network connection reset")
	}
	return ExecutionResult{
		PaymentID: command.PaymentID,
		Recovered: true,
		Outcome:   "EXECUTED",
		Amount:    command.Amount,
	}, nil
}

// 1. Duplicate events: second delivery of already-completed event returns AlreadyCompleted without re-executing
func TestDurableEventStore_DuplicateEventSuppression(t *testing.T) {
	store := NewEventStore()
	decisioner := &failingDecisioner{}
	executor := &failingExecutor{}
	flow := NewRecoveryFlow(store, decisioner, executor)

	event := PaymentFailedEvent{
		EventID:   "evt-dup-001",
		PaymentID: "pay-dup-001",
		Amount:    1000,
	}

	// First execution succeeds
	res1, err := flow.Process(event)
	if err != nil {
		t.Fatalf("first process failed: %v", err)
	}
	if !res1.Execution.Recovered {
		t.Fatal("expected first execution to succeed")
	}
	if executor.execCount != 1 {
		t.Fatalf("expected 1 execution, got %d", executor.execCount)
	}

	// Redelivery of duplicate event
	res2, err := flow.Process(event)
	if err != nil {
		t.Fatalf("duplicate event process returned error: %v", err)
	}
	if !res2.AlreadyCompleted {
		t.Fatal("expected duplicate event to be marked AlreadyCompleted")
	}
	if executor.execCount != 1 {
		t.Fatalf("expected executor count to remain 1, got %d", executor.execCount)
	}
}

// 2. Concurrent workers: two workers attempt to claim the same event concurrently; only one gets the lease
func TestDurableEventStore_ConcurrentClaimContention(t *testing.T) {
	store := NewEventStore()
	eventID := "evt-concurrent-lease-001"
	ctx := context.Background()

	const numWorkers = 10
	results := make(chan EventClaimResult, numWorkers)
	var wg sync.WaitGroup

	for i := 0; i < numWorkers; i++ {
		wg.Add(1)
		workerID := fmt.Sprintf("worker-%d", i)
		go func(wID string) {
			defer wg.Done()
			res, err := store.ClaimOrRenew(ctx, eventID, wID, 10*time.Second, 3)
			if err != nil {
				t.Errorf("claim error: %v", err)
				return
			}
			results <- res
		}(workerID)
	}

	wg.Wait()
	close(results)

	claimedCount := 0
	inProgressCount := 0

	for res := range results {
		if res.Claimed {
			claimedCount++
		}
		if res.InProgress {
			inProgressCount++
		}
	}

	if claimedCount != 1 {
		t.Fatalf("expected exactly 1 worker to claim lease, got %d", claimedCount)
	}
	if inProgressCount != numWorkers-1 {
		t.Fatalf("expected %d workers to observe InProgress, got %d", numWorkers-1, inProgressCount)
	}
}

// 3. Failure after initial claim: execution fails, row transitions to FAILED and lease is cleared for retry
func TestDurableEventStore_FailureAfterClaim_TransitionsToFailed(t *testing.T) {
	store := NewEventStore()
	decisioner := &failingDecisioner{}
	executor := &failingExecutor{shouldFail: true}
	flow := NewRecoveryFlow(store, decisioner, executor)

	event := PaymentFailedEvent{
		EventID:   "evt-fail-claim-001",
		PaymentID: "pay-fail-001",
	}

	_, err := flow.Process(event)
	if err == nil {
		t.Fatal("expected flow to return error on execution failure")
	}

	status, err := store.GetStatus(context.Background(), event.EventID)
	if err != nil {
		t.Fatalf("get status failed: %v", err)
	}
	if status != StatusFailed {
		t.Fatalf("expected status FAILED, got %s", status)
	}
}

// 4. Retry after recoverable failure: subsequent worker claims and completes
func TestDurableEventStore_RetryAfterRecoverableFailure(t *testing.T) {
	store := NewEventStore()
	decisioner := &failingDecisioner{}
	executor := &failingExecutor{shouldFail: true}
	flow1 := NewRecoveryFlow(store, decisioner, executor)
	flow1.SetWorkerID("worker-alpha")

	event := PaymentFailedEvent{
		EventID:   "evt-retry-001",
		PaymentID: "pay-retry-001",
	}

	// First attempt fails
	_, err := flow1.Process(event)
	if err == nil {
		t.Fatal("expected first attempt to fail")
	}

	// Fix downstream failure
	executor.mu.Lock()
	executor.shouldFail = false
	executor.mu.Unlock()

	flow2 := NewRecoveryFlow(store, decisioner, executor)
	flow2.SetWorkerID("worker-beta")

	// Retry attempt succeeds
	res, err := flow2.Process(event)
	if err != nil {
		t.Fatalf("retry attempt failed: %v", err)
	}
	if !res.Execution.Recovered {
		t.Fatal("expected retry execution to succeed")
	}

	status, err := store.GetStatus(context.Background(), event.EventID)
	if err != nil {
		t.Fatalf("get status failed: %v", err)
	}
	if status != StatusCompleted {
		t.Fatalf("expected final status COMPLETED, got %s", status)
	}
}

// 5. Recovery of expired work leases: abandoned worker lease can be reclaimed by second worker
func TestDurableEventStore_RecoveryOfExpiredLeases(t *testing.T) {
	store := NewEventStore()
	ctx := context.Background()
	eventID := "evt-abandoned-lease-001"

	// Worker 1 claims with very short lease (10ms) and crashes/abandons
	claim1, err := store.ClaimOrRenew(ctx, eventID, "worker-crashed", 10*time.Millisecond, 3)
	if err != nil || !claim1.Claimed {
		t.Fatalf("worker 1 initial claim failed: %v", err)
	}

	// Immediately, Worker 2 observes InProgress
	claim2, err := store.ClaimOrRenew(ctx, eventID, "worker-healthy", 10*time.Second, 3)
	if err != nil {
		t.Fatalf("worker 2 check failed: %v", err)
	}
	if !claim2.InProgress {
		t.Fatal("expected worker 2 to see in-progress while lease is active")
	}

	// Wait for lease to expire
	time.Sleep(20 * time.Millisecond)

	// Worker 2 should now successfully reclaim the expired lease
	claim3, err := store.ClaimOrRenew(ctx, eventID, "worker-healthy", 10*time.Second, 3)
	if err != nil {
		t.Fatalf("worker 2 reclaim failed: %v", err)
	}
	if !claim3.Claimed {
		t.Fatal("expected worker 2 to successfully reclaim expired lease")
	}
	if claim3.RetryCount != 1 {
		t.Fatalf("expected retry count 1, got %d", claim3.RetryCount)
	}

	// Worker 2 finishes work
	err = store.MarkCompleted(ctx, eventID, "worker-healthy")
	if err != nil {
		t.Fatalf("worker 2 mark completed failed: %v", err)
	}

	status, _ := store.GetStatus(ctx, eventID)
	if status != StatusCompleted {
		t.Fatalf("expected status COMPLETED, got %s", status)
	}
}

// 6. Failure to persist completion: lease loss causes MarkCompleted to fail
func TestDurableEventStore_FailureToPersistCompletion_WhenLeaseLost(t *testing.T) {
	store := NewEventStore()
	ctx := context.Background()
	eventID := "evt-lease-loss-001"

	// Worker 1 claims with 5ms lease
	_, _ = store.ClaimOrRenew(ctx, eventID, "worker-1", 5*time.Millisecond, 3)

	time.Sleep(15 * time.Millisecond)

	// Worker 2 reclaims
	_, _ = store.ClaimOrRenew(ctx, eventID, "worker-2", 10*time.Second, 3)

	// Worker 1 attempts to mark completed late (zombie worker)
	err := store.MarkCompleted(ctx, eventID, "worker-1")
	if !errors.Is(err, ErrLeaseLost) {
		t.Fatalf("expected ErrLeaseLost for zombie worker, got %v", err)
	}
}

// 7. Exhaustion of bounded retries and dead-letter behavior
func TestDurableEventStore_ExhaustedRetries_DeadLetterBehavior(t *testing.T) {
	store := NewEventStore()
	decisioner := &failingDecisioner{shouldFail: true}
	executor := &failingExecutor{}
	flow := NewRecoveryFlow(store, decisioner, executor)
	flow.SetMaxRetries(2)

	event := PaymentFailedEvent{
		EventID:   "evt-exhaust-001",
		PaymentID: "pay-exhaust-001",
	}

	// Attempt 1 (initial attempt) -> fails
	_, err := flow.Process(event)
	if err == nil {
		t.Fatal("attempt 1 should fail")
	}

	// Attempt 2 (retry 1) -> fails
	_, err = flow.Process(event)
	if err == nil {
		t.Fatal("attempt 2 should fail")
	}

	// Attempt 3 (retry 2) -> fails
	_, err = flow.Process(event)
	if err == nil {
		t.Fatal("attempt 3 should fail")
	}

	// Attempt 4 (retries exhausted -> DeadLettered)
	res, err := flow.Process(event)
	if err != nil {
		t.Fatalf("expected dead-letter path to return nil error to allow offset commit, got %v", err)
	}
	if !res.DeadLettered {
		t.Fatal("expected event to be marked DeadLettered")
	}
}

// 8. Kafka Consumer offset commit semantics: commits on complete or dead-letter, does NOT commit on failure/in-progress
func TestDurableEventStore_KafkaConsumerOffsetCommitSemantics(t *testing.T) {
	store := NewEventStore()
	decisioner := &failingDecisioner{shouldFail: true}
	executor := &failingExecutor{}
	flow := NewRecoveryFlow(store, decisioner, executor)
	handler := NewRecoveryFlowHandler(flow)

	event := PaymentFailedEvent{
		EventID:   "evt-kafka-offset-001",
		PaymentID: "pay-kafka-001",
	}

	// Handler returns error on failure -> KafkaConsumer DOES NOT commit
	err := handler.Handle(event)
	if err == nil {
		t.Fatal("expected handler to return error to prevent Kafka offset commit")
	}

	// Now fix decisioner and retry
	decisioner.shouldFail = false
	err = handler.Handle(event)
	if err != nil {
		t.Fatalf("expected retry to succeed and return nil for offset commit, got %v", err)
	}

	// Redelivery returns nil so duplicate message offset is safely committed
	err = handler.Handle(event)
	if err != nil {
		t.Fatalf("expected duplicate event to return nil for offset commit, got %v", err)
	}
}
