//go:build integration
// +build integration

package main

import (
	"context"
	"fmt"
	"net"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

func skipIfRedisUnavailable(t *testing.T, addr string) {
	conn, err := net.DialTimeout("tcp", addr, 200*time.Millisecond)
	if err != nil {
		t.Skipf("Skipping integration test: Redis not reachable at %s: %v", addr, err)
	}
	conn.Close()
}

func TestDistributedRateLimiter_AllowedWithinLimit(t *testing.T) {
	skipIfRedisUnavailable(t, "localhost:6379")
	limiter := NewDistributedRateLimiter("localhost:6379", "", 0, true)
	defer limiter.Close()

	ctx := context.Background()
	testKey := fmt.Sprintf("test-allow-%d", time.Now().UnixNano())
	limit := int64(5)
	windowSec := 10

	// First 5 requests must be allowed
	for i := int64(1); i <= limit; i++ {
		res, err := limiter.Allow(ctx, testKey, limit, windowSec)
		if err != nil {
			t.Fatalf("unexpected error on request %d: %v", i, err)
		}
		if !res.Allowed {
			t.Fatalf("expected request %d to be allowed", i)
		}
		if res.CurrentTokens != i {
			t.Fatalf("expected current tokens %d, got %d", i, res.CurrentTokens)
		}
		if res.Status != "LIVE" {
			t.Fatalf("expected status LIVE, got %s", res.Status)
		}
	}

	// 6th request must be rejected
	res6, err := limiter.Allow(ctx, testKey, limit, windowSec)
	if err != nil {
		t.Fatalf("unexpected error on request 6: %v", err)
	}
	if res6.Allowed {
		t.Fatalf("expected request 6 to be rejected by rate limiter")
	}
	if res6.RemainingTokens != 0 {
		t.Fatalf("expected 0 remaining tokens, got %d", res6.RemainingTokens)
	}
}

func TestDistributedRateLimiter_ConcurrentGoroutines(t *testing.T) {
	skipIfRedisUnavailable(t, "localhost:6379")
	limiter := NewDistributedRateLimiter("localhost:6379", "", 0, true)
	defer limiter.Close()

	ctx := context.Background()
	testKey := fmt.Sprintf("test-concurrent-%d", time.Now().UnixNano())
	limit := int64(15)
	windowSec := 10
	totalRequests := 50

	var allowedCount int64
	var rejectedCount int64

	var wg sync.WaitGroup
	wg.Add(totalRequests)

	for i := 0; i < totalRequests; i++ {
		go func() {
			defer wg.Done()
			res, err := limiter.Allow(ctx, testKey, limit, windowSec)
			if err != nil {
				t.Errorf("unexpected error in concurrent goroutine: %v", err)
				return
			}
			if res.Allowed {
				atomic.AddInt64(&allowedCount, 1)
			} else {
				atomic.AddInt64(&rejectedCount, 1)
			}
		}()
	}

	wg.Wait()

	if allowedCount != limit {
		t.Fatalf("expected exactly %d allowed requests under concurrent load, got %d", limit, allowedCount)
	}
	if rejectedCount != int64(totalRequests)-limit {
		t.Fatalf("expected exactly %d rejected requests, got %d", int64(totalRequests)-limit, rejectedCount)
	}
}

func TestDistributedRateLimiter_FailClosedWhenRedisDown(t *testing.T) {
	// Point to non-existent port to simulate Redis failure
	limiter := NewDistributedRateLimiter("localhost:59999", "", 0, true)
	defer limiter.Close()

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	res, err := limiter.Allow(ctx, "fail-closed-test", 10, 10)
	if err == nil {
		t.Fatalf("expected error when redis is down")
	}
	if res == nil {
		t.Fatalf("expected non-nil result structure")
	}
	if res.Allowed != false {
		t.Fatalf("fail-closed rate limiter must reject payment when redis is down")
	}
	if res.Status != "UNAVAILABLE" {
		t.Fatalf("expected status UNAVAILABLE, got %s", res.Status)
	}
}
