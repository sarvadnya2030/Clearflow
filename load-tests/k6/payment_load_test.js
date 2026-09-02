/**
 * ClearFlow Payment Load Test — k6
 *
 * Scenarios:
 *  1. ramp-up   : 0 → 50 VUs over 2 min
 *  2. sustained : 50 VUs for 5 min (target ~200 TPS)
 *  3. spike     : 50 → 200 VUs for 1 min
 *  4. ramp-down : 200 → 0 VUs over 1 min
 *
 * SLA thresholds:
 *  - http_req_duration p(99) < 500ms
 *  - http_req_duration p(95) < 200ms
 *  - error rate < 1%
 *  - HTTP 202 rate > 95%
 *
 * Run:
 *   k6 run load-tests/k6/payment_load_test.js
 *   k6 run --out influxdb=http://localhost:8086/clearflow load-tests/k6/payment_load_test.js
 */

import http from "k6/http";
import { check, sleep } from "k6";
import { Counter, Rate, Trend } from "k6/metrics";
import { uuidv4 } from "https://jslib.k6.io/k6-utils/1.4.0/index.js";

// ── Custom metrics ──────────────────────────────────────────
const paymentAccepted  = new Counter("clearflow_payment_accepted");
const paymentRejected  = new Counter("clearflow_payment_rejected");
const duplicateHit     = new Counter("clearflow_payment_duplicate");
const rateLimitHit     = new Counter("clearflow_payment_rate_limited");
const acceptRate       = new Rate("clearflow_payment_accept_rate");
const paymentDuration  = new Trend("clearflow_payment_duration_ms", true);

// ── Config ──────────────────────────────────────────────────
const GATEWAY_URL = __ENV.GATEWAY_URL || "http://localhost:8080";

export const options = {
  scenarios: {
    ramp_up: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "2m",  target: 50  },
        { duration: "5m",  target: 50  },
        { duration: "1m",  target: 200 },
        { duration: "1m",  target: 0   },
      ],
    },
  },
  thresholds: {
    http_req_duration:              ["p(99)<500", "p(95)<200"],
    http_req_failed:                ["rate<0.01"],
    clearflow_payment_accept_rate:  ["rate>0.95"],
  },
};

// ── Test data ───────────────────────────────────────────────
const PARTIES = [
  { name: "Alpine Logistics GmbH",  iban: "DE89370400440532013000", bic: "DEUTDEDBXXX", country: "DE" },
  { name: "Euro Trade SARL",        iban: "FR7630006000011234567890189", bic: "BNPAFRPPXXX", country: "FR" },
  { name: "HSBC Holdings PLC",      iban: "GB29NWBK60161331926819", bic: "HBUKGB4BXXX", country: "GB" },
  { name: "UBS AG Zurich",          iban: "CH5604835012345678009",  bic: "UBSWCHZHXXX", country: "CH" },
  { name: "ING Bank NV",            iban: "NL91ABNA0417164300",     bic: "INGBNL2AXXX", country: "NL" },
  { name: "Banco Santander SA",     iban: "ES9121000418450200051332", bic: "BSCHESMM",  country: "ES" },
];

const CHANNELS  = ["SWIFT", "SEPA", "FEDWIRE", "FASTER_PAYMENTS", "INTERNAL"];
const CURRENCIES = ["USD", "EUR", "GBP", "CHF"];

function randomParty() {
  return PARTIES[Math.floor(Math.random() * PARTIES.length)];
}

function randomAmount() {
  return (Math.random() * 999_900 + 100).toFixed(2);
}

function buildPayload() {
  let debtor   = randomParty();
  let creditor = randomParty();
  while (creditor.iban === debtor.iban) {
    creditor = randomParty();
  }

  const today = new Date().toISOString().split("T")[0];
  const tomorrow = new Date(Date.now() + 86400000).toISOString().split("T")[0];

  return JSON.stringify({
    instructionId:  uuidv4(),
    endToEndId:     `E2E-${today.replace(/-/g, "")}-${Math.floor(Math.random() * 99999).toString().padStart(5, "0")}`,
    uetr:           uuidv4(),
    debtor: {
      name:    debtor.name,
      iban:    debtor.iban,
      bic:     debtor.bic,
      address: `${debtor.country} HQ`,
      country: debtor.country,
    },
    creditor: {
      name:    creditor.name,
      iban:    creditor.iban,
      bic:     creditor.bic,
      address: `${creditor.country} Branch`,
      country: creditor.country,
    },
    amount:        parseFloat(randomAmount()),
    currency:      CURRENCIES[Math.floor(Math.random() * CURRENCIES.length)],
    valueDate:     tomorrow,
    purpose:       "SUPP",
    remittanceInfo: `INV-${Math.floor(Math.random() * 99999)}`,
    channel:       CHANNELS[Math.floor(Math.random() * CHANNELS.length)],
  });
}

// ── Main VU function ────────────────────────────────────────
export default function () {
  const correlationId = `LT-${uuidv4().substring(0, 8).toUpperCase()}`;
  const payload = buildPayload();

  const res = http.post(
    `${GATEWAY_URL}/api/v1/payments`,
    payload,
    {
      headers: {
        "Content-Type": "application/json",
        "X-Correlation-Id": correlationId,
      },
      timeout: "10s",
    }
  );

  paymentDuration.add(res.timings.duration);

  const ok = check(res, {
    "status is 202 Accepted": (r) => r.status === 202,
    "response has paymentId": (r) => {
      try { return JSON.parse(r.body).paymentId !== undefined; }
      catch { return false; }
    },
    "no server error": (r) => r.status < 500,
  });

  if (res.status === 202) {
    paymentAccepted.add(1);
    acceptRate.add(1);
  } else if (res.status === 409) {
    duplicateHit.add(1);
    acceptRate.add(0);
  } else if (res.status === 429) {
    rateLimitHit.add(1);
    acceptRate.add(0);
  } else {
    paymentRejected.add(1);
    acceptRate.add(0);
  }

  // ~10 requests/sec per VU at steady state
  sleep(0.1);
}

// ── Setup: verify gateway is up ─────────────────────────────
export function setup() {
  const res = http.get(`${GATEWAY_URL}/actuator/health`, { timeout: "5s" });
  if (res.status !== 200) {
    throw new Error(`Gateway health check failed: HTTP ${res.status}. Start services first.`);
  }
  console.log(`Gateway is UP — starting load test against ${GATEWAY_URL}`);
  return { startTime: new Date().toISOString() };
}

// ── Teardown: print summary ──────────────────────────────────
export function teardown(data) {
  console.log(`Load test started: ${data.startTime}`);
  console.log(`Load test ended:   ${new Date().toISOString()}`);
}
