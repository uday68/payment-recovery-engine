package main

import (
	"testing"
)

func TestCommandStoreClaimsOnlyOnce(t *testing.T) {
	store := NewCommandStore()

	first, err := store.Claim("cmd-001")
	if err != nil {
		t.Fatalf("first claim failed :%v", err)
	}

	second, err := store.Claim("cmd-001")
	if err != nil {
		t.Fatalf("second claim failed :%v", err)
	}
	if !first {
		t.Fatal("first claim should succeed")
	}

	if second {
		t.Fatal("second claim should fail")
	}
}

func TestCommandIdempotency(t *testing.T) {
	store := NewCommandStore()

	commandID := "cmd-idempotency-001"

	first, err := store.Claim(commandID)
	if err != nil {
		t.Fatalf("first claim returned error: %v", err)
	}

	if !first {
		t.Fatal("first claim should succeed")
	}

	second, err := store.Claim(commandID)
	if err != nil {
		t.Fatalf("second claim returned error: %v", err)
	}

	if second {
		t.Fatal("second claim should be rejected as duplicate")
	}
}
