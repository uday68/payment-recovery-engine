package main

import "testing"

func TestRecoveryMetricsRecordsSuccessfulExecution(t *testing.T) {
	metrics := NewRecoveryMetrics()

	metrics.Record(ExecutionResult{
		Attempts:  2,
		Outcome:   "EXECUTED",
		Recovered: true,
	})

	snapshot := metrics.Snapshot()

	if snapshot.TotalExecutions != 1 {
		t.Fatalf(
			"expected 1 execution, got %d",
			snapshot.TotalExecutions,
		)
	}

	if snapshot.RecoveredExecutions != 1 {
		t.Fatalf(
			"expected 1 recovered execution, got %d",
			snapshot.RecoveredExecutions,
		)
	}

	if snapshot.TotalAttempts != 2 {
		t.Fatalf(
			"expected 2 attempts, got %d",
			snapshot.TotalAttempts,
		)
	}
}

func TestRecoveryMetricsRecordsFailedExecution(t *testing.T) {
	metrics := NewRecoveryMetrics()

	metrics.Record(ExecutionResult{
		Attempts:  3,
		Outcome:   "FAILED_PERMANENT",
		Recovered: false,
	})

	snapshot := metrics.Snapshot()

	if snapshot.TotalExecutions != 1 {
		t.Fatalf("expected 1 execution, got %d", snapshot.TotalExecutions)
	}

	if snapshot.RecoveredExecutions != 0 {
		t.Fatalf(
			"expected 0 recovered executions, got %d",
			snapshot.RecoveredExecutions,
		)
	}

	if snapshot.TotalAttempts != 3 {
		t.Fatalf(
			"expected 3 attempts, got %d",
			snapshot.TotalAttempts,
		)
	}
}

func TestRecoveryMetricsCalculatesRecoveryRate(t *testing.T) {
	metrics := NewRecoveryMetrics()

	metrics.Record(ExecutionResult{
		Attempts:  1,
		Outcome:   "EXECUTED",
		Recovered: true,
	})

	metrics.Record(ExecutionResult{
		Attempts:  2,
		Outcome:   "FAILED_PERMANENT",
		Recovered: false,
	})

	metrics.Record(ExecutionResult{
		Attempts:  3,
		Outcome:   "EXECUTOR_ERROR",
		Recovered: false,
	})

	snapshot := metrics.Snapshot()

	if snapshot.TotalExecutions != 3 {
		t.Fatalf("expected 3 executions, got %d", snapshot.TotalExecutions)
	}

	if snapshot.RecoveredExecutions != 1 {
		t.Fatalf(
			"expected 1 recovered execution, got %d",
			snapshot.RecoveredExecutions,
		)
	}

	if snapshot.FailedExecutions != 2 {
		t.Fatalf(
			"expected 2 failed executions, got %d",
			snapshot.FailedExecutions,
		)
	}

	expectedRate := 1.0 / 3.0

	if snapshot.RecoveryRate != expectedRate {
		t.Fatalf(
			"expected recovery rate %f, got %f",
			expectedRate,
			snapshot.RecoveryRate,
		)
	}
}

// func TestRecoveryMetricsTracksRecoveredRevenue(t *testing.T) {
// 	metrics := NewRecoveryMetrics()

// 	metrics.Record(ExecutionResult{
// 		FinalResult: GatewayResult{
// 			Status: "SUCCESS",
// 		},
// 		Attempts:  2,
// 		Outcome:   "EXECUTED",
// 		Recovered: true,
// 		Amount:    2500,
// 	})

// 	metrics.Record(ExecutionResult{
// 		FinalResult: GatewayResult{
// 			Status: "FAILED",
// 		},
// 		Attempts:  1,
// 		Outcome:   "FAILED_PERMANENT",
// 		Recovered: false,
// 		Amount:    1500,
// 	})

// 	snapshot := metrics.Snapshot()

//		if snapshot.RecoveredRevenue != 2500 {
//			t.Fatalf(
//				"expected recovered revenue 2500, got %f",
//				snapshot.RecoveredRevenue,
//			)
//		}
//	}
func TestRecoveryMetricsTracksOutcomes(t *testing.T) {
	metrics := NewRecoveryMetrics()

	metrics.Record(ExecutionResult{
		Attempts:  1,
		Outcome:   "EXECUTED",
		Recovered: true,
		Amount:    1000,
	})

	metrics.Record(ExecutionResult{
		Attempts:  2,
		Outcome:   "FAILED_RETRYABLE",
		Recovered: false,
		Amount:    2000,
	})

	metrics.Record(ExecutionResult{
		Attempts:  1,
		Outcome:   "FAILED_PERMANENT",
		Recovered: false,
		Amount:    3000,
	})

	metrics.Record(ExecutionResult{
		Attempts:  3,
		Outcome:   "EXECUTOR_ERROR",
		Recovered: false,
		Amount:    4000,
	})

	snapshot := metrics.Snapshot()

	if snapshot.RetryableFailures != 1 {
		t.Fatalf(
			"expected 1 retryable failure, got %d",
			snapshot.RetryableFailures,
		)
	}

	if snapshot.PermanentFailures != 1 {
		t.Fatalf(
			"expected 1 permanent failure, got %d",
			snapshot.PermanentFailures,
		)
	}

	if snapshot.ExecutorErrors != 1 {
		t.Fatalf(
			"expected 1 executor error, got %d",
			snapshot.ExecutorErrors,
		)
	}
}
func TestRecoveryMetricsSnapshotIsDeterministic(t *testing.T) {
	metrics := NewRecoveryMetrics()

	metrics.Record(ExecutionResult{
		Outcome:   "EXECUTED",
		Recovered: true,
		Attempts:  2,
		Amount:    5000,
	})

	metrics.Record(ExecutionResult{
		Outcome:   "FAILED_RETRYABLE",
		Recovered: false,
		Attempts:  3,
		Amount:    3000,
	})

	snapshot := metrics.Snapshot()

	if snapshot.TotalExecutions != 2 {
		t.Fatalf("expected 2 executions, got %d", snapshot.TotalExecutions)
	}

	if snapshot.RecoveredExecutions != 1 {
		t.Fatalf("expected 1 recovered execution, got %d", snapshot.RecoveredExecutions)
	}

	if snapshot.FailedExecutions != 1 {
		t.Fatalf("expected 1 failed execution, got %d", snapshot.FailedExecutions)
	}

	if snapshot.RetryableFailures != 1 {
		t.Fatalf("expected 1 retryable failure, got %d", snapshot.RetryableFailures)
	}

	if snapshot.TotalAttempts != 5 {
		t.Fatalf("expected 5 total attempts, got %d", snapshot.TotalAttempts)
	}

	if snapshot.RecoveredRevenue != 5000 {
		t.Fatalf("expected recovered revenue 5000, got %f", snapshot.RecoveredRevenue)
	}

	expectedRecoveryRate := 0.5
	if snapshot.RecoveryRate != expectedRecoveryRate {
		t.Fatalf(
			"expected recovery rate %f, got %f",
			expectedRecoveryRate,
			snapshot.RecoveryRate,
		)
	}
}
func TestRecoveryMetricsTracksRecoveredRevenue(t *testing.T) {
	metrics := NewRecoveryMetrics()

	metrics.Record(ExecutionResult{
		Recovered: true,
		Attempts:  1,
		Amount:    5000,
	})

	metrics.Record(ExecutionResult{
		Recovered: true,
		Attempts:  2,
		Amount:    3000,
	})

	metrics.Record(ExecutionResult{
		Recovered: false,
		Attempts:  3,
		Amount:    2000,
	})

	snapshot := metrics.Snapshot()

	if snapshot.TotalExecutions != 3 {
		t.Fatalf(
			"expected 3 executions, got %d",
			snapshot.TotalExecutions,
		)
	}

	if snapshot.RecoveredExecutions != 2 {
		t.Fatalf(
			"expected 2 recovered executions, got %d",
			snapshot.RecoveredExecutions,
		)
	}

	if snapshot.TotalAttempts != 6 {
		t.Fatalf(
			"expected 6 total attempts, got %d",
			snapshot.TotalAttempts,
		)
	}

	if snapshot.RecoveredRevenue != 8000 {
		t.Fatalf(
			"expected recovered revenue 8000, got %f",
			snapshot.RecoveredRevenue,
		)
	}
}
