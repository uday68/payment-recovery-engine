from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class RecoveryDecisionRequest(BaseModel):
    event_id: str
    event_type: str
    payment_id: str
    customer_id: str
    amount: float = Field(gt=0)
    payment_method: str
    bank: str
    failure_code: str
    timestamp: datetime
    success_rate: float = Field(default=0.80, ge=0, le=1)
    recovery_rate: float = Field(default=0.50, ge=0, le=1)


class RecoveryDecisionResponse(BaseModel):
    payment_id: str
    action: str
    probability: float
    expected_value: float


class TransactionItem(BaseModel):
    payment_id: str
    timestamp: str
    method: Optional[str] = "UNAVAILABLE"
    bank: Optional[str] = "UNAVAILABLE"
    amount: float
    failure_code: str
    expected_value: float
    action: str
    status: str
    customer_id: Optional[str] = None
    outcome: Optional[str] = None
    recovered: Optional[bool] = None
    attempts: Optional[int] = None
    retryable: Optional[bool] = None


class TrajectoryPoint(BaseModel):
    time: str
    recovered: float
    failed: float


class CircuitBreakerOverview(BaseModel):
    gateway: str
    state: str
    failure_count: int
    failure_threshold: int
    last_trip_time: Optional[str] = None
    status: Optional[str] = "LIVE"
    source: Optional[str] = "go-executor"


class OverviewSummaryResponse(BaseModel):
    status: str = "LIVE"
    source: str = "postgres.recovery_audit"
    at_risk_revenue: float
    recovered_revenue: float
    recovery_rate: float
    ai_lift: float
    ai_lift_status: str = "SIMULATED"
    ai_lift_source: str = "simulator.controlled_experiment (Seed 42)"
    active_in_flight: int
    trajectory_series: List[TrajectoryPoint]
    circuit_breakers: List[CircuitBreakerOverview]
    recent_transactions: List[TransactionItem]


class StateStepItem(BaseModel):
    step: str
    time: str
    status: str
    description: str
    color: str


class AuditDetailResponse(BaseModel):
    event_id: Optional[str] = None
    payment_id: str
    customer_id: str
    amount: float
    payment_method: Optional[str] = "UNAVAILABLE"
    bank: Optional[str] = "UNAVAILABLE"
    failure_code: str
    probabilities: Dict[str, float]
    recommended_action: str
    expected_value: float
    policy_allowed: bool
    policy_reason: str
    executed_action: str
    outcome: Optional[str] = None
    attempts: Optional[int] = None
    recovered: Optional[bool] = None
    retryable: Optional[bool] = None
    timestamp: str
    merkle_leaf_hash: Optional[str] = None
    merkle_proof: Optional[List[str]] = None
    state_steps: Optional[List[StateStepItem]] = None
    raw_payload: Optional[Dict[str, Any]] = None
    status: str = "LIVE"
    source: str = "postgres.recovery_audit"


class MABArm(BaseModel):
    arm_id: str
    name: str
    strategy: str
    traffic_pct: float
    trials: int
    wins: int
    win_rate: float
    mean_ev: float


class MABExperimentResponse(BaseModel):
    experiment_id: str
    experiment_type: str = "3-WAY_CONTROLLED_EXPERIMENT"
    status: str = "SIMULATED_EXPERIMENT"
    source: str = "simulator.controlled_experiment"
    total_trials: int
    active_arms_count: int
    exploration_allocation: float
    ai_lift_vs_rule: float
    statistical_p_value: Optional[float] = None
    winning_arm: str
    arms: List[MABArm]


class CalibrationPoint(BaseModel):
    predicted: float
    observed: float


class LatencyQuantiles(BaseModel):
    p50_ms: float
    p95_ms: float
    p99_ms: float
    mean_ms: float


class FeatureImportanceItem(BaseModel):
    feature: str
    importance: float


class AIModelHealthResponse(BaseModel):
    status: str = "EVALUATION"
    source: str = "model.evaluation_dataset (ml/data.csv, 59,380 trials)"
    model_name: str
    accuracy: float
    precision: float
    recall: float
    f1_score: float
    roc_auc: float
    cv_roc_auc_mean: float
    cv_roc_auc_std: float
    brier_score: float
    ece: float
    concept_drift_psi: Optional[float] = None
    drift_status: str = "UNAVAILABLE (Requires continuous production streaming feature store)"
    calibration_curve: List[CalibrationPoint]
    latency: LatencyQuantiles
    feature_importances: List[FeatureImportanceItem]


class PolicyItem(BaseModel):
    id: str
    tier: str = "P0"
    priority: str = "P0 CRITICAL"
    name: str
    description: str
    trigger_condition: str
    action_override: str
    triggers_today: int
    enabled: bool


class PolicySimulateRequest(BaseModel):
    recovery_target: float
    gateway_trip_rate: float
    ev_floor: float
    max_hops: int
    auto_recovery_enabled: bool = True


class PolicyConfig(BaseModel):
    recovery_target: float = Field(default=50.0, ge=0.0, le=100.0)
    gateway_trip_rate: float = Field(default=15.0, ge=0.0, le=100.0)
    ev_floor: float = Field(default=50.0, ge=0.0)
    max_hops: int = Field(default=3, ge=1, le=10)
    auto_recovery_enabled: bool = True


class PolicySimulateResponse(BaseModel):
    status: str = "SIMULATED"
    source: str = "policy_simulation_sandbox"
    simulated_recovery_rate: float
    simulated_recovered_revenue: float
    simulated_blocked_count: int
    estimated_ev_gain: float
    gateway_protection_score: float


class AuditLedgerEntry(BaseModel):
    id: int
    payment_id: str
    timestamp: str
    action: str
    amount: float
    recovered: bool
    leaf_hash: str


class AuditLedgerResponse(BaseModel):
    status: str = "LIVE"
    source: str = "postgres.recovery_audit"
    ledger_type: str = "SHA-256 Audit Digest Chain (PostgreSQL ACID WAL)"
    total_records: int
    merkle_root: str
    tree_height: int
    tamper_proof: bool = False
    active_wal_replicas: int = 1
    entries: List[AuditLedgerEntry]


class MerkleProofResponse(BaseModel):
    status: str = "LIVE"
    source: str = "postgres.recovery_audit"
    proof_type: str = "SHA-256 Digest Verification (RFC 6962 tree proofs unavailable)"
    payment_id: str
    leaf_hash: str
    merkle_root: str
    proof_hashes: List[str]
    verified: bool


class KafkaPartitionLag(BaseModel):
    partition: int
    topic: str
    current_offset: Optional[int] = None
    log_end_offset: Optional[int] = None
    lag: Optional[int] = None
    status: str = "UNAVAILABLE"
    source: Optional[str] = "kafka:9092"


class LiveRecoveryStreamResponse(BaseModel):
    status: str = "UNAVAILABLE"
    source: str = "kafka.runtime"
    message: Optional[str] = "Kafka live ingestion metrics uninstrumented in local dev"
    streaming_rate: Optional[str] = "UNAVAILABLE"
    instant_recovery_p95: Optional[str] = "UNAVAILABLE"
    decision_p99_latency_ms: Optional[str] = "UNAVAILABLE"
    kafka_lag_msgs: Optional[str] = "UNAVAILABLE"
    partitions: List[KafkaPartitionLag] = []
    trend_data: List[TrajectoryPoint] = []


class NodeStatus(BaseModel):
    status: str = "HEALTHY"
    source: str = "go-executor"
    node_id: str
    uptime_seconds: float
    goroutines: int
    memory_alloc_mb: float
    memory_sys_mb: float
    num_gc: int
    active_workers: int
    queue_depth: int
    throughput_ops_sec: float


class LatencyBucket(BaseModel):
    bucket: str
    count: int
    percentage: float


class SystemHealthResponse(BaseModel):
    status: str = "LIVE"
    executor_throughput: Optional[str] = "UNAVAILABLE"
    kafka_ingestion_lag: Optional[str] = "UNAVAILABLE"
    p99_execution_time: Optional[str] = "UNAVAILABLE"
    postgres_wal_sync: Optional[str] = "UNAVAILABLE"
    node_status: Optional[NodeStatus] = None
    circuit_breakers: List[CircuitBreakerOverview] = []
    kafka_partitions: List[KafkaPartitionLag] = []
    latency_histogram: List[LatencyBucket] = []


# ==========================================
# 11. Advanced Production Feature Schemas
# ==========================================

class BanditArmState(BaseModel):
    action: str
    alpha: float
    beta: float
    mean_reward: float
    variance: float
    credible_interval_95: List[float]
    successes: int
    failures: int
    total_pulls: int
    updated_at: Optional[str] = None


class BanditStateResponse(BaseModel):
    status: str = "LIVE"
    algorithm: str = "Beta-Bernoulli Thompson Sampling"
    priors: str = "Beta(1.0, 1.0) Uniform"
    total_decisions: int
    arms: List[BanditArmState]


class SHAPFeatureAttribution(BaseModel):
    feature: str
    raw_value: Any
    shap_value: float
    direction: str
    importance_rank: int


class SHAPExplanationResponse(BaseModel):
    payment_id: Optional[str] = None
    model_name: str = "RandomForestClassifier"
    base_value: float
    output_probability: float
    prediction_label: str
    attributions: List[SHAPFeatureAttribution]


class RFC6962MerkleRootResponse(BaseModel):
    root_hash: str
    tree_size: int
    latest_leaf_id: Optional[int] = None
    algorithm: str = "RFC 6962 SHA-256 Merkle Tree"
    leaf_prefix: str = "0x00"
    node_prefix: str = "0x01"
    timestamp: str


class RFC6962ProofStep(BaseModel):
    direction: str
    hash: str


class RFC6962MerkleProofResponse(BaseModel):
    payment_id: str
    leaf_index: int
    tree_size: int
    leaf_hash: str
    audit_path: List[RFC6962ProofStep]
    root_hash: str
    verified: bool


class VerifyProofRequest(BaseModel):
    leaf_hash: str
    leaf_index: int
    tree_size: int
    audit_path: List[RFC6962ProofStep]
    expected_root: str


class VerifyProofResponse(BaseModel):
    valid: bool
    computed_root: str
    expected_root: str
    message: str


class RateLimiterStatusResponse(BaseModel):
    status: str = "LIVE"
    source: str = "redis:6379"
    key: str
    limit: int
    window_seconds: int
    current_tokens: int
    remaining_tokens: int
    ttl_seconds: int
    allowed: bool


class KafkaDLQStatsResponse(BaseModel):
    status: str = "LIVE"
    topic: str = "recovery.payment.failed.dlq"
    total_dead_letters: int
    sample_dead_letters: List[Dict[str, Any]] = []


class AuditSearchAggregations(BaseModel):
    by_action: Dict[str, int] = {}
    by_outcome: Dict[str, int] = {}


class AuditSearchResultItem(BaseModel):
    payment_id: str
    customer_id: Optional[str] = None
    amount: float = 0.0
    failure_code: Optional[str] = None
    recommended_action: Optional[str] = None
    executed_action: Optional[str] = None
    chosen_action: Optional[str] = None
    expected_value: float = 0.0
    policy_allowed: bool = False
    policy_reason: Optional[str] = None
    policy_outcome: Optional[str] = None
    outcome: Optional[str] = None
    recovered: Optional[bool] = None
    execution_result: Optional[str] = None
    timestamp: str = ""
    bank: Optional[str] = None
    payment_method: Optional[str] = None


class AuditSearchResponse(BaseModel):
    total: int
    results: List[AuditSearchResultItem]
    aggregations: AuditSearchAggregations
    source: str  # "elasticsearch", "postgres", or "in_memory"
