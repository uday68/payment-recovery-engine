"""
Data generator module for payment simulation.
Generates synthetic customer profiles and payment transactions with realistic
failure scenarios for testing the recovery engine.
"""

import random
import uuid

from datetime import datetime, timedelta
from .models import Customer, Payment
from .config import *

def generate_customers(num_customers:int)->list[Customer]:
    customers =[]
    # for _ in range(num_customers):
    #     successful_payments = random.randint(5, 100)
    #     failed_payments = random.randint(0, 20)
    #     recovered_payments = random.randint(0, failed_payments)
    #     customers.append(
    #         Customer(
    #         id = str(uuid.UUID(int=random.getrandbits(128))),
    #         successful_payments=successful_payments,
    #         failed_payments=failed_payments,
    #         recovered_payments=recovered_payments))
    for _ in range(num_customers):
        #each customer has an underlying behavioral profile
        #this hidden value represent how reliably they pay

        reliability = random.uniform(0.65,0.98)
        total_payments  = random.randint(20,150)

        successful =0
        failed =0
        recovered =0

        for _ in range(total_payments):
            if random.random()  < reliability:
                successful += 1
                continue
            failed +=1

            #customer differe in how likely they are
            #to recover after a failed payment.
            recovery_chance = random.uniform(0.20,0.80)
            if random.random()  < recovery_chance:
                recovered+=1

        customers.append(
            Customer(
                id=str(uuid.uuid4()),
                successful_payments=successful,
                failed_payments=failed,
                recovered_payments=recovered,
            )
        )

    return customers

def generate_payments(customers:list[Customer], num_payments:int)->list[Payment]:
    payments = []
    start = datetime(2025, 1, 1, 0, 0, 0)
    for _ in range(num_payments):
        customer = random.choice(customers)
        amount  = round(random.uniform(100, 10000), 2)
        payment_method = random.choice(PAYMENT_METHODS)
        bank = random.choice(BANKS)

        failed = random.random() < 0.3

        if failed :
            failure_code = random.choice(FAILURE_CODES)
            status = "FAILED"
        else:
            failure_code =None
            status ="SUCCESS"
        timestamps = start + timedelta(seconds=random.randint(0,90*24*60*60))
        payments.append( 
            Payment(
                id = str(uuid.UUID(int=random.getrandbits(128))),
                customer_id = customer.id,
                amount = amount,
                payment_method = payment_method,
                bank = bank,
                failure_code = failure_code,
                timestamp = timestamps,
                status = status,
            )
        )
    return payments
    