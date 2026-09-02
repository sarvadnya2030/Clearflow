#!/usr/bin/env python3
"""
ClearFlow Bulk Payment Sender — 1 lakh+ transactions
Simulates realistic ISO 20022 pacs.008 traffic with varied currencies, amounts, corridors.
~20% intentional failures (bad IBANs, embargoed countries, rate limits).
"""
import random, uuid, time, json, threading, sys
from concurrent.futures import ThreadPoolExecutor
import urllib.request, urllib.error

GATEWAY = "http://localhost:8080/api/v1/payments"
TOTAL    = 100_000
WORKERS  = 50          # concurrent threads
BATCH_LOG = 500        # print progress every N payments

CURRENCIES = ["EUR", "USD", "GBP", "CHF", "SGD", "AUD", "JPY", "CNY"]
CHANNELS   = ["SWIFT", "SEPA", "FEDWIRE", "CHAPS"]
RAILS      = {"EUR":"SEPA","USD":"FEDWIRE","GBP":"CHAPS","CHF":"SWIFT","SGD":"SWIFT","AUD":"SWIFT","JPY":"SWIFT","CNY":"SWIFT"}

GOOD_IBANS = [
    ("DE89370400440532013000","DE"),("DE75512108001245126199","DE"),
    ("DE44500105175407324931","DE"),("GB29NWBK60161331926819","GB"),
    ("GB82WEST12345698765432","GB"),("FR7630006000011234567890189","FR"),
    ("NL91ABNA0417164300","NL"),("CH9300762011623852957","CH"),
    ("IT60X0542811101000000123456","IT"),("ES9121000418450200051332","ES"),
    ("BE68539007547034","BE"),("GB96MIDL40051512345678","GB"),
]
EMBARGOED_IBANS = [
    ("IR123456789012345678","IR"),("SY123456789012345678","SY"),
    ("KP123456789012345678","KP"),("CU123456789012345678","CU"),
]
BAD_IBANS = [("INVALID_IBAN_001","XX"),("BAD_FORMAT_999","ZZ")]
BICS = ["DEUTDEDB","NWBKGB2L","BNPAFRPP","INGBNL2A","CHASUS33","BOFAUS3N","UBSWCHZH","OCBCSGSG"]
NAMES = ["Acme Corp","Global Trade Ltd","FinTech Solutions","Munich Holdings","London Capital",
         "Paris Finance","Amsterdam Bank","Zurich Trust","Singapore FX","Sydney Markets",
         "Tokyo Funds","Beijing Capital","Madrid Group","Rome Ventures","Brussels Asset"]

stats = {"submitted":0,"accepted":0,"rejected":0,"error":0,"conflict":0}
lock  = threading.Lock()
start_time = time.time()

def make_payment(idx: int) -> dict:
    ccy  = random.choice(CURRENCIES)
    mode = random.random()
    if mode < 0.78:                               # 78% clean
        dib, dc = random.choice(GOOD_IBANS)
        cib, cc = random.choice(GOOD_IBANS)
        while cc == dc: cib, cc = random.choice(GOOD_IBANS)
        amt = round(random.uniform(100, 500_000), 2)
    elif mode < 0.88:                              # 10% embargoed
        dib, dc = random.choice(EMBARGOED_IBANS)
        cib, cc = random.choice(GOOD_IBANS)
        amt = round(random.uniform(1000, 50_000), 2)
    else:                                          # 12% bad IBAN
        dib, dc = random.choice(BAD_IBANS)
        cib, cc = random.choice(GOOD_IBANS)
        amt = round(random.uniform(50, 5_000), 2)

    channel = RAILS.get(ccy, "SWIFT")
    return {
        "instructionId": f"BULK-{idx:07d}",
        "endToEndId":    f"E2E-{idx:07d}",
        "uetr":          str(uuid.uuid4()),
        "amount":        str(amt),
        "currency":      ccy,
        "channel":       channel,
        "debtor":  {"name": random.choice(NAMES), "iban": dib, "bic": random.choice(BICS), "country": dc[:2]},
        "creditor":{"name": random.choice(NAMES), "iban": cib, "bic": random.choice(BICS), "country": cc[:2]},
    }

def send_one(idx: int):
    payload = make_payment(idx)
    data    = json.dumps(payload).encode()
    req     = urllib.request.Request(GATEWAY, data=data,
                headers={"Content-Type":"application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            status = r.status
            with lock:
                stats["submitted"] += 1
                if status == 202: stats["accepted"] += 1
                elif status == 409: stats["conflict"] += 1
                else: stats["rejected"] += 1
    except urllib.error.HTTPError as e:
        with lock:
            stats["submitted"] += 1
            if e.code in (400,422): stats["rejected"] += 1
            elif e.code == 429:     stats["error"] += 1   # rate limited
            else:                   stats["error"] += 1
    except Exception:
        with lock:
            stats["error"] += 1

    with lock:
        n = stats["submitted"] + stats["error"]
        if n % BATCH_LOG == 0:
            elapsed = time.time() - start_time
            tps = n / elapsed if elapsed > 0 else 0
            print(f"[{n:>7}/{TOTAL}] acc={stats['accepted']} rej={stats['rejected']} "
                  f"err={stats['error']} tps={tps:.1f}", flush=True)

def main():
    print(f"ClearFlow Bulk Sender: {TOTAL:,} payments | {WORKERS} workers | gateway={GATEWAY}")
    print("Starting in 3 seconds... (Ctrl+C to stop)")
    time.sleep(3)

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        list(pool.map(send_one, range(1, TOTAL + 1)))

    elapsed = time.time() - start_time
    print(f"\n=== COMPLETE in {elapsed:.1f}s ===")
    print(f"  Accepted : {stats['accepted']:>7,}")
    print(f"  Rejected : {stats['rejected']:>7,}")
    print(f"  Conflicts: {stats['conflict']:>7,}")
    print(f"  Errors   : {stats['error']:>7,}")
    print(f"  Avg TPS  : {TOTAL/elapsed:.1f}")

if __name__ == "__main__":
    main()
