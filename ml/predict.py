import pandas as pd
from pathlib import Path
from backend.decision.engine import choose_action

_MODEL_CACHE = None

def get_or_load_model():
    global _MODEL_CACHE
    if _MODEL_CACHE is not None:
        return _MODEL_CACHE

    try:
        from .model_store import load_model
        _MODEL_CACHE = load_model()
    except Exception:
        from .train import train_model
        _MODEL_CACHE = train_model()
    return _MODEL_CACHE

def predict_action_probabilities(payment_context, model=None):
    if model is None:
        model = get_or_load_model()

    predictions = {}

    actions = [
        "RETRY_NOW",
        "RETRY_LATER",
        "SEND_REMINDER",
        "NO_ACTION",
    ]

    for action in actions:

        context = payment_context.copy()
        context["action"] = action

        probability = model.predict_proba(
            pd.DataFrame([context])
        )[0][1]

        predictions[action] = probability

    return predictions


if __name__ == "__main__":

    payment = {
        "success_rate": 0.85,
        "recovery_rate": 0.60,
        "amount": 3000,
        "payment_method": "UPI",
        "bank": "HDFC",
        "failure_code": "BANK_TIMEOUT",
        "hour": 14,
    }

    predictions = predict_action_probabilities(payment)

    print("RECOVERY PREDICTIONS")
    print("====================")

    for action, probability in predictions.items():
        print(
            f"{action:<20} "
            f"{probability:.2%}"
        )

    result = choose_action(
        amount=payment["amount"],
        probabilities=predictions,
    )

    print("\nDECISION")
    print("====================")
    print(f"Selected action: {result['action']}")
    print(
        f"Expected value: "
        f"₹{result['expected_value']:.2f}"
    )

    print("\nACTION VALUES")

    for action, value in result["all_values"].items():
        print(
            f"{action:<20} "
            f"₹{value:.2f}"
        )
    