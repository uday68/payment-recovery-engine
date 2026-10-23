package main

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func TestSystemCircuitBreakersHandler(t *testing.T) {
	registry := NewGatewayCircuitBreakers()
	handler := circuitBreakersHandler(registry)

	req := httptest.NewRequest(http.MethodGet, "/v1/system/circuit-breakers", nil)
	rec := httptest.NewRecorder()

	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", rec.Code)
	}

	var statuses []CircuitBreakerStatus
	if err := json.NewDecoder(rec.Body).Decode(&statuses); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}

	if len(statuses) != 4 {
		t.Fatalf("expected 4 circuit breakers, got %d", len(statuses))
	}
}

func TestSystemCircuitBreakerTripAndReset(t *testing.T) {
	registry := NewGatewayCircuitBreakers()
	tripHandler := circuitBreakersTripHandler(registry)
	resetHandler := circuitBreakersResetHandler(registry)

	// Trip HDFC
	tripReq := httptest.NewRequest(http.MethodPost, "/v1/system/circuit-breakers/trip?gateway=HDFC", nil)
	tripRec := httptest.NewRecorder()
	tripHandler.ServeHTTP(tripRec, tripReq)

	if tripRec.Code != http.StatusOK {
		t.Fatalf("expected 200 on trip, got %d", tripRec.Code)
	}

	statuses := registry.GetAll()
	var hdfcStatus CircuitBreakerStatus
	for _, s := range statuses {
		if s.Gateway == "HDFC" {
			hdfcStatus = s
			break
		}
	}

	if hdfcStatus.State != CircuitOpen {
		t.Fatalf("expected HDFC to be OPEN after trip, got %s", hdfcStatus.State)
	}

	// Reset HDFC
	resetReq := httptest.NewRequest(http.MethodPost, "/v1/system/circuit-breakers/reset?gateway=HDFC", nil)
	resetRec := httptest.NewRecorder()
	resetHandler.ServeHTTP(resetRec, resetReq)

	if resetRec.Code != http.StatusOK {
		t.Fatalf("expected 200 on reset, got %d", resetRec.Code)
	}

	statuses = registry.GetAll()
	for _, s := range statuses {
		if s.Gateway == "HDFC" {
			hdfcStatus = s
			break
		}
	}

	if hdfcStatus.State != CircuitClosed {
		t.Fatalf("expected HDFC to be CLOSED after reset, got %s", hdfcStatus.State)
	}
}

func TestSystemNodesHandler(t *testing.T) {
	metrics := NewRecoveryMetrics()
	startTime := time.Now().Add(-10 * time.Second)
	handler := systemNodesHandler(startTime, metrics)

	req := httptest.NewRequest(http.MethodGet, "/v1/system/nodes", nil)
	rec := httptest.NewRecorder()

	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", rec.Code)
	}

	var node NodeStatus
	if err := json.NewDecoder(rec.Body).Decode(&node); err != nil {
		t.Fatalf("failed to decode node status: %v", err)
	}

	if node.NodeID != "go-executor-primary-01" {
		t.Fatalf("expected node_id 'go-executor-primary-01', got %s", node.NodeID)
	}

	if node.Status != "HEALTHY" {
		t.Fatalf("expected status 'HEALTHY', got %s", node.Status)
	}

	if node.Goroutines <= 0 {
		t.Fatalf("expected goroutines > 0, got %d", node.Goroutines)
	}
}

func TestWithCORS(t *testing.T) {
	dummy := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte("ok"))
	})
	handler := withCORS(dummy)

	// Test OPTIONS preflight
	req := httptest.NewRequest(http.MethodOptions, "/any", nil)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200 on OPTIONS, got %d", rec.Code)
	}

	if rec.Header().Get("Access-Control-Allow-Origin") != "*" {
		t.Fatalf("expected Access-Control-Allow-Origin = *")
	}

	// Test GET request passes through
	req = httptest.NewRequest(http.MethodGet, "/any", nil)
	rec = httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK || strings.TrimSpace(rec.Body.String()) != "ok" {
		t.Fatalf("expected 200 with body 'ok', got %d: %s", rec.Code, rec.Body.String())
	}
}
