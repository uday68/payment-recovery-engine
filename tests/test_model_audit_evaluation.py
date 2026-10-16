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
    assert "Logistic Regression" in summary
    assert "Random Forest (Raw)" in summary
    assert "Random Forest (Calibrated)" in summary

    for model_name, metrics in summary.items():
        assert "roc_auc" in metrics
        assert "brier_score" in metrics
        assert "mean" in metrics["roc_auc"]
        assert "std" in metrics["roc_auc"]
