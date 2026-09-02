#!/usr/bin/env bash
# ============================================================
# ClearFlow — Elasticsearch Pre-seed Script
# Generates ~500k structured log events and bulk-indexes them
# into per-service daily indices for Kibana/Grafana demos.
#
# Usage:
#   ./seed-elasticsearch.sh [ES_HOST] [DAYS_BACK] [TX_PER_DAY]
#   ./seed-elasticsearch.sh localhost:9200 30 1000
#
# Requires: bash 4+, curl, jq, awk, date (GNU coreutils)
# ============================================================
set -euo pipefail

ES_HOST="${1:-localhost:9200}"
DAYS_BACK="${2:-30}"
TX_PER_DAY="${3:-1000}"
BULK_SIZE=500
ES_URL="http://${ES_HOST}"

# Colour output
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# ── Prerequisites ───────────────────────────────────────────
command -v curl >/dev/null || error "curl not found"
command -v jq   >/dev/null || error "jq not found"

info "Target: ${ES_URL}  days=${DAYS_BACK}  tx/day=${TX_PER_DAY}"
info "Total events ≈ $((DAYS_BACK * TX_PER_DAY * 5)) (5 event types per payment)"

# ── Wait for Elasticsearch ──────────────────────────────────
info "Waiting for Elasticsearch..."
for i in $(seq 1 30); do
    if curl -sf "${ES_URL}/_cluster/health" >/dev/null 2>&1; then
        info "Elasticsearch is ready"; break
    fi
    [ "$i" -eq 30 ] && error "Elasticsearch not ready after 30s"
    sleep 1
done

# ── Apply index template ─────────────────────────────────────
TEMPLATE_FILE="$(dirname "$0")/../logstash/templates/clearflow-template.json"
if [ -f "$TEMPLATE_FILE" ]; then
    info "Applying index template..."
    curl -sf -X PUT "${ES_URL}/_index_template/clearflow" \
         -H 'Content-Type: application/json' \
         -d @"$TEMPLATE_FILE" >/dev/null
    info "Template applied"
else
    warn "Template file not found at ${TEMPLATE_FILE}, skipping"
fi

# ── Data generation helpers ─────────────────────────────────
SERVICES=("gateway" "fraud-scoring" "aml-compliance" "settlement" "audit")
CURRENCIES=("EUR" "GBP" "USD" "CHF" "JPY")
RISK_BANDS=("LOW" "LOW" "LOW" "MEDIUM" "MEDIUM" "HIGH" "CRITICAL")
RAILS=("SEPA_INSTANT" "SEPA_CREDIT_TRANSFER" "FASTER_PAYMENTS" "CHAPS" "SWIFT_GPI" "SWIFT_MT103" "FEDWIRE" "FEDACH")
COUNTRIES=("DE" "GB" "FR" "NL" "ES" "IT" "US" "AU" "JP" "SG" "ZA" "AE")

rand_element() { local arr=("$@"); echo "${arr[$((RANDOM % ${#arr[@]}))]}"; }
rand_int()     { echo $(( RANDOM % ($2 - $1 + 1) + $1 )); }
rand_score()   { awk "BEGIN { printf \"%.4f\", $RANDOM/32767 }"; }
rand_uuid()    { cat /proc/sys/kernel/random/uuid 2>/dev/null || python3 -c "import uuid; print(uuid.uuid4())"; }

iso_date() {
    # $1 = days_ago, $2 = seconds offset within day
    local days_ago="$1"
    local sec_offset="${2:-0}"
    date -u -d "${days_ago} days ago ${sec_offset} seconds" '+%Y-%m-%dT%H:%M:%S.000Z' 2>/dev/null \
      || date -u -v-"${days_ago}"d '+%Y-%m-%dT%H:%M:%S.000Z'  # macOS fallback
}

index_date() {
    date -u -d "${1} days ago" '+%Y.%m.%d' 2>/dev/null \
      || date -u -v-"${1}"d '+%Y.%m.%d'
}

# ── Build one payment lifecycle (5 events) ──────────────────
build_payment_events() {
    local day_ago="$1"
    local payment_id trace_id correlation_id
    payment_id="$(rand_uuid)"
    correlation_id="$(rand_uuid)"
    trace_id="00-$(tr -dc 'a-f0-9' </dev/urandom 2>/dev/null | head -c32 || echo "abcdef1234567890abcdef1234567890")-$(tr -dc 'a-f0-9' </dev/urandom 2>/dev/null | head -c16 || echo "abcdef12")-01"

    local currency debtor_country creditor_country rail risk_band fraud_score amount
    currency="$(rand_element "${CURRENCIES[@]}")"
    debtor_country="$(rand_element "${COUNTRIES[@]}")"
    creditor_country="$(rand_element "${COUNTRIES[@]}")"
    rail="$(rand_element "${RAILS[@]}")"
    risk_band="$(rand_element "${RISK_BANDS[@]}")"
    fraud_score="$(rand_score)"
    amount="$(rand_int 100 500000).$(rand_int 0 99)"

    local ts_submit ts_fraud ts_aml ts_settle ts_audit
    local base_sec
    base_sec=$(( (RANDOM % 14) * 3600 + RANDOM % 3600 )) # 00:00–14:00 + jitter
    ts_submit="$(iso_date "$day_ago" "$base_sec")"
    ts_fraud="$(iso_date "$day_ago" "$((base_sec + 200))")"
    ts_aml="$(iso_date "$day_ago" "$((base_sec + 600))")"
    ts_settle="$(iso_date "$day_ago" "$((base_sec + 1800))")"
    ts_audit="$(iso_date "$day_ago" "$((base_sec + 2000))")"

    local screening_result alert_level
    if [[ "$risk_band" == "CRITICAL" ]]; then
        screening_result="HIT"; alert_level="HIGH"
    elif [[ "$risk_band" == "HIGH" ]]; then
        screening_result="CLEAR"; alert_level="MEDIUM"
    else
        screening_result="CLEAR"; alert_level="LOW"
    fi

    local idx_date
    idx_date="$(index_date "$day_ago")"

    # Emit 5 newline-delimited JSON objects: action + source pairs for _bulk
    # 1. gateway — PAYMENT_SUBMITTED
    echo "{\"index\":{\"_index\":\"clearflow-gateway-${idx_date}\"}}"
    jq -cn --arg ts "$ts_submit" --arg pid "$payment_id" --arg cid "$correlation_id" \
       --arg tid "$trace_id" --arg cur "$currency" --arg dc "$debtor_country" \
       --arg cc "$creditor_country" --arg amt "$amount" --arg rail "$rail" \
       '{"@timestamp":$ts,"paymentId":$pid,"correlationId":$cid,"traceId":$tid,
         "service":"gateway","level":"INFO","eventType":"PAYMENT_SUBMITTED",
         "currency":$cur,"debtorCountry":$dc,"creditorCountry":$cc,
         "amount":($amt|tonumber),"rail":$rail,"alertLevel":"LOW",
         "message":("PAYMENT_SUBMITTED paymentId="+$pid+" debtorCountry="+$dc+" creditorCountry="+$cc)}'

    # 2. fraud-scoring — FRAUD_SCORE_COMPUTED
    echo "{\"index\":{\"_index\":\"clearflow-fraud-${idx_date}\"}}"
    jq -cn --arg ts "$ts_fraud" --arg pid "$payment_id" --arg cid "$correlation_id" \
       --arg tid "$trace_id" --arg rb "$risk_band" --arg fs "$fraud_score" \
       --arg al "$alert_level" \
       '{"@timestamp":$ts,"paymentId":$pid,"correlationId":$cid,"traceId":$tid,
         "service":"fraud-scoring","level":(if $rb=="CRITICAL" or $rb=="HIGH" then "WARN" else "INFO" end),
         "eventType":"FRAUD_SCORE_COMPUTED","riskBand":$rb,"fraudScore":($fs|tonumber),
         "alertLevel":$al,"durationMs":(150 + (200|floor)),
         "message":("FRAUD_SCORE_COMPUTED score="+$fs+" riskBand="+$rb)}'

    # 3. aml-compliance — AML_SCREENING_COMPLETE
    echo "{\"index\":{\"_index\":\"clearflow-aml-${idx_date}\"}}"
    jq -cn --arg ts "$ts_aml" --arg pid "$payment_id" --arg cid "$correlation_id" \
       --arg tid "$trace_id" --arg sr "$screening_result" --arg al "$alert_level" \
       '{"@timestamp":$ts,"paymentId":$pid,"correlationId":$cid,"traceId":$tid,
         "service":"aml-compliance",
         "level":(if $sr=="HIT" then "WARN" else "INFO" end),
         "eventType":(if $sr=="HIT" then "AML_SANCTIONS_HIT" else "AML_SCREENING_COMPLETE" end),
         "screeningResult":$sr,"matchScore":(if $sr=="HIT" then 0.91 else 0.0 end),
         "alertLevel":$al,"durationMs":320,
         "message":("AML_SCREENING_COMPLETE result="+$sr)}'

    # 4. settlement — SETTLEMENT_COMPLETE
    echo "{\"index\":{\"_index\":\"clearflow-settlement-${idx_date}\"}}"
    jq -cn --arg ts "$ts_settle" --arg pid "$payment_id" --arg cid "$correlation_id" \
       --arg tid "$trace_id" --arg rail "$rail" --arg cur "$currency" \
       --arg amt "$amount" \
       '{"@timestamp":$ts,"paymentId":$pid,"correlationId":$cid,"traceId":$tid,
         "service":"settlement","level":"INFO","eventType":"SETTLEMENT_COMPLETE",
         "rail":$rail,"currency":$cur,"amount":($amt|tonumber),"alertLevel":"LOW",
         "durationMs":95,
         "message":("SETTLEMENT_COMPLETE paymentId="+$pid+" rail="+$rail)}'

    # 5. audit — AUDIT_CHAIN_APPENDED
    echo "{\"index\":{\"_index\":\"clearflow-audit-${idx_date}\"}}"
    jq -cn --arg ts "$ts_audit" --arg pid "$payment_id" --arg cid "$correlation_id" \
       --arg tid "$trace_id" \
       '{"@timestamp":$ts,"paymentId":$pid,"correlationId":$cid,"traceId":$tid,
         "service":"audit","level":"INFO","eventType":"AUDIT_CHAIN_APPENDED",
         "alertLevel":"LOW","durationMs":15,
         "message":("AUDIT_CHAIN_APPENDED paymentId="+$pid)}'
}

# ── Main bulk-index loop ─────────────────────────────────────
TOTAL_INDEXED=0
TOTAL_ERRORS=0

for day in $(seq 0 "$((DAYS_BACK - 1))"); do
    batch_buf=""
    batch_count=0

    for _tx in $(seq 1 "$TX_PER_DAY"); do
        while IFS= read -r line; do
            batch_buf+="${line}"$'\n'
            (( batch_count++ ))

            if (( batch_count >= BULK_SIZE * 2 )); then  # *2 because action+source pairs
                response=$(echo "$batch_buf" | curl -sf -X POST "${ES_URL}/_bulk" \
                    -H 'Content-Type: application/x-ndjson' \
                    --data-binary @- 2>&1)
                if echo "$response" | jq -e '.errors == true' >/dev/null 2>&1; then
                    err_count=$(echo "$response" | jq '[.items[].index | select(.error)] | length' 2>/dev/null || echo "?")
                    warn "Bulk had ${err_count} errors on day ${day}"
                    (( TOTAL_ERRORS += 1 ))
                fi
                (( TOTAL_INDEXED += batch_count / 2 ))
                batch_buf=""
                batch_count=0
            fi
        done < <(build_payment_events "$day")
    done

    # Flush remainder
    if [ -n "$batch_buf" ]; then
        echo "$batch_buf" | curl -sf -X POST "${ES_URL}/_bulk" \
            -H 'Content-Type: application/x-ndjson' \
            --data-binary @- >/dev/null 2>&1 || (( TOTAL_ERRORS += 1 ))
        (( TOTAL_INDEXED += batch_count / 2 ))
    fi

    info "Day ${day}/${DAYS_BACK}: indexed ~$((TX_PER_DAY)) payments (total so far: ${TOTAL_INDEXED})"
done

# ── Alerts index (HIGH events) ───────────────────────────────
info "Seeding alerts index with sampled HIGH events..."
ALERT_DATE="$(index_date 0)"
alert_buf=""
for _ in $(seq 1 50); do
    ts="$(iso_date 0 $((RANDOM % 86400)))"
    payment_id="$(rand_uuid)"
    alert_buf+="{\"index\":{\"_index\":\"clearflow-alerts-${ALERT_DATE}\"}}"$'\n'
    alert_buf+="$(jq -cn --arg ts "$ts" --arg pid "$payment_id" \
        '{"@timestamp":$ts,"paymentId":$pid,"service":"fraud-scoring","level":"WARN",
          "eventType":"FRAUD_SCORE_COMPUTED","riskBand":"CRITICAL","fraudScore":0.92,
          "alertLevel":"HIGH","message":"High-risk payment detected"}')"$'\n'
done
echo "$alert_buf" | curl -sf -X POST "${ES_URL}/_bulk" \
    -H 'Content-Type: application/x-ndjson' \
    --data-binary @- >/dev/null

# ── Refresh indices ──────────────────────────────────────────
info "Refreshing all clearflow-* indices..."
curl -sf -X POST "${ES_URL}/clearflow-*/_refresh" >/dev/null

# ── Summary ──────────────────────────────────────────────────
DOC_COUNT=$(curl -sf "${ES_URL}/clearflow-*/_count" | jq '.count // 0' 2>/dev/null || echo "unknown")
info "============================================"
info " Seed complete!"
info " Payments processed : ${TOTAL_INDEXED}"
info " Bulk error batches : ${TOTAL_ERRORS}"
info " Total ES docs      : ${DOC_COUNT}"
info "============================================"
info "Open Kibana at http://localhost:5601 and create index pattern: clearflow-*"
