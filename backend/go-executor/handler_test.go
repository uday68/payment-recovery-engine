package main

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

type countingExecutor struct {
	calls int
}

func (e *countingExecutor) ExecuteWithMetadata(command RecoveryCommand) ExecutionResult {
	e.calls++

	return ExecutionResult{
		Recovered: true,
		Attempts:  1,
		Outcome:   "EXECUTED",
		Retryable: false,
		Amount:    command.Amount,
	}
}
func TestExecuteRecovery(t *testing.T) {
	body := `{
		"command_id": "cmd-123",
		"payment_id": "payment-123",
		"action": "RETRY_LATER",
		"amount": 5000
	}`

	req := httptest.NewRequest(
		http.MethodPost,
		"/v1/recovery/execute",
		strings.NewReader(body),
	)

	req.Header.Set("Content-Type", "application/json")

	rec := httptest.NewRecorder()

	handler := executeRecoveryHandler()

	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d", rec.Code)
	}

	response := rec.Body.String()

	if !strings.Contains(response, `"command_id":"cmd-123"`) {
		t.Fatalf("response missing command_id: %s", response)
	}

	if !strings.Contains(response, `"payment_id":"payment-123"`) {
		t.Fatalf("response missing payment_id: %s", response)
	}

	if !strings.Contains(response, `"status":"EXECUTED"`) {
		t.Fatalf("response missing EXECUTED status: %s", response)
	}
}
func TestExecuteRecoveryIsIdempotent(t *testing.T) {
	body := `{
		"command_id": "cmd-idempotent",
		"payment_id": "payment-idempotent",
		"action": "RETRY_LATER",
		"amount": 5000
	}`

	handler := executeRecoveryHandler()

	// First request
	req1 := httptest.NewRequest(
		http.MethodPost,
		"/v1/recovery/execute",
		strings.NewReader(body),
	)

	rec1 := httptest.NewRecorder()

	handler.ServeHTTP(rec1, req1)

	if rec1.Code != http.StatusOK {
		t.Fatalf("first request: expected 200, got %d", rec1.Code)
	}

	if !strings.Contains(rec1.Body.String(), `"status":"EXECUTED"`) {
		t.Fatalf("first request should execute: %s", rec1.Body.String())
	}

	// Same command again
	req2 := httptest.NewRequest(
		http.MethodPost,
		"/v1/recovery/execute",
		strings.NewReader(body),
	)

	rec2 := httptest.NewRecorder()

	handler.ServeHTTP(rec2, req2)

	if rec2.Code != http.StatusOK {
		t.Fatalf("second request: expected 200, got %d", rec2.Code)
	}

	if !strings.Contains(rec2.Body.String(), `"status":"DUPLICATE"`) {
		t.Fatalf("second request should be duplicate: %s", rec2.Body.String())
	}
}
func TestExecuteRecoveryReturnsGatewayOutcome(t *testing.T) {
	handler := executeRecoveryHandler()

	body := `{
		"command_id": "gateway-outcome-001",
		"payment_id": "payment-gateway-outcome-001",
		"action": "RETRY_LATER",
		"amount": 5000
	}`

	req := httptest.NewRequest(
		http.MethodPost,
		"/v1/recovery/execute",
		strings.NewReader(body),
	)

	rec := httptest.NewRecorder()

	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", rec.Code)
	}

	response := rec.Body.String()

	if !strings.Contains(response, `"status"`) {
		t.Fatalf("response missing status: %s", response)
	}

	if !strings.Contains(response, `"recovered"`) {
		t.Fatalf("response missing recovered field: %s", response)
	}
}
func TestExecuteRecoveryReturnsGatewayFailure(t *testing.T) {
	gateway := &FakeGateway{
		result: GatewayResult{
			PaymentID: "payment-gateway-failure-001",
			Action:    "RETRY_LATER",
			Status:    "FAILED",
			ErrorCode: "BANK_TIMEOUT",
			Retryable: true,
		},
	}

	handler := executeRecoveryHandlerWithDependencies(
		NewCommandStore(),
		gateway,
	)

	body := `{
		"command_id": "gateway-failure-001",
		"payment_id": "payment-gateway-failure-001",
		"action": "RETRY_LATER",
		"amount": 5000
	}`

	req := httptest.NewRequest(
		http.MethodPost,
		"/v1/recovery/execute",
		strings.NewReader(body),
	)

	rec := httptest.NewRecorder()

	handler.ServeHTTP(rec, req)

	response := rec.Body.String()

	if !strings.Contains(response, `"status":"FAILED"`) {
		t.Fatalf("expected FAILED status: %s", response)
	}

	if !strings.Contains(response, `"recovered":false`) {
		t.Fatalf("expected recovered=false: %s", response)
	}
}

func TestExecuteRecoveryPermanentFailureStopsRetry(t *testing.T) {
	store := NewCommandStore()

	gateway := &FakeGateway{
		result: GatewayResult{
			PaymentID: "payment-permanent",
			Action:    "RETRY_NOW",
			Status:    "FAILED",
			ErrorCode: "CARD_EXPIRED",
		},
	}

	handler := executeRecoveryHandlerWithDependencies(store, gateway)

	body := `{
		"command_id": "cmd-permanent-001",
		"payment_id": "payment-permanent",
		"action": "RETRY_NOW",
		"amount": 1000
	}`

	req := httptest.NewRequest(
		http.MethodPost,
		"/v1/recovery/execute",
		strings.NewReader(body),
	)

	rec := httptest.NewRecorder()

	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d", rec.Code)
	}

	var response RecoveryResponse

	if err := json.NewDecoder(rec.Body).Decode(&response); err != nil {
		t.Fatal(err)
	}

	if response.Status != "FAILED" {
		t.Fatalf("expected FAILED, got %s", response.Status)
	}

	if response.Recovered {
		t.Fatal("permanent failure must not be recovered")
	}
}
func TestExecuteRecoveryReturnsRetryableForTransientFailure(t *testing.T) {
	store := NewCommandStore()

	gateway := &FakeGateway{
		result: GatewayResult{
			PaymentID: "payment-transient",
			Action:    "RETRY_NOW",
			Status:    "FAILED",
			ErrorCode: "GATEWAY_TIMEOUT",
		},
	}

	handler := executeRecoveryHandlerWithDependencies(store, gateway)

	body := `{
		"command_id": "cmd-transient-001",
		"payment_id": "payment-transient",
		"action": "RETRY_NOW",
		"amount": 1000
	}`

	req := httptest.NewRequest(
		http.MethodPost,
		"/v1/recovery/execute",
		strings.NewReader(body),
	)

	rec := httptest.NewRecorder()

	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d", rec.Code)
	}

	var response RecoveryResponse

	if err := json.NewDecoder(rec.Body).Decode(&response); err != nil {
		t.Fatal(err)
	}

	if response.Status != "FAILED" {
		t.Fatalf("expected FAILED, got %s", response.Status)
	}

	if !response.Retryable {
		t.Fatal("expected transient failure to be retryable")
	}
}
func TestMetricsHandlerReturnsSnapshot(t *testing.T) {
	metrics := NewRecoveryMetrics()

	metrics.Record(ExecutionResult{
		Outcome:   "EXECUTED",
		Recovered: true,
		Attempts:  2,
		Amount:    5000,
	})

	handler := metricsHandler(metrics)

	req := httptest.NewRequest(http.MethodGet, "/metrics", nil)
	recorder := httptest.NewRecorder()

	handler.ServeHTTP(recorder, req)

	if recorder.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d", recorder.Code)
	}

	var response RecoveryMetricsSnapshot

	if err := json.NewDecoder(recorder.Body).Decode(&response); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}

	if response.TotalExecutions != 1 {
		t.Fatalf(
			"expected 1 execution, got %d",
			response.TotalExecutions,
		)
	}

	if response.RecoveredRevenue != 5000 {
		t.Fatalf(
			"expected recovered revenue 5000, got %f",
			response.RecoveredRevenue,
		)
	}
}
func TestServerExposesMetricsEndpoint(t *testing.T) {
	metrics := NewRecoveryMetrics()

	mux := http.NewServeMux()
	mux.Handle("/metrics", metricsHandler(metrics))

	req := httptest.NewRequest(http.MethodGet, "/metrics", nil)
	recorder := httptest.NewRecorder()

	mux.ServeHTTP(recorder, req)

	if recorder.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d", recorder.Code)
	}

	if recorder.Header().Get("Content-Type") != "application/json" {
		t.Fatalf(
			"expected application/json, got %s",
			recorder.Header().Get("Content-Type"),
		)
	}
}
func TestServerMetricsReflectExecution(t *testing.T) {
	store := NewCommandStore()
	metrics := NewRecoveryMetrics()

	gateway := &FakeGateway{
		result: GatewayResult{
			PaymentID: "payment-123",
			Action:    "RETRY_NOW",
			Status:    "SUCCESS",
		},
	}

	executor := NewRetryExecutorWithBackoff(
		gateway,
		1,
		NewBackoffPolicy(1),
		func(time.Duration) {},
	)

	mux := http.NewServeMux()

	mux.Handle(
		"/v1/recovery/execute",
		executeRecoveryHandlerWithExecutorAndMetrics(
			store,
			executor,
			metrics,
		),
	)

	mux.Handle(
		"/metrics",
		metricsHandler(metrics),
	)

	body := `{
        "command_id": "metrics-command-123",
        "payment_id": "payment-123",
        "action": "RETRY_NOW",
        "amount": 5000
    }`

	executeReq := httptest.NewRequest(
		http.MethodPost,
		"/v1/recovery/execute",
		strings.NewReader(body),
	)

	executeRecorder := httptest.NewRecorder()

	mux.ServeHTTP(executeRecorder, executeReq)

	if executeRecorder.Code != http.StatusOK {
		t.Fatalf(
			"expected execution status 200, got %d",
			executeRecorder.Code,
		)
	}

	metricsReq := httptest.NewRequest(
		http.MethodGet,
		"/metrics",
		nil,
	)

	metricsRecorder := httptest.NewRecorder()

	mux.ServeHTTP(metricsRecorder, metricsReq)

	if metricsRecorder.Code != http.StatusOK {
		t.Fatalf(
			"expected metrics status 200, got %d",
			metricsRecorder.Code,
		)
	}

	var snapshot RecoveryMetricsSnapshot

	if err := json.NewDecoder(metricsRecorder.Body).Decode(&snapshot); err != nil {
		t.Fatalf("failed to decode metrics: %v", err)
	}

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

	if snapshot.RecoveredRevenue != 5000 {
		t.Fatalf(
			"expected recovered revenue 5000, got %f",
			snapshot.RecoveredRevenue,
		)
	}
}

func TestExecuteRecoveryHandlerWithStoreAndMetricsExists(t *testing.T) {
	store := NewCommandStore()
	metrics := NewRecoveryMetrics()

	handler := executeRecoveryHandlerWithStoreAndMetrics(
		store,
		metrics,
	)

	if handler == nil {
		t.Fatal("expected handler, got nil")
	}
}
func TestRecoveryCommandContract(t *testing.T) {
	payload := `{
        "command_id": "cmd-contract-001",
        "payment_id": "pay-contract-001",
        "action": "RETRY_NOW",
        "amount": 5000
    }`

	var command RecoveryCommand

	err := json.Unmarshal([]byte(payload), &command)
	if err != nil {
		t.Fatalf("failed to decode command: %v", err)
	}

	if command.CommandID != "cmd-contract-001" {
		t.Fatalf("unexpected command_id: %s", command.CommandID)
	}

	if command.PaymentID != "pay-contract-001" {
		t.Fatalf("unexpected payment_id: %s", command.PaymentID)
	}

	if command.Action != "RETRY_NOW" {
		t.Fatalf("unexpected action: %s", command.Action)
	}

	if command.Amount != 5000 {
		t.Fatalf("unexpected amount: %v", command.Amount)
	}
}
func TestRecoveryCommandValidation(t *testing.T) {
	tests := []struct {
		name    string
		command RecoveryCommand
		wantErr bool
	}{
		{
			name: "valid command",
			command: RecoveryCommand{
				CommandID: "cmd-valid-001",
				PaymentID: "pay-valid-001",
				Action:    "RETRY_NOW",
				Amount:    5000,
			},
			wantErr: false,
		},
		{
			name: "missing command id",
			command: RecoveryCommand{
				PaymentID: "pay-valid-001",
				Action:    "RETRY_NOW",
				Amount:    5000,
			},
			wantErr: true,
		},
		{
			name: "missing payment id",
			command: RecoveryCommand{
				CommandID: "cmd-valid-001",
				Action:    "RETRY_NOW",
				Amount:    5000,
			},
			wantErr: true,
		},
		{
			name: "invalid action",
			command: RecoveryCommand{
				CommandID: "cmd-valid-001",
				PaymentID: "pay-valid-001",
				Action:    "STEAL_MONEY",
				Amount:    5000,
			},
			wantErr: true,
		},
		{
			name: "zero amount",
			command: RecoveryCommand{
				CommandID: "cmd-valid-001",
				PaymentID: "pay-valid-001",
				Action:    "RETRY_NOW",
				Amount:    0,
			},
			wantErr: true,
		},
		{
			name: "negative amount",
			command: RecoveryCommand{
				CommandID: "cmd-valid-001",
				PaymentID: "pay-valid-001",
				Action:    "RETRY_NOW",
				Amount:    -100,
			},
			wantErr: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := validateRecoveryCommand(tt.command)

			if (err != nil) != tt.wantErr {
				t.Fatalf(
					"validateRecoveryCommand() error = %v, wantErr = %v",
					err,
					tt.wantErr,
				)
			}
		})
	}
}
func TestRecoveryHandlerRejectsInvalidCommand(t *testing.T) {
	payload := `{
		"command_id": "cmd-invalid-001",
		"payment_id": "pay-invalid-001",
		"action": "INVALID_ACTION",
		"amount": 5000
	}`

	req := httptest.NewRequest(
		http.MethodPost,
		"/v1/recovery/execute",
		strings.NewReader(payload),
	)
	req.Header.Set("Content-Type", "application/json")

	rec := httptest.NewRecorder()

	handler := executeRecoveryHandlerWithExecutor(
		nil,
		nil,
	)

	handler.ServeHTTP(rec, req)

	if rec.Code == http.StatusOK {
		t.Fatalf("expected invalid command to be rejected, got status %d", rec.Code)
	}
}
func TestRecoveryHandlerDoesNotExecuteDuplicateCommand(t *testing.T) {
	store := NewCommandStore()

	executor := &countingExecutor{}

	payload := `{
		"command_id": "cmd-duplicate-001",
		"payment_id": "pay-duplicate-001",
		"action": "RETRY_NOW",
		"amount": 5000
	}`

	sendRequest := func() *httptest.ResponseRecorder {
		req := httptest.NewRequest(
			http.MethodPost,
			"/v1/recovery/execute",
			strings.NewReader(payload),
		)

		req.Header.Set("Content-Type", "application/json")

		rec := httptest.NewRecorder()

		handler := executeRecoveryHandlerWithExecutor(store, executor)
		handler.ServeHTTP(rec, req)

		return rec
	}

	first := sendRequest()

	if first.Code != http.StatusOK {
		t.Fatalf("first request failed: status=%d body=%s", first.Code, first.Body.String())
	}

	second := sendRequest()

	if second.Code != http.StatusOK {
		t.Fatalf("duplicate request failed: status=%d body=%s", second.Code, second.Body.String())
	}

	if executor.calls != 1 {
		t.Fatalf(
			"expected executor to be called once, got %d",
			executor.calls,
		)
	}
}
