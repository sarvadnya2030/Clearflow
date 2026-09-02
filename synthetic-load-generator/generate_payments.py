import argparse, asyncio, random, time, uuid
from datetime import datetime, timedelta
import aiohttp, numpy as np, pandas as pd
from faker import Faker
from tqdm.asyncio import tqdm
import jwt

SEPA_COUNTRIES = ["DE","FR","NL","ES","IT","BE","AT","PT","FI","IE","GR","LU",
                  "SK","SI","EE","LV","LT","MT","CY","PL","CZ","HU","RO","BG",
                  "HR","SE","DK","NO","CH","IS","LI","MC","SM","GB"]

HIGH_RISK_COUNTRIES = ["IR","KP","SY","CU","SD","MM","RU","BY","AF","IQ"]
CURRENCIES = [("EUR",0.40),("USD",0.30),("GBP",0.15),("CHF",0.05),("JPY",0.05),("SGD",0.05)]
SDN_CLOSE_NAMES = ["AL QAIDA NETWORK","IBRAHIM AL ASIRI","HAMAS MOVEMENT","HEZBOLLAH ORG","ISLAMIC STATE","REVOLUTIONARY GUARD"]


def generate_iban(country: str) -> str:
    bban_length = {"DE":18,"FR":23,"NL":14,"GB":18,"US":16,"ES":20,"IT":23}
    length = bban_length.get(country, 16)
    bban = ''.join([str(random.randint(0,9)) for _ in range(length)])
    iban_without_check = country + "00" + bban
    rearranged = iban_without_check[4:] + iban_without_check[:4]
    numeric = ''.join([str(ord(c)-55) if c.isalpha() else c for c in rearranged])
    check_digits = 98 - (int(numeric) % 97)
    return country + str(check_digits).zfill(2) + bban


def generate_payment(fake: Faker, index: int) -> dict:
    currency, _ = random.choices(CURRENCIES, weights=[w for _, w in CURRENCIES])[0]
    amount = round(np.random.lognormal(mean=6.2, sigma=1.8), 2)
    amount = max(0.01, min(amount, 9999999.99))
    debtor_country = random.choices(SEPA_COUNTRIES + HIGH_RISK_COUNTRIES, weights=[5] * len(SEPA_COUNTRIES) + [1] * len(HIGH_RISK_COUNTRIES))[0]
    cross_border = random.random() < 0.15
    creditor_country = random.choice(["US","GB","SG","JP","HK","AU","CA"]) if cross_border else random.choice(SEPA_COUNTRIES)
    if random.random() < 0.05:
        creditor_country = random.choice(HIGH_RISK_COUNTRIES)

    if random.random() < 0.02:
        debtor_name = random.choice(SDN_CLOSE_NAMES)
    else:
        debtor_name = fake.name().upper()

    creditor_name = fake.name().upper()

    return {
        "instructionId": str(uuid.uuid4()),
        "endToEndId": f"E2E-{index:08d}-{int(time.time())}",
        "uetr": str(uuid.uuid4()),
        "debtor": {
            "name": debtor_name,
            "iban": generate_iban(debtor_country),
            "bic": f"{''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ',k=4))}{debtor_country}{''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789',k=2))}",
            "country": debtor_country
        },
        "creditor": {
            "name": creditor_name,
            "iban": generate_iban(creditor_country),
            "bic": f"{''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ',k=4))}{creditor_country}{''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789',k=2))}",
            "country": creditor_country
        },
        "amount": amount,
        "currency": currency,
        "valueDate": (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d"),
        "purpose": random.choice(["SUPP","SALA","PENS","DIVI","TRAD","LOAN","CORT"]),
        "remittanceInfo": f"Payment {index} - {fake.bs()[:50]}",
        "channel": random.choice(["SWIFT","SEPA","FEDWIRE","FASTER_PAYMENTS","INTERNAL"])
    }


def generate_jwt(secret: str = "clearflow-dev-secret") -> str:
    payload = {
        "sub": f"client-{random.randint(1000,9999)}",
        "iss": "http://localhost:8080/auth",
        "aud": "clearflow-gateway",
        "exp": int(time.time()) + 3600,
        "iat": int(time.time()),
        "scope": "payment:write"
    }
    return jwt.encode(payload, secret, algorithm="HS256")


async def send_payment(session, url, payment, token, semaphore, stats):
    async with semaphore:
        try:
            start = time.time()
            async with session.post(url, json=payment, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "X-Correlation-Id": str(uuid.uuid4())}, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                latency = (time.time() - start) * 1000
                stats["total"] += 1
                stats["latencies"].append(latency)
                if resp.status == 202:
                    stats["success"] += 1
                elif resp.status == 409:
                    stats["duplicate"] += 1
                elif resp.status == 429:
                    stats["ratelimited"] += 1
                else:
                    stats["error"] += 1
        except Exception as e:
            stats["error"] += 1
            stats["errors"].append(str(e))


async def main():
    parser = argparse.ArgumentParser(description="ClearFlow Synthetic Payment Generator")
    parser.add_argument("--count", type=int, default=100000)
    parser.add_argument("--concurrency", type=int, default=200)
    parser.add_argument("--url", default="http://localhost:8080/api/v1/payments")
    parser.add_argument("--secret", default="clearflow-dev-secret")
    parser.add_argument("--duplicate-rate", type=float, default=0.03)
    args = parser.parse_args()

    fake = Faker()
    stats = {"total":0,"success":0,"duplicate":0,"ratelimited":0,"error":0,"latencies":[],"errors":[]}
    payments = [generate_payment(fake, i) for i in range(args.count)]

    dup_count = int(args.count * args.duplicate_rate)
    for _ in range(dup_count):
        payments.append(payments[random.randint(0, len(payments)-1)].copy())

    random.shuffle(payments)
    token = generate_jwt(args.secret)
    semaphore = asyncio.Semaphore(args.concurrency)

    start_time = time.time()
    async with aiohttp.ClientSession() as session:
        tasks = [send_payment(session, args.url, p, token, semaphore, stats) for p in payments]
        await tqdm.gather(*tasks, desc="Sending payments")

    elapsed = time.time() - start_time
    tps = stats["total"] / elapsed if elapsed else 0

    lat = sorted(stats["latencies"]) if stats["latencies"] else [0]
    summary_file = f"generate_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    pd.DataFrame([{
        "timestamp": datetime.now().isoformat(),
        "total_sent": stats["total"], "success": stats["success"],
        "duplicates": stats["duplicate"], "errors": stats["error"],
        "tps": round(tps, 2), "elapsed_seconds": round(elapsed, 2),
        "p50_ms": round(lat[len(lat)//2], 2),
        "p99_ms": round(lat[int(len(lat)*0.99)], 2)
    }]).to_csv(summary_file, index=False)

    print(f"RESULTS total={stats['total']} success={stats['success']} duplicate={stats['duplicate']} ratelimited={stats['ratelimited']} errors={stats['error']} tps={tps:.0f}")
    print(f"Summary written to {summary_file}")


if __name__ == "__main__":
    asyncio.run(main())
