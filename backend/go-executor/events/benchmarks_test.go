package events

import (
	"context"
	"fmt"
	"testing"
	"time"
)

func BenchmarkDurableEventStore_ClaimOrRenew(b *testing.B) {
	store := NewEventStore()
	ctx := context.Background()

	b.ResetTimer()
	b.RunParallel(func(pb *testing.PB) {
		idx := 0
		for pb.Next() {
			idx++
			eventID := fmt.Sprintf("bench-evt-%d-%d", time.Now().UnixNano(), idx)
			_, _ = store.ClaimOrRenew(ctx, eventID, "bench-worker", 30*time.Second, 3)
		}
	})
}

func BenchmarkDurableEventStore_DuplicateSuppression(b *testing.B) {
	store := NewEventStore()
	ctx := context.Background()
	eventID := "bench-static-event-001"

	// Initial claim and mark completed
	_, _ = store.ClaimOrRenew(ctx, eventID, "bench-worker", 30*time.Second, 3)
	_ = store.MarkCompleted(ctx, eventID, "bench-worker")

	b.ResetTimer()
	b.RunParallel(func(pb *testing.PB) {
		for pb.Next() {
			res, _ := store.ClaimOrRenew(ctx, eventID, "bench-worker", 30*time.Second, 3)
			if !res.AlreadyCompleted {
				b.Fatalf("expected AlreadyCompleted")
			}
		}
	})
}

func BenchmarkRecoveryFlow_ProcessEndToEnd(b *testing.B) {
	store := NewEventStore()
	decisioner := &failingDecisioner{}
	executor := &failingExecutor{}
	flow := NewRecoveryFlow(store, decisioner, executor)

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		event := PaymentFailedEvent{
			EventID:   fmt.Sprintf("bench-flow-%d", i),
			PaymentID: fmt.Sprintf("pay-bench-%d", i),
			Amount:    5000,
		}
		_, err := flow.Process(event)
		if err != nil {
			b.Fatalf("process error: %v", err)
		}
	}
}
