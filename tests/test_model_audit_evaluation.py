import numpy as np
import pytest
from ml.evaluate import compute_ece, evaluate_predictions, audit_models_cross_validation
from ml.dataset import generate_dataset


def test_compute_ece_perfect_calibration():
    # Exactly half 0s and half 1s with confidence 0.5
    y_true = np.array([0, 1, 0, 1, 0, 1])
    y_prob = np.array([0.5, 0.5, 0.5, 0.5, 0.5, 0.5])
    ece = compute_ece(y_true, y_prob, n_bins=5)
    assert pytest.approx(ece, abs=1e-5) == 0.0


def test_compute_ece_uncalibrated():
    # All 0s but model predicted 1.0 confidence
    y_true = np.array([0, 0, 0, 0])
    y_prob = np.array([1.0, 1.0, 1.0, 1.0])
    ece = compute_ece(y_true, y_prob, n_bins=5)
    assert pytest.approx(ece, abs=1e-5) == 1.0


def test_evaluate_predictions_keys():
    y_true = np.array([0, 1, 1, 0])
    y_prob = np.array([0.1, 0.9, 0.8, 0.2])
    res = evaluate_predictions(y_true, y_prob)
    for expected_key in ["roc_auc", "pr_auc", "brier_score", "log_loss", "ece", "accuracy", "f1"]:
        assert expected_key in res
        assert 0.0 <= res[expected_key] <= 1.0 or expected_key == "log_loss"


def test_audit_models_cross_validation_small():
    df = generate_dataset(num_customers=10, num_payments=20, trials_per_action=1)
    summary = audit_models_cross_validation(df=df, n_splits=3, group_col="payment_id")
    assert "Dummy (Prior)" in summary
    assert "Logistic Regression (L2)" in summary
    assert "Random Forest (Raw - Preferred)" in summary
    assert "Random Forest (Sigmoid Calibrated)" in summary
    assert "Random Forest (Isotonic Calibrated)" in summary

    for model_name, metrics in summary.items():
        assert "roc_auc" in metrics
        assert "brier_score" in metrics
        assert "mean" in metrics["roc_auc"]
        assert "std" in metrics["roc_auc"]


def test_raw_rf_probability_dynamic_range():
    from ml.train import build_pipeline
    df = generate_dataset(num_customers=20, num_payments=40, trials_per_action=1)
    X = df[["success_rate", "recovery_rate", "amount", "payment_method", "bank", "failure_code", "hour", "action"]]
    y = df["success"].values

    pipe = build_pipeline("random_forest", calibrate=False)
    pipe.fit(X, y)
    probs = pipe.predict_proba(X)[:, 1]

    # Raw Random Forest must not have artificially compressed probabilities
    assert np.min(probs) <= 0.05
    assert np.max(probs) >= 0.75
    # Proper scoring rule: Brier score must be better than trivial coin-flip 0.25
    brier = np.mean((probs - y) ** 2)
    assert brier < 0.20
