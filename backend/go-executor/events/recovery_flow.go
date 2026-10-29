package events

import (
	"context"
	"fmt"
	"time"
)

type RecoveryFlowResult struct {
	Command          RecoveryCommand
	Execution        ExecutionResult
	AlreadyCompleted bool
	DeadLettered     bool
}

type RecoveryFlow struct {
	eventStore    EventStoreClaimer
	decisioner    RecoveryDecisioner
	executor      CommandExecutor
	workerID      string
	leaseDuration time.Duration
	maxRetries    int
}

func NewRecoveryFlow(
	eventStore EventStoreClaimer,
	decisioner RecoveryDecisioner,
	executor CommandExecutor,
) *RecoveryFlow {
	return &RecoveryFlow{
		eventStore:    eventStore,
		decisioner:    decisioner,
		executor:      executor,
		workerID:      fmt.Sprintf("worker-%d", time.Now().UnixNano()),
		leaseDuration: 30 * time.Second,
		maxRetries:    3,
	}
}

func (f *RecoveryFlow) SetWorkerID(id string) {
	f.workerID = id
}

func (f *RecoveryFlow) SetLeaseDuration(d time.Duration) {
	f.leaseDuration = d
}

func (f *RecoveryFlow) SetMaxRetries(m int) {
	f.maxRetries = m
}

func (f *RecoveryFlow) Process(
	event PaymentFailedEvent,
) (RecoveryFlowResult, error) {
	ctx := context.Background()

	// Check if event store supports durable lease state transitions
	if durableStore, ok := f.eventStore.(DurableEventStore); ok {
		claimRes, err := durableStore.ClaimOrRenew(ctx, event.EventID, f.workerID, f.leaseDuration, f.maxRetries)
		if err != nil {
			return RecoveryFlowResult{}, fmt.Errorf("claim or renew event %s: %w", event.EventID, err)
		}

		if claimRes.AlreadyCompleted {
			return RecoveryFlowResult{AlreadyCompleted: true}, nil
		}

		if claimRes.InProgress {
			return RecoveryFlowResult{}, ErrEventInProgress
		}

		if claimRes.DeadLettered {
			return RecoveryFlowResult{DeadLettered: true}, nil
		}

		processor := NewDecisionRecoveryProcessor(f.decisioner)
		command, err := processor.Process(event)
		if err != nil {
			_ = durableStore.MarkFailed(ctx, event.EventID, f.workerID, fmt.Sprintf("decision failed: %v", err))
			return RecoveryFlowResult{}, err
		}

		executionWorker := NewRecoveryExecutionWorker(f.executor)
		execution, err := executionWorker.Execute(command)
		if err != nil {
			_ = durableStore.MarkFailed(ctx, event.EventID, f.workerID, fmt.Sprintf("execution failed: %v", err))
			return RecoveryFlowResult{}, err
		}

		if err := durableStore.MarkCompleted(ctx, event.EventID, f.workerID); err != nil {
			return RecoveryFlowResult{}, fmt.Errorf("failed to durably record completion: %w", err)
		}

		return RecoveryFlowResult{
			Command:   command,
			Execution: execution,
		}, nil
	}

	// Legacy fallback for simple EventStoreClaimer
	claimed, err := f.eventStore.Claim(event.EventID)
	if err != nil {
		return RecoveryFlowResult{}, err
	}

	if !claimed {
		return RecoveryFlowResult{AlreadyCompleted: true}, nil
	}

	processor := NewDecisionRecoveryProcessor(f.decisioner)
	command, err := processor.Process(event)
	if err != nil {
		return RecoveryFlowResult{}, err
	}

	executionWorker := NewRecoveryExecutionWorker(f.executor)
	execution, err := executionWorker.Execute(command)
	if err != nil {
		return RecoveryFlowResult{}, err
	}

	return RecoveryFlowResult{
		Command:   command,
		Execution: execution,
	}, nil
}
