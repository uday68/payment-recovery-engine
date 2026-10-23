//go:build integration
// +build integration

package events

import (
	"testing"
	"time"
)

func TestPostgresEventStorePersistsIdempotency(t *testing.T) {
	databaseURL := "postgres://recovery:recovery@localhost:5432/recovery_engine?sslmode=disable"

	store, err := NewPostgresEventStore(databaseURL)
	if err != nil {
		t.Skipf("PostgreSQL not available: %v", err)
	}
	defer store.Close()

	eventID := "evt-postgres-idempotency-" +
		time.Now().Format("20060102150405.000000000")

	first, err := store.Claim(eventID)
	if err != nil {
		t.Fatalf("first claim failed: %v", err)
	}

	if !first {
		t.Fatal("first event claim should succeed")
	}

	second, err := store.Claim(eventID)
	if err != nil {
		t.Fatalf("second claim failed: %v", err)
	}

	if second {
		t.Fatal("duplicate event should not be claimed")
	}

	if err := store.Delete(eventID); err != nil {
		t.Fatalf("cleanup failed: %v", err)
	}
}
