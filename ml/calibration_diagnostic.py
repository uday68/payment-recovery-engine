import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold
from ml.train import load_dataset, NUMERIC_FEATURES, CATEGORICAL_FEATURES
from sklearn.calibration import calibration_curve, CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from ml.evaluate import compute_ece, evaluate_predictions


def main():
    df = load_dataset()
    X = df[NUMERIC_FEATURES + CATEGORICAL_FEATURES]
    y = df['success'].values
    groups = df['payment_id'].values

    gkf = GroupKFold(n_splits=5)
    train_idx, val_idx = next(gkf.split(X, y, groups=groups))
    X_train, y_train = X.iloc[train_idx], y[train_idx]
    X_val, y_val = X.iloc[val_idx], y[val_idx]

    prep = ColumnTransformer([
        ('num', StandardScaler(), NUMERIC_FEATURES),
        ('cat', OneHotEncoder(handle_unknown='ignore'), CATEGORICAL_FEATURES)
    ])

    models = {
        'Logistic Regression': Pipeline([
            ('prep', prep),
            ('clf', LogisticRegression(max_iter=1000, random_state=42))
        ]),
        'Raw Random Forest': Pipeline([
            ('prep', prep),
            ('clf', RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=-1))
        ]),
        'Sigmoid RF (Platt)': Pipeline([
            ('prep', prep),
            ('clf', CalibratedClassifierCV(RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=-1), method='sigmoid', cv=3))
        ]),
        'Isotonic RF': Pipeline([
            ('prep', prep),
            ('clf', CalibratedClassifierCV(RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=-1), method='isotonic', cv=3))
        ]),
    }

    print("=== CALIBRATION DIAGNOSTIC ON IDENTICAL GROUPED VALIDATION FOLD ===")
    base_rate = float(np.mean(y_val))
    uncertainty = base_rate * (1 - base_rate)
    print(f"Validation Base Rate: {base_rate:.4f} | Target Uncertainty Var(Y): {uncertainty:.4f}\n")

    for name, model in models.items():
        model.fit(X_train, y_train)
        probs = model.predict_proba(X_val)[:, 1]
        metrics = evaluate_predictions(y_val, probs)

        prob_true, prob_pred = calibration_curve(y_val, probs, n_bins=5, strategy='uniform')

        print(f"--- {name} ---")
        print(f"  ROC-AUC:     {metrics['roc_auc']:.4f}")
        print(f"  PR-AUC:      {metrics['pr_auc']:.4f}")
        print(f"  Brier Score: {metrics['brier_score']:.4f}")
        print(f"  Log Loss:    {metrics['log_loss']:.4f}")
        print(f"  ECE (10 bin):{metrics['ece']:.4f}")
        quantiles = [np.min(probs), np.percentile(probs, 25), np.median(probs), np.percentile(probs, 75), np.max(probs)]
        print(f"  Quantiles [min, p25, median, p75, max]: [{quantiles[0]:.3f}, {quantiles[1]:.3f}, {quantiles[2]:.3f}, {quantiles[3]:.3f}, {quantiles[4]:.3f}]")
        print(f"  Proportion p > 0.5: {float(np.mean(probs > 0.5)):.4f} | Recall: {metrics['recall']:.4f} | Precision: {metrics['precision']:.4f}")
        print("  Reliability Bins (predicted -> observed true):")
        for p_p, p_t in zip(prob_pred, prob_true):
            print(f"    Pred: {p_p:.3f} -> True: {p_t:.3f} | Calibration Gap: {abs(p_p - p_t):.3f}")
        print()


if __name__ == '__main__':
    main()
