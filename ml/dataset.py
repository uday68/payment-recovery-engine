import csv
import random
import sys
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from simulator.generator import (
    generate_customers,
    generate_payments,
)
from simulator.recovery import (
    execute_recovery,
)
from simulator.config import ACTION as ACTIONS


def generate_dataset(
    num_customers: int = 20,
    num_payments: int = 50,
    trials_per_action: int = 5,
    **kwargs,
):
    if "customer_count" in kwargs:
        num_customers = kwargs["customer_count"]
    if "payment_count" in kwargs:
        num_payments = kwargs["payment_count"]

    customers = generate_customers(num_customers)
    payments = generate_payments(customers, num_payments)

    customer_map = {
        customer.id: customer
        for customer in customers
    }

    rows = []

    for payment in payments:
        if payment.status != "FAILED":
            continue

        customer = customer_map[payment.customer_id]

        for action in ACTIONS:
            for _ in range(trials_per_action):
                success = execute_recovery(
                    customer,
                    payment,
                    action,
                )

                rows.append(
                    {
                        "payment_id": payment.id,
                        "customer_id": customer.id,
                        "success_rate": customer.success_rate,
                        "recovery_rate": customer.recovery_rate,
                        "amount": payment.amount,
                        "payment_method": payment.payment_method,
                        "bank": payment.bank,
                        "failure_code": payment.failure_code,
                        "hour": payment.timestamp.hour,
                        "action": action,
                        "success": int(success),
                    }
                )

    random.shuffle(rows)

    return pd.DataFrame(rows)


def build_dataset(
    customer_count: int = 1000,
    payment_count: int = 10000,
):
    df = generate_dataset(
        num_customers=customer_count,
        num_payments=payment_count,
        trials_per_action=1,
    )
    return df.to_dict(orient="records")


def save_dataset(
    rows,
    filename: str = "data.csv",
):
    if isinstance(rows, pd.DataFrame):
        rows.to_csv(filename, index=False)
        return
    if not rows:
        return

    fieldnames = rows[0].keys()

    with open(
        filename,
        "w",
        newline="",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
        )

        writer.writeheader()
        writer.writerows(rows)


def generate_observational_dataset(
    num_customers: int = 1000,
    num_payments: int = 10000,
    policy_fn=None,
    random_state: int = 42,
) -> pd.DataFrame:
    """
    Generates an observational payment failure log where each payment
    experiences only ONE logged action and outcome (reflecting real production logs).
    """
    import random
    rng = random.Random(random_state)

    customers = generate_customers(num_customers)
    payments = generate_payments(customers, num_payments)
    customer_map = {c.id: c for c in customers}

    rows = []
    for payment in payments:
        if payment.status != "FAILED":
            continue
        customer = customer_map[payment.customer_id]

        if policy_fn is not None:
            action = policy_fn(payment, customer)
        else:
            action = rng.choice(ACTIONS)

        success = execute_recovery(customer, payment, action)
        rows.append(
            {
                "payment_id": payment.id,
                "customer_id": customer.id,
                "success_rate": customer.success_rate,
                "recovery_rate": customer.recovery_rate,
                "amount": payment.amount,
                "payment_method": payment.payment_method,
                "bank": payment.bank,
                "failure_code": payment.failure_code,
                "hour": payment.timestamp.hour if payment.timestamp else 0,
                "action": action,
                "success": int(success),
                "timestamp": payment.timestamp.isoformat() if payment.timestamp else None,
            }
        )

    return pd.DataFrame(rows)


def split_grouped(
    df: pd.DataFrame,
    group_col: str = "payment_id",
    test_size: float = 0.2,
    random_state: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Splits a DataFrame into train and test sets strictly grouped by group_col,
    guaranteeing zero group leakage between splits.
    """
    from sklearn.model_selection import GroupShuffleSplit
    gss = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=random_state)
    groups = df[group_col]
    train_idx, test_idx = next(gss.split(df, groups=groups))
    return df.iloc[train_idx].copy().reset_index(drop=True), df.iloc[test_idx].copy().reset_index(drop=True)


def validate_no_leakage(
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    group_cols: list[str] = ("payment_id",),
) -> dict:
    """
    Validates that there is zero overlap between train and test groups.
    Raises ValueError if leakage is detected.
    """
    results = {}
    for col in group_cols:
        if col in train_df.columns and col in test_df.columns:
            train_groups = set(train_df[col].unique())
            test_groups = set(test_df[col].unique())
            overlap = train_groups.intersection(test_groups)
            results[col] = {
                "train_unique": len(train_groups),
                "test_unique": len(test_groups),
                "overlap_count": len(overlap),
                "leakage_free": len(overlap) == 0,
            }
            if len(overlap) > 0:
                raise ValueError(
                    f"Data leakage detected in column '{col}': {len(overlap)} groups overlap between train and test splits!"
                )
    return results


if __name__ == "__main__":
    data_path = Path(__file__).parent / "data.csv"
    df = generate_dataset(
        num_customers=1000,
        num_payments=10000,
        trials_per_action=5,
    )

    save_dataset(df, filename=str(data_path))

    print("DATASET GENERATED")
    print("=================")
    print(f"Rows: {len(df):,}")