//go:build integration
// +build integration

package main

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func TestPostgresCommandStorePersistsIdempotency(t *testing.T) {
	databaseURL := "postgres://recovery:recovery@localhost:5432/recovery_engine?sslmode=disable"

	store, err := NewPostgresCommandStore(databaseURL)
	if err != nil {
		t.Skipf("PostgreSQL not available: %v", err)
	}
	defer store.Close()

	commandID := "postgres-persistence-" + time.Now().Format("20060102150405.000000000")

	first, err := store.Claim(commandID)
	if err != nil {
		t.Fatalf("first claim failed: %v", err)
	}

	if !first {
		t.Fatal("first claim should succeed")
	}

	second, err := store.Claim(commandID)
	if err != nil {
		t.Fatalf("second claim failed: %v", err)
	}

	if second {
		t.Fatal("second claim should be rejected as duplicate")
	}

	if err := store.Delete(commandID); err != nil {
		t.Fatalf("failed to clean up command: %v", err)
	}
}

func TestPostgresCommandStoreClaimsOnlyOnce(t *testing.T) {
	store, err := NewPostgresCommandStore(
		"postgres://recovery:recovery@localhost:5432/recovery_engine?sslmode=disable",
	)

	if err != nil {
		t.Skipf("Skipping integration test: Postgres store unavailable: %v", err)
	}
	defer store.Close()

	commandID := "postgres-test-001"

	// Clean up from previous runs.
	err = store.Delete(commandID)
	if err != nil {
		t.Fatalf("failed to clean test command: %v", err)
	}

	first, err := store.Claim(commandID)
	if err != nil {
		t.Fatalf("first claim failed: %v", err)
	}

	second, err := store.Claim(commandID)
	if err != nil {
		t.Fatalf("second claim failed: %v", err)
	}

	if !first {
		t.Fatal("first claim should succeed")
	}

	if second {
		t.Fatal("second claim should fail")
	}

	err = store.Delete(commandID)
	if err != nil {
		t.Fatalf("failed to clean up: %v", err)
	}
}

func TestExecuteRecoveryWithPostgresIdempotency(t *testing.T) {
	store, err := NewPostgresCommandStore(
		"postgres://recovery:recovery@localhost:5432/recovery_engine?sslmode=disable",
	)

	if err != nil {
		t.Skipf("Skipping integration test: Postgres store unavailable: %v", err)
	}
	defer store.Close()

	commandID := "http-postgres-test-001"

	if err := store.Delete(commandID); err != nil {
		t.Fatalf("failed to clean test command: %v", err)
	}

	handler := executeRecoveryHandlerWithStore(store)

	body := `{
		"command_id": "http-postgres-test-001",
		"payment_id": "payment-postgres-test-001",
		"action": "RETRY_LATER",
		"amount": 5000
	}`

	req1 := httptest.NewRequest(
		http.MethodPost,
		"/v1/recovery/execute",
		strings.NewReader(body),
	)

	rec1 := httptest.NewRecorder()
	handler.ServeHTTP(rec1, req1)

	if !strings.Contains(rec1.Body.String(), `"status":"EXECUTED"`) {
		t.Fatalf("first request should execute: %s", rec1.Body.String())
	}

	req2 := httptest.NewRequest(
		http.MethodPost,
		"/v1/recovery/execute",
		strings.NewReader(body),
	)

	rec2 := httptest.NewRecorder()
	handler.ServeHTTP(rec2, req2)

	if !strings.Contains(rec2.Body.String(), `"status":"DUPLICATE"`) {
		t.Fatalf("second request should be duplicate: %s", rec2.Body.String())
	}

	if err := store.Delete(commandID); err != nil {
		t.Fatalf("failed to clean up: %v", err)
	}
}
