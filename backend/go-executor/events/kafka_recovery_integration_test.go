package events

import (
	"context"
	"encoding/json"
	"testing"
	"time"

	"github.com/segmentio/kafka-go"
)

func TestKafkaDrivesRecoveryFlow(t *testing.T) {
	skipIfKafkaUnavailable(t)
	topic := "recovery.payment.failed"

	reader := kafka.NewReader(kafka.ReaderConfig{
		Brokers: []string{"localhost:9092"},
		Topic:   topic,
		GroupID: "recovery-flow-integration-" + time.Now().Format("20060102150405.000000000"),
	})

	defer reader.Close()

	decisioner := &flowDecisioner{}
	executor := &flowExecutor{}
	eventStore := NewEventStore()

	consumer := NewRecoveryKafkaConsumer(
		reader,
		eventStore,
		decisioner,
		executor,
	)

	event := PaymentFailedEvent{
		EventID:       "evt-kafka-flow-001",
		EventType:     "PAYMENT_FAILED",
		PaymentID:     "pay-kafka-flow-001",
		CustomerID:    "cust-kafka-flow-001",
		Amount:        5000,
		PaymentMethod: "UPI",
		Bank:          "HDFC",
		FailureCode:   "BANK_TIMEOUT",
		SuccessRate:   0.80,
		RecoveryRate:  0.50,
		Timestamp:     time.Now().UTC(),
	}

	payload, err := json.Marshal(event)
	if err != nil {
		t.Fatalf("failed to marshal event: %v", err)
	}

	writer := &kafka.Writer{
		Addr:  kafka.TCP("localhost:9092"),
		Topic: topic,
	}

	defer writer.Close()

	if err := writer.WriteMessages(
		context.Background(),
		kafka.Message{
			Key:   []byte(event.EventID),
			Value: payload,
		},
	); err != nil {
		t.Fatalf("failed to publish event: %v", err)
	}

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	if err := consumer.Consume(ctx); err != nil {
		t.Fatalf("consumer failed: %v", err)
	}

	if decisioner.calls != 1 {
		t.Fatalf(
			"expected one decision call, got %d",
			decisioner.calls,
		)
	}

	if executor.calls != 1 {
		t.Fatalf(
			"expected one execution call, got %d",
			executor.calls,
		)
	}
}
