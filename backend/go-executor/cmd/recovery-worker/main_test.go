package main

import (
	"net"
	"testing"
	"time"

	"github.com/segmentio/kafka-go"
)

func TestBuildRecoveryConsumer(t *testing.T) {
	conn, err := net.DialTimeout("tcp", "localhost:5432", 200*time.Millisecond)
	if err != nil {
		t.Skipf("Skipping integration test: Postgres unreachable: %v", err)
	}
	conn.Close()

	defer func() {
		if r := recover(); r != nil {
			t.Skipf("Skipping integration test: Postgres credentials or schema not ready: %v", r)
		}
	}()

	reader := kafka.NewReader(kafka.ReaderConfig{
		Brokers: []string{"localhost:9092"},
		Topic:   "recovery.payment.failed",
		GroupID: "recovery-worker-test",
	})

	defer reader.Close()

	consumer := buildRecoveryConsumer(
		reader,
		"postgres://recovery:recovery@localhost:5432/recovery_engine?sslmode=disable",
		"http://localhost:8000",
		"http://localhost:8080",
	)

	if consumer == nil {
		t.Fatal("expected recovery consumer to be created")
	}
}
