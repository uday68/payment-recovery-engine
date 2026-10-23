//go:build integration
// +build integration

package events

import (
	"sync"
	"testing"
)

func TestPostgresEventStorePreventsConcurrentDuplicateClaims(t *testing.T) {
	databaseURL := "postgres://recovery:recovery@localhost:5432/recovery_engine?sslmode=disable"

	store, err := NewPostgresEventStore(databaseURL)
	if err != nil {
		t.Skipf("PostgreSQL not available: %v", err)
	}
	defer store.Close()

	eventID := "evt-concurrent-postgres-dedup-001"

	const workers = 20

	results := make(chan bool, workers)
	errors := make(chan error, workers)

	var wg sync.WaitGroup

	for i := 0; i < workers; i++ {
		wg.Add(1)

		go func() {
			defer wg.Done()

			claimed, err := store.Claim(eventID)
			if err != nil {
				errors <- err
				return
			}

			results <- claimed
		}()
	}

	wg.Wait()

	close(results)
	close(errors)

	for err := range errors {
		t.Fatalf("claim failed: %v", err)
	}

	successfulClaims := 0

	for claimed := range results {
		if claimed {
			successfulClaims++
		}
	}

	if successfulClaims != 1 {
		t.Fatalf(
			"expected exactly 1 successful claim, got %d",
			successfulClaims,
		)
	}

	if err := store.Delete(eventID); err != nil {
		t.Fatalf("cleanup failed: %v", err)
	}
}
