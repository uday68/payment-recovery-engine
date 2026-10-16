from .config import ACTION
from .models import Customer, Payment
import random

def recovery_probablity(
        customer: Customer,
        payment: Payment,
        action:str,   )->float:

    """ 
    Calculates the probability of a successful recovery for a given customer, payment, and action.
    """

    probability = 0.10
    probability += customer.recovery_rate * 0.30
    probability += customer.success_rate * 0.20

    if payment.failure_code == "BANK_TIMEOUT":
        if action == "RETRY_LATER":
            probability += 0.35
        elif action == "RETRY_NOW":
            probability += 0.15

    elif payment.failure_code == "NETWORK_ERROR":
        if action  == "RETRY_NOW":
            probability += 0.15
        elif action == "RETRY_LATER":
            probability += 0.30

    elif payment.failure_code == "INSUFFICIENT_FUNDS":
        if action == "SEND_REMINDER":
            probability += 0.20
        elif action in ("RETRY_LATER", "RETRY_NOW"):
            probability -= 0.10
    elif payment.failure_code == "CARD_EXPIRED":
        if action == "SEND_REMINDER":
            probability += 0.15
        else:
            probability -= 0.15

    elif payment.failure_code == "LIMIT_EXCEEDED":
        if action == "RETRY_LATER":
            probability += 0.10
        elif action == "RETRY_NOW":
            probability -= 0.10

    elif payment.failure_code == "AUTHENTICATION_FAILED":

        if action == "SEND_REMINDER":
            probability += 0.10
    if action == "NO_ACTION":
        return 0.0
    
    return max(0.0, min(1.0, probability))

def execute_recovery(customer:Customer, payment:Payment, action:str)->bool:
    """
    Executes the recovery action for a given customer and payment.
    Returns True if the recovery is successful, False otherwise.
    """
    prob = recovery_probablity(customer, payment, action)
    return random.random() < prob
    