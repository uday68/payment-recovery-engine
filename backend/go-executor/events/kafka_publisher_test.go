//go:build integration
// +build integration

package events

import (
	"context"
	"testing"
	"time"

	"github.com/segmentio/kafka-go"
)

func TestKafkaPublisherPublishesPaymentFailedEvent(t *testing.T) {
	skipIfKafkaUnavailable(t)
	writer := &kafka.Writer{
		Addr:                   kafka.TCP("127.0.0.1:9092"),
		Topic:                  "recovery.payment.failed",
		Balancer:               &kafka.LeastBytes{},
		AllowAutoTopicCreation: true,
	}

	defer writer.Close()

	publisher := NewKafkaPublisher(writer)

	event := PaymentFailedEvent{
		EventID:       "evt-kafka-001",
		EventType:     "PAYMENT_FAILED",
		PaymentID:     "pay-kafka-001",
		CustomerID:    "cust-kafka-001",
		Amount:        5000,
		PaymentMethod: "UPI",
		Bank:          "HDFC",
		FailureCode:   "BANK_TIMEOUT",
		Timestamp:     time.Now().UTC(),
	}

	err := publisher.Publish(event)
	if err != nil {
		t.Fatalf("publish failed: %v", err)
	}

	reader := kafka.NewReader(kafka.ReaderConfig{
		Brokers: []string{"127.0.0.1:9092"},
		Topic:   "recovery.payment.failed",
		GroupID: "test-kafka-publisher",
	})

	defer reader.Close()

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	var matched kafka.Message
	for {
		message, err := reader.ReadMessage(ctx)
		if err != nil {
			t.Fatalf("failed to read published event: %v", err)
		}

		if string(message.Key) == event.EventID {
			matched = message
			break
		}
	}

	if string(matched.Key) != event.EventID {
		t.Fatalf(
			"expected message key %s, got %s",
			event.EventID,
			string(matched.Key),
		)
	}

	if len(matched.Value) == 0 {
		t.Fatal("published message should contain event payload")
	}
}
