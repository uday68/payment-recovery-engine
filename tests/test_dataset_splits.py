import pytest
import pandas as pd
from ml.dataset import generate_dataset, split_grouped, validate_no_leakage, generate_observational_dataset


def test_split_grouped_prevents_payment_id_leakage():
    df = generate_dataset(num_customers=20, num_payments=50, trials_per_action=2)
    train_df, test_df = split_grouped(df, group_col="payment_id", test_size=0.25, random_state=42)

    assert len(train_df) > 0
    assert len(test_df) > 0
    assert len(train_df) + len(test_df) == len(df)

    validation = validate_no_leakage(train_df, test_df, group_cols=["payment_id"])
    assert validation["payment_id"]["leakage_free"] is True
    assert validation["payment_id"]["overlap_count"] == 0


def test_validate_no_leakage_detects_leakage():
    df = generate_dataset(num_customers=10, num_payments=20, trials_per_action=1)
    # Intentionally leak by splitting randomly without grouping
    train_df = df.iloc[:15]
    test_df = df.iloc[10:]  # Overlaps indices 10-14

    with pytest.raises(ValueError, match="Data leakage detected"):
        validate_no_leakage(train_df, test_df, group_cols=["payment_id"])


def test_generate_observational_dataset():
    obs_df = generate_observational_dataset(num_customers=30, num_payments=100, random_state=42)
    assert len(obs_df) > 0
    # In observational data, each payment_id appears exactly once
    assert obs_df["payment_id"].nunique() == len(obs_df)
    assert set(obs_df["success"].unique()).issubset({0, 1})
