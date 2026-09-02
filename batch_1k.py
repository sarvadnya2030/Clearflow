#!/usr/bin/env python3
"""ClearFlow 1K payment test — 2 batches × 500"""
import json, random, sys, time, uuid, threading
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import requests
except ImportError:
    print("pip install requests"); sys.exit(1)

GATEWAY    = "http://localhost:8080"
BATCH_SIZE = 500
NUM_BATCHES = 2
WORKERS    = 5
COOLDOWN   = 1

CLEAN = [
    {"name": "Alpine Logistics",  "iban": "DE89370400440532013000",      "bic": "DEUTDEDBXXX", "country": "DE"},
    {"name": "Euro Trade SARL",   "iban": "FR7630006000011234567890189",  "bic": "BNPAFRPPXXX", "country": "FR"},
    {"name": "HSBC Holdings PLC", "iban": "GB29NWBK60161331926819",      "bic": "HBUKGB4BXXX", "country": "GB"},
    {"name": "ING Bank NV",       "iban": "NL91ABNA0417164300",          "bic": "INGBNL2AXXX", "country": "NL"},
    {"name": "Banco Santander",   "iban": "ES9121000418450200051332",     "bic": "BSCHESMMXXX", "country": "ES"},
]

def get_token():
    r = requests.post(f"{GATEWAY}/auth/token",
        json={"clientId":"clearflow-demo","clientSecret":"demo-secret-2024","grantType":"client_credentials"},
        timeout=5)
    if r.status_code == 200: return r.json().get("access_token","")
    return ""

def send_payment(token, pid):
    debtor  = random.choice(CLEAN)
    creditor = random.choice([c for c in CLEAN if c != debtor])
    payload = {
        "paymentId": pid, "instructionId": f"INSTR-{pid[:8]}",
        "endToEndId": f"E2E-{pid[:8]}", "uetr": str(uuid.uuid4()),
        "amount": round(random.uniform(100, 50000), 2),
        "currency": random.choice(["EUR","GBP","USD"]),
        "channel": random.choice(["SWIFT","SEPA","FASTER_PAYMENTS"]),
        "debtor":   {"name": debtor["name"],   "iban": debtor["iban"],   "bic": debtor["bic"],   "country": debtor["country"]},
        "creditor": {"name": creditor["name"], "iban": creditor["iban"], "bic": creditor["bic"], "country": creditor["country"]},
        "remittanceInfo": f"Payment {pid[:8]}"
    }
    try:
        r = requests.post(f"{GATEWAY}/api/v1/payments",
            json=payload, headers={"Authorization": f"Bearer {token}"},
            timeout=10)
        return r.status_code
    except: return 0

token = get_token()
sent = accepted = err4xx = err5xx = conn_err = 0
start = time.time()
print(f"1K Payment Test — {NUM_BATCHES} batches × {BATCH_SIZE}")
for batch in range(1, NUM_BATCHES + 1):
    ids = [str(uuid.uuid4()) for _ in range(BATCH_SIZE)]
    results = []
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(send_payment, token, pid): pid for pid in ids}
        for f in as_completed(futs):
            code = f.result()
            sent += 1
            if code == 202: accepted += 1
            elif 400 <= code < 500: err4xx += 1
            elif code >= 500: err5xx += 1
            else: conn_err += 1
    pct = round(accepted/sent*100, 1) if sent else 0
    print(f"  Batch {batch:2d} | Accept%: {pct}% | Sent: {sent}")
    if batch < NUM_BATCHES: time.sleep(COOLDOWN)

elapsed = time.time() - start
print(f"\nFINAL: Sent={sent} Accepted={accepted} Rate={round(accepted/sent*100,1)}%")
print(f"Errors: 4xx={err4xx} 5xx={err5xx} Conn={conn_err}")
print(f"Time: {elapsed:.1f}s")
