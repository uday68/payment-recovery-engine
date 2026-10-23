package events

import (
	"context"
	"errors"
	"testing"
)

type mockCapacityChecker struct {
	full bool
}

func (m *mockCapacityChecker) IsFull() bool {
	return m.full
}

type mockConsumer struct {
	consumeCalls int
}

func (m *mockConsumer) Consume(ctx context.Context) error {
	m.consumeCalls++
	return nil
}

func TestBackpressureAwareConsumerStopsWhenCapacityIsFull(t *testing.T) {
	consumer := NewBackpressureAwareConsumer(
		nil,
		nil,
	)

	if consumer == nil {
		t.Fatal("expected backpressure-aware consumer")
	}
}

func TestBackpressureAwareConsumerPausesWhenQueueIsFullAndResumesWhenDrained(t *testing.T) {
	// Verifies the backpressure contract:
	// queue full
	//   ↓
	// consumer does not fetch
	//   ↓
	// Kafka retains event
	//   ↓
	// queue drains
	//   ↓
	// consumer resumes

	queue := &mockCapacityChecker{full: true}
	downstream := &mockConsumer{}

	consumer := NewBackpressureAwareConsumer(
		downstream,
		queue,
	)

	ctx := context.Background()

	// 1. Queue is full: consumer must NOT fetch from source
	err := consumer.Consume(ctx)
	if !errors.Is(err, ErrQueueFull) {
		t.Fatalf("expected ErrQueueFull when queue is full, got: %v", err)
	}

	if downstream.consumeCalls != 0 {
		t.Fatalf("expected 0 consumer fetch calls when queue is full, got %d", downstream.consumeCalls)
	}

	// 2. Queue drains: capacity becomes available
	queue.full = false

	// 3. Consumer resumes fetching
	err = consumer.Consume(ctx)
	if err != nil {
		t.Fatalf("expected nil error after queue drains, got: %v", err)
	}

	if downstream.consumeCalls != 1 {
		t.Fatalf("expected consumer to resume and fetch 1 event, got %d", downstream.consumeCalls)
	}
}
