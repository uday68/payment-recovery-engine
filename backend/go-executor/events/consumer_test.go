//go:build integration
// +build integration

package events

import (
	"context"
	"encoding/json"
	"fmt"
	"testing"
	"time"

	"github.com/segmentio/kafka-go"
)

type testEventHandler struct {
	events []PaymentFailedEvent
}
type failingEventHandler struct{}

func (h *failingEventHandler) Handle(event PaymentFailedEvent) error {
	return fmt.Errorf("simulated processing failure")
}

func (h *testEventHandler) Handle(event PaymentFailedEvent) error {
	h.events = append(h.events, event)
	return nil
}

func TestKafkaConsumerDeliversPaymentFailedEvent(t *testing.T) {
	skipIfKafkaUnavailable(t)
	reader := kafka.NewReader(kafka.ReaderConfig{
		Brokers: []string{"localhost:9092"},
		Topic:   "recovery.payment.failed",
		GroupID: "test-kafka-consumer",
	})

	defer reader.Close()

	handler := &testEventHandler{}

	consumer := NewKafkaConsumer(reader, handler)

	event := PaymentFailedEvent{
		EventID:       "evt-consumer-001",
		EventType:     "PAYMENT_FAILED",
		PaymentID:     "pay-consumer-001",
		CustomerID:    "cust-consumer-001",
		Amount:        5000,
		PaymentMethod: "UPI",
		Bank:          "HDFC",
		FailureCode:   "BANK_TIMEOUT",
		Timestamp:     time.Now().UTC(),
	}

	payload, err := json.Marshal(event)
	if err != nil {
		t.Fatalf("failed to marshal event: %v", err)
	}

	writer := &kafka.Writer{
		Addr:                   kafka.TCP("localhost:9092"),
		Topic:                  "recovery.payment.failed",
		AllowAutoTopicCreation: true,
	}

	defer writer.Close()

	err = writer.WriteMessages(context.Background(), kafka.Message{
		Key:   []byte(event.EventID),
		Value: payload,
	})

	if err != nil {
		t.Fatalf("failed to publish test event: %v", err)
	}

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	found := false
	for !found {
		err = consumer.Consume(ctx)
		if err != nil {
			t.Fatalf("consumer failed: %v", err)
		}

		for _, e := range handler.events {
			if e.EventID == event.EventID {
				found = true
				break
			}
		}
	}
}
func TestKafkaConsumerDoesNotCommitWhenHandlerFails(t *testing.T) {
	skipIfKafkaUnavailable(t)
	reader := kafka.NewReader(kafka.ReaderConfig{
		Brokers: []string{"localhost:9092"},
		Topic:   "recovery.payment.failed",
		GroupID: "test-consumer-failure",
	})

	defer reader.Close()

	handler := &failingEventHandler{}

	consumer := NewKafkaConsumer(reader, handler)

	event := PaymentFailedEvent{
		EventID:       "evt-failure-001",
		EventType:     "PAYMENT_FAILED",
		PaymentID:     "pay-failure-001",
		CustomerID:    "cust-failure-001",
		Amount:        5000,
		PaymentMethod: "UPI",
		Bank:          "HDFC",
		FailureCode:   "BANK_TIMEOUT",
		Timestamp:     time.Now().UTC(),
	}

	payload, err := json.Marshal(event)
	if err != nil {
		t.Fatalf("failed to marshal event: %v", err)
	}

	writer := &kafka.Writer{
		Addr:                   kafka.TCP("localhost:9092"),
		Topic:                  "recovery.payment.failed",
		AllowAutoTopicCreation: true,
	}

	defer writer.Close()

	err = writer.WriteMessages(context.Background(), kafka.Message{
		Key:   []byte(event.EventID),
		Value: payload,
	})

	if err != nil {
		t.Fatalf("failed to publish event: %v", err)
	}

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	err = consumer.Consume(ctx)

	if err == nil {
		t.Fatal("expected handler failure")
	}
}
func TestConsumerCommitsOnlyAfterSuccessfulHandler(t *testing.T) {
	skipIfKafkaUnavailable(t)
	reader := kafka.NewReader(kafka.ReaderConfig{
		Brokers: []string{"localhost:9092"},
		Topic:   "recovery.payment.failed",
		GroupID: "test-consumer-commit",
	})

	defer reader.Close()

	handler := &testEventHandler{}
	consumer := NewKafkaConsumer(reader, handler)

	event := PaymentFailedEvent{
		EventID:       "evt-commit-001",
		EventType:     "PAYMENT_FAILED",
		PaymentID:     "pay-commit-001",
		CustomerID:    "cust-commit-001",
		Amount:        5000,
		PaymentMethod: "UPI",
		Bank:          "HDFC",
		FailureCode:   "BANK_TIMEOUT",
		Timestamp:     time.Now().UTC(),
	}

	payload, err := json.Marshal(event)
	if err != nil {
		t.Fatalf("failed to marshal event: %v", err)
	}

	writer := &kafka.Writer{
		Addr:                   kafka.TCP("localhost:9092"),
		Topic:                  "recovery.payment.failed",
		AllowAutoTopicCreation: true,
	}

	defer writer.Close()

	err = writer.WriteMessages(context.Background(), kafka.Message{
		Key:   []byte(event.EventID),
		Value: payload,
	})

	if err != nil {
		t.Fatalf("failed to publish event: %v", err)
	}

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	if err := consumer.Consume(ctx); err != nil {
		t.Fatalf("consumer failed: %v", err)
	}

	if len(handler.events) != 1 {
		t.Fatalf(
			"expected handler to receive 1 event, got %d",
			len(handler.events),
		)
	}
}
