package main

import (
	"encoding/json"
	"log"
	"net/http"
	"os"
	"runtime"
	"sync"
	"time"
)

type RecoveryCommand struct {
	CommandID string  `json:"command_id"`
	PaymentID string  `json:"payment_id"`
	Action    string  `json:"action"`
	Amount    float64 `json:"amount"`
}

type RecoveryResponse struct {
	CommandID string `json:"command_id"`
	PaymentID string `json:"payment_id"`
	Status    string `json:"status"`
	Action    string `json:"action,omitempty"`
	Recovered bool   `json:"recovered"`
	Retryable bool   `json:"retryable"`
	Outcome   string `json:"outcome,omitempty"`
	Attempts  int    `json:"attempts,omitempty"`
}

func executeRecoveryHandler() http.Handler {
	return executeRecoveryHandlerWithStore(NewCommandStore())
}
func executeRecoveryHandlerWithStore(
	store CommandClaimer,
) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var command RecoveryCommand

		if err := json.NewDecoder(r.Body).Decode(&command); err != nil {
			http.Error(w, "invalid request", http.StatusBadRequest)
			return
		}

		claimed, err := store.Claim(command.CommandID)

		if err != nil {
			http.Error(w, "idempotency store error", http.StatusInternalServerError)
			return
		}

		if !claimed {
			response := RecoveryResponse{
				CommandID: command.CommandID,
				PaymentID: command.PaymentID,
				Status:    "DUPLICATE",
			}

			w.Header().Set("Content-Type", "application/json")
			json.NewEncoder(w).Encode(response)
			return
		}

		log.Printf(
			"Executing recovery: payment_id=%s action=%s amount=%.2f",
			command.PaymentID,
			command.Action,
			command.Amount,
		)

		response := RecoveryResponse{
			CommandID: command.CommandID,
			PaymentID: command.PaymentID,
			Status:    "EXECUTED",
			Action:    command.Action,
			Recovered: true,
		}

		w.Header().Set("Content-Type", "application/json")

		json.NewEncoder(w).Encode(response)
	})
}
func executeRecoveryHandlerWithStoreAndMetrics(
	store CommandClaimer,
	metrics *RecoveryMetrics,
) http.Handler {
	gateway := NewSimulatedGateway()

	executor := NewRetryExecutorWithBackoff(
		gateway,
		3,
		NewBackoffPolicy(100),
		time.Sleep,
	)

	return executeRecoveryHandlerWithExecutorAndMetrics(
		store,
		executor,
		metrics,
	)
}

type CircuitBreakerStatus struct {
	Gateway          string       `json:"gateway"`
	State            CircuitState `json:"state"`
	FailureCount     int          `json:"failure_count"`
	FailureThreshold int          `json:"failure_threshold"`
	LastTripTime     *time.Time   `json:"last_trip_time,omitempty"`
}

type GatewayCircuitBreakers struct {
	mu       sync.RWMutex
	breakers map[string]*CircuitBreaker
}

func NewGatewayCircuitBreakers() *GatewayCircuitBreakers {
	return &GatewayCircuitBreakers{
		breakers: map[string]*CircuitBreaker{
			"HDFC":  NewCircuitBreaker(5),
			"ICICI": NewCircuitBreaker(5),
			"SBI":   NewCircuitBreaker(5),
			"Axis":  NewCircuitBreaker(5),
		},
	}
}

func (g *GatewayCircuitBreakers) GetAll() []CircuitBreakerStatus {
	g.mu.RLock()
	defer g.mu.RUnlock()

	keys := []string{"HDFC", "ICICI", "SBI", "Axis"}
	result := make([]CircuitBreakerStatus, 0, len(keys))
	for _, k := range keys {
		b, exists := g.breakers[k]
		if !exists {
			continue
		}
		b.mu.Lock()
		state := b.state
		fc := b.failureCount
		ft := b.failureThreshold
		var opened *time.Time
		if !b.openedAt.IsZero() {
			t := b.openedAt
			opened = &t
		}
		b.mu.Unlock()

		result = append(result, CircuitBreakerStatus{
			Gateway:          k,
			State:            state,
			FailureCount:     fc,
			FailureThreshold: ft,
			LastTripTime:     opened,
		})
	}
	return result
}

func (g *GatewayCircuitBreakers) Trip(gateway string) bool {
	g.mu.Lock()
	defer g.mu.Unlock()
	b, ok := g.breakers[gateway]
	if !ok {
		return false
	}
	b.mu.Lock()
	b.state = CircuitOpen
	b.openedAt = time.Now()
	b.failureCount = b.failureThreshold
	b.mu.Unlock()
	return true
}

func (g *GatewayCircuitBreakers) Reset(gateway string) bool {
	g.mu.Lock()
	defer g.mu.Unlock()
	b, ok := g.breakers[gateway]
	if !ok {
		return false
	}
	b.RecordSuccess()
	return true
}

type NodeStatus struct {
	NodeID           string  `json:"node_id"`
	UptimeSeconds    float64 `json:"uptime_seconds"`
	Goroutines       int     `json:"goroutines"`
	MemoryAllocMB    float64 `json:"memory_alloc_mb"`
	MemorySysMB      float64 `json:"memory_sys_mb"`
	NumGC            uint32  `json:"num_gc"`
	Status           string  `json:"status"`
	ActiveWorkers    int     `json:"active_workers"`
	QueueDepth       int     `json:"queue_depth"`
	ThroughputOpsSec float64 `json:"throughput_ops_sec"`
}

func withCORS(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type, Authorization")
		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusOK)
			return
		}
		next.ServeHTTP(w, r)
	})
}

func circuitBreakersHandler(registry *GatewayCircuitBreakers) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(registry.GetAll())
	})
}

func circuitBreakersTripHandler(registry *GatewayCircuitBreakers) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gateway := r.URL.Query().Get("gateway")
		if gateway == "" {
			var body struct {
				Gateway string `json:"gateway"`
			}
			_ = json.NewDecoder(r.Body).Decode(&body)
			gateway = body.Gateway
		}
		if gateway == "" || !registry.Trip(gateway) {
			http.Error(w, "invalid gateway", http.StatusBadRequest)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]any{"status": "TRIPPED", "gateway": gateway})
	})
}

func circuitBreakersResetHandler(registry *GatewayCircuitBreakers) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gateway := r.URL.Query().Get("gateway")
		if gateway == "" {
			var body struct {
				Gateway string `json:"gateway"`
			}
			_ = json.NewDecoder(r.Body).Decode(&body)
			gateway = body.Gateway
		}
		if gateway == "" || !registry.Reset(gateway) {
			http.Error(w, "invalid gateway", http.StatusBadRequest)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]any{"status": "RESET", "gateway": gateway})
	})
}

func systemNodesHandler(startTime time.Time, metrics *RecoveryMetrics) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var m runtime.MemStats
		runtime.ReadMemStats(&m)

		uptime := time.Since(startTime).Seconds()
		snapshot := metrics.Snapshot()
		var throughput float64
		if uptime > 0 && snapshot.TotalExecutions > 0 {
			throughput = float64(snapshot.TotalExecutions) / uptime
		}

		node := NodeStatus{
			NodeID:           "go-executor-primary-01",
			UptimeSeconds:    uptime,
			Goroutines:       runtime.NumGoroutine(),
			MemoryAllocMB:    float64(m.Alloc) / (1024 * 1024),
			MemorySysMB:      float64(m.Sys) / (1024 * 1024),
			NumGC:            m.NumGC,
			Status:           "HEALTHY",
			ActiveWorkers:    4,
			QueueDepth:       0,
			ThroughputOpsSec: throughput,
		}

		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(node)
	})
}

func main() {
	databaseURL := os.Getenv("DATABASE_URL")
	if databaseURL == "" {
		databaseURL = "postgres://recovery:recovery@localhost:5432/recovery_engine?sslmode=disable"
	}

	store, err := NewPostgresCommandStore(databaseURL)
	if err != nil {
		log.Fatalf("failed to initialize command store: %v", err)
	}
	defer store.Close()

	metrics := NewRecoveryMetrics()
	cbRegistry := NewGatewayCircuitBreakers()
	startTime := time.Now()

	mux := http.NewServeMux()
	mux.Handle(
		"/v1/recovery/execute",
		executeRecoveryHandlerWithStoreAndMetrics(store, metrics),
	)
	mux.Handle(
		"/metrics",
		metricsHandler(metrics),
	)
	mux.Handle(
		"/v1/system/circuit-breakers",
		circuitBreakersHandler(cbRegistry),
	)
	mux.Handle(
		"/v1/system/circuit-breakers/trip",
		circuitBreakersTripHandler(cbRegistry),
	)
	mux.Handle(
		"/v1/system/circuit-breakers/reset",
		circuitBreakersResetHandler(cbRegistry),
	)
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]string{"status": "healthy", "service": "go-executor"})
	})
	mux.HandleFunc("/v1/health", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]string{"status": "healthy", "service": "go-executor"})
	})
	mux.Handle(
		"/v1/system/nodes",
		systemNodesHandler(startTime, metrics),
	)

	log.Println("Go executor listening on :8080")

	if err := http.ListenAndServe(":8080", withCORS(mux)); err != nil {
		log.Fatal(err)
	}
}
func executeRecoveryHandlerWithExecutor(
	store CommandClaimer,
	executor RecoveryExecutor,
) http.Handler {
	return executeRecoveryHandlerWithExecutorAndMetrics(
		store,
		executor,
		NewRecoveryMetrics(),
	)
}

func executeRecoveryHandlerWithDependencies(
	store CommandClaimer,
	gateway RecoveryGateway,
) http.Handler {
	executor := NewRetryExecutorWithBackoff(
		gateway,
		3,
		NewBackoffPolicy(100),
		time.Sleep,
	)

	return executeRecoveryHandlerWithExecutor(store, executor)
}
func executeRecoveryHandlerWithExecutorAndMetrics(
	store CommandClaimer,
	executor RecoveryExecutor,
	metrics *RecoveryMetrics,
) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var command RecoveryCommand

		if err := json.NewDecoder(r.Body).Decode(&command); err != nil {
			http.Error(w, "invalid request", http.StatusBadRequest)
			return
		}

		if err := validateRecoveryCommand(command); err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}

		claimed, err := store.Claim(command.CommandID)
		if err != nil {
			http.Error(w, "idempotency error", http.StatusInternalServerError)
			return
		}

		if !claimed {
			response := RecoveryResponse{
				CommandID: command.CommandID,
				PaymentID: command.PaymentID,
				Status:    "DUPLICATE",
			}

			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode(response)
			return
		}

		executionResult := executor.ExecuteWithMetadata(command)
		metrics.Record(executionResult)

		gatewayResult := executionResult.FinalResult

		status := gatewayResult.Status
		if status == "SUCCESS" {
			status = "EXECUTED"
		}

		response := RecoveryResponse{
			CommandID: command.CommandID,
			PaymentID: command.PaymentID,
			Status:    status,
			Action:    gatewayResult.Action,
			Recovered: executionResult.Recovered,
			Retryable: executionResult.Retryable,
			Outcome:   executionResult.Outcome,
			Attempts:  executionResult.Attempts,
		}

		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(response)
	})
}

func metricsHandler(metrics *RecoveryMetrics) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		snapshot := metrics.Snapshot()
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(snapshot)
	})
}
