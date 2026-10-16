"""
Evaluation and Auditing Engine for Payment Recovery ML Models.
Performs leak-free GroupKFold cross-validation across baselines,
computes calibration metrics (ECE, Brier score), and audits discriminative power.
"""
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import (
    roc_auc_score,
    average_precision_score,
    brier_score_loss,
    log_loss,
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
)
from sklearn.model_selection import GroupKFold
from ml.train import build_pipeline, NUMERIC_FEATURES, CATEGORICAL_FEATURES, load_dataset


def compute_ece(y_true: np.ndarray, y_prob: np.ndarray, n_bins: int = 10) -> float:
    """
    Computes Expected Calibration Error (ECE):
    ECE = sum_{b=1}^B (|B_b| / N) * |acc(B_b) - conf(B_b)|
    """
    bin_limits = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    total_samples = len(y_true)

    for i in range(n_bins):
        low, high = bin_limits[i], bin_limits[i + 1]
        mask = (y_prob >= low) & (y_prob <= high if i == n_bins - 1 else y_prob < high)
        bin_count = np.sum(mask)

        if bin_count > 0:
            bin_acc = np.mean(y_true[mask])
            bin_conf = np.mean(y_prob[mask])
            ece += (bin_count / total_samples) * abs(bin_acc - bin_conf)

    return float(ece)


def evaluate_predictions(y_true: np.ndarray, y_prob: np.ndarray) -> dict:
    """
    Computes complete classification and calibration metric battery.
    """
    y_pred = (y_prob >= 0.5).astype(int)
    y_prob_clipped = np.clip(y_prob, 1e-15, 1 - 1e-15)

    return {
        "roc_auc": float(roc_auc_score(y_true, y_prob)),
        "pr_auc": float(average_precision_score(y_true, y_prob)),
        "brier_score": float(brier_score_loss(y_true, y_prob)),
        "log_loss": float(log_loss(y_true, y_prob_clipped)),
        "ece": float(compute_ece(y_true, y_prob)),
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
    }


def audit_models_cross_validation(
    df: pd.DataFrame = None,
    n_splits: int = 5,
    group_col: str = "payment_id",
) -> dict:
    """
    Audits multiple model architectures using leak-free GroupKFold CV.
    Guarantees no payment_id appears in both train and validation splits.
    """
    if df is None:
        df = load_dataset()

    X = df[NUMERIC_FEATURES + CATEGORICAL_FEATURES]
    y = df["success"].values
    groups = df[group_col].values

    gkf = GroupKFold(n_splits=n_splits)

    results = {
        "Dummy (Prior)": [],
        "Logistic Regression (L2)": [],
        "Random Forest (Raw - Preferred)": [],
        "Random Forest (Sigmoid Calibrated)": [],
        "Random Forest (Isotonic Calibrated)": [],
    }

    for fold, (train_idx, val_idx) in enumerate(gkf.split(X, y, groups=groups), 1):
        X_train, y_train = X.iloc[train_idx], y[train_idx]
        X_val, y_val = X.iloc[val_idx], y[val_idx]

        # Verify zero leakage across folds
        train_groups = set(groups[train_idx])
        val_groups = set(groups[val_idx])
        assert len(train_groups.intersection(val_groups)) == 0, f"Leakage detected in fold {fold}!"

        min_class = int(np.min(np.bincount(y_train))) if len(np.bincount(y_train)) > 1 else 0
        cal_cv = min(3, min_class)

        models = {
            "Dummy (Prior)": build_pipeline(model_type="dummy"),
            "Logistic Regression (L2)": build_pipeline(model_type="logistic"),
            "Random Forest (Raw - Preferred)": build_pipeline(model_type="random_forest", calibrate=False),
            "Random Forest (Sigmoid Calibrated)": build_pipeline(
                model_type="random_forest",
                calibrate=(cal_cv >= 2),
                calibrate_cv=max(2, cal_cv),
                calibration_method="sigmoid",
            ),
            "Random Forest (Isotonic Calibrated)": build_pipeline(
                model_type="random_forest",
                calibrate=(cal_cv >= 2),
                calibrate_cv=max(2, cal_cv),
                calibration_method="isotonic",
            ),
        }

        for name, model in models.items():
            model.fit(X_train, y_train)
            probs = model.predict_proba(X_val)[:, 1]
            metrics = evaluate_predictions(y_val, probs)
            results[name].append(metrics)

    summary = {}
    for name, fold_metrics in results.items():
        summary[name] = {}
        for metric_key in fold_metrics[0].keys():
            vals = [m[metric_key] for m in fold_metrics]
            summary[name][metric_key] = {
                "mean": float(np.mean(vals)),
                "std": float(np.std(vals)),
            }

    return summary
