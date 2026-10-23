//go:build integration
// +build integration

package events

import (
	"context"
	"encoding/json"
	"fmt"
	"sync"
	"testing"
	"time"

	"github.com/segmentio/kafka-go"
)

func TestKafkaConcurrentRecoveryWorkers(t *testing.T) {
	const (
		eventCount  = 20
		workerCount = 2
	)

	topic := fmt.Sprintf(
		"recovery.payment.failed.concurrent-%d",
		time.Now().UnixNano(),
	)

	conn, err := kafka.Dial("tcp", "localhost:9092")
	if err != nil {
		t.Skipf("Skipping integration test: failed to dial kafka: %v", err)
	}
	defer conn.Close()

	if err := conn.CreateTopics(kafka.TopicConfig{
		Topic:             topic,
		NumPartitions:     3,
		ReplicationFactor: 1,
	}); err != nil {
		t.Fatalf("failed to create topic %s: %v", topic, err)
	}

	groupID := "recovery-concurrent-" +
		time.Now().Format("20060102150405.000000000")

	eventStore := NewEventStore()
	decisioner := &flowDecisioner{}
	executor := &flowExecutor{}

	var consumers []*KafkaConsumer
	var readers []*kafka.Reader

	for i := 0; i < workerCount; i++ {
		reader := kafka.NewReader(kafka.ReaderConfig{
			Brokers: []string{"localhost:9092"},
			Topic:   topic,
			GroupID: groupID,
		})

		readers = append(readers, reader)

		consumers = append(
			consumers,
			NewRecoveryKafkaConsumer(
				reader,
				eventStore,
				decisioner,
				executor,
			),
		)
	}

	defer func() {
		for _, reader := range readers {
			_ = reader.Close()
		}
	}()

	writer := &kafka.Writer{
		Addr:                   kafka.TCP("localhost:9092"),
		Topic:                  topic,
		Balancer:               &kafka.Hash{},
		AllowAutoTopicCreation: true,
	}

	defer writer.Close()

	messages := make([]kafka.Message, 0, eventCount)

	for i := 0; i < eventCount; i++ {
		event := PaymentFailedEvent{
			EventID:       fmt.Sprintf("evt-worker-concurrent-%d", i),
			EventType:     "PAYMENT_FAILED",
			PaymentID:     fmt.Sprintf("pay-worker-concurrent-%d", i),
			CustomerID:    fmt.Sprintf("cust-worker-concurrent-%d", i),
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
			t.Fatalf("marshal event: %v", err)
		}

		messages = append(messages, kafka.Message{
			Key:   []byte(event.EventID),
			Value: payload,
		})
	}

	if err := writer.WriteMessages(
		context.Background(),
		messages...,
	); err != nil {
		t.Fatalf("publish events: %v", err)
	}

	ctx, cancel := context.WithTimeout(
		context.Background(),
		30*time.Second,
	)
	defer cancel()

	var wg sync.WaitGroup

	for i, consumer := range consumers {
		wg.Add(1)

		go func(workerID int, c *KafkaConsumer) {
			defer wg.Done()

			for {
				if err := c.Consume(ctx); err != nil {
					if ctx.Err() != nil {
						return
					}

					t.Errorf(
						"worker %d consumer error: %v",
						workerID,
						err,
					)
					return
				}
			}
		}(i, consumer)
	}

	// Allow the workers time to consume the full test batch.
	for {
		if decisioner.callCount() >= eventCount &&
			executor.callCount() >= eventCount {
			break
		}

		select {
		case <-ctx.Done():
			t.Fatalf(
				"timed out: decisions=%d executions=%d",
				decisioner.callCount(),
				executor.callCount(),
			)
		case <-time.After(10 * time.Millisecond):
		}
	}

	cancel()
	wg.Wait()

	if decisioner.callCount() != eventCount {
		t.Fatalf(
			"expected %d decision calls, got %d",
			eventCount,
			decisioner.callCount(),
		)
	}

	if executor.callCount() != eventCount {
		t.Fatalf(
			"expected %d execution calls, got %d",
			eventCount,
			executor.callCount(),
		)
	}
}
