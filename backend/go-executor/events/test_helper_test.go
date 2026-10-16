package events

import (
	"net"
	"testing"
	"time"
)

func skipIfKafkaUnavailable(t *testing.T) {
	conn, err := net.DialTimeout("tcp", "localhost:9092", 200*time.Millisecond)
	if err != nil {
		t.Skipf("Skipping Kafka integration test: Kafka broker unreachable at localhost:9092: %v", err)
	}
	conn.Close()
}
