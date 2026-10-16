import pandas as pd
from pathlib import Path

from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.calibration import CalibratedClassifierCV
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


NUMERIC_FEATURES = [
    "success_rate",
    "recovery_rate",
    "amount",
    "hour",
]

CATEGORICAL_FEATURES = [
    "payment_method",
    "bank",
    "failure_code",
    "action",
]


def build_pipeline(
    model_type: str = "random_forest",
    calibrate: bool = False,
    calibrate_cv: int = 3,
    calibration_method: str = "sigmoid",
):
    preprocessor = ColumnTransformer(
        transformers=[
            (
                "numeric",
                StandardScaler(),
                NUMERIC_FEATURES,
            ),
            (
                "categorical",
                OneHotEncoder(
                    handle_unknown="ignore"
                ),
                CATEGORICAL_FEATURES,
            ),
        ]
    )

    if model_type == "dummy":
        base_model = DummyClassifier(strategy="prior")
    elif model_type == "logistic":
        base_model = LogisticRegression(max_iter=1000, random_state=42)
    elif model_type == "random_forest":
        base_model = RandomForestClassifier(
            n_estimators=100,
            random_state=42,
            n_jobs=-1,
        )
    else:
        raise ValueError(f"Unknown model_type: {model_type}")

    if calibrate and model_type != "dummy":
        cv = calibrate_cv if calibrate_cv is not None else 3
        estimator = CalibratedClassifierCV(base_model, method=calibration_method, cv=cv)
    else:
        estimator = base_model

    return Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            ("model", estimator),
        ]
    )


def load_dataset(path=None):
    if path is None:
        # Resolve path relative to this module's location
        path = Path(__file__).parent / "data.csv"
    return pd.read_csv(path)


def train_model(path=None):
    df = load_dataset(path)

    X = df[
        NUMERIC_FEATURES +
        CATEGORICAL_FEATURES
    ]

    y = df["success"]
    

    pipeline = build_pipeline()

    pipeline.fit(X, y)

    return pipeline

if __name__ == "__main__":
    model = train_model()
    save_path = Path(__file__).parent / "model.pkl"
    try:
        from .model_store import save_model
    except ImportError:
        from model_store import save_model
    save_model(model, save_path)
    print("Model trained successfully.")