#!/bin/bash
# Generates self-signed CA + per-service keystores/truststores for dev mTLS
# Run once: bash generate-mtls-certs.sh
# Outputs to: certs/ directory

set -e

BASE="$(cd "$(dirname "$0")" && pwd)"
CERTS="$BASE/certs"
PASS="clearflow"

echo "======================================================"
echo "  ClearFlow mTLS Certificate Generator"
echo "======================================================"
echo ""

mkdir -p "$CERTS"

# ── Step 1: Generate self-signed CA ────────────────────────
echo "[1/3] Generating ClearFlow self-signed CA..."
if [ -f "$CERTS/clearflow-ca.p12" ]; then
  echo "      CA keystore already exists — skipping CA generation."
else
  keytool -genkeypair \
    -alias clearflow-ca \
    -keyalg RSA -keysize 2048 -validity 3650 \
    -keystore "$CERTS/clearflow-ca.p12" \
    -storepass "$PASS" \
    -storetype PKCS12 \
    -dname "CN=ClearFlow-CA,O=ClearFlow,C=US" \
    -ext bc:ca=true
  echo "      CA keypair generated."
fi

echo "      Exporting CA certificate..."
keytool -export \
  -alias clearflow-ca \
  -keystore "$CERTS/clearflow-ca.p12" \
  -storepass "$PASS" \
  -file "$CERTS/clearflow-ca.crt" \
  -rfc
echo "      CA certificate exported: certs/clearflow-ca.crt"

# ── Step 2: Generate per-service keystores ─────────────────
SERVICES=(
  "gateway"
  "fraud-scoring"
  "validation-enrichment"
  "aml-compliance"
  "routing-execution"
  "settlement"
  "audit"
  "mcp-readonly-gateway"
)

echo ""
echo "[2/3] Generating per-service keypairs, CSRs, and signed certificates..."
for SERVICE in "${SERVICES[@]}"; do
  echo ""
  echo "  --- $SERVICE ---"

  # (a) Generate service keypair
  echo "      Generating keypair..."
  keytool -genkeypair \
    -alias "$SERVICE" \
    -keyalg RSA -keysize 2048 -validity 365 \
    -keystore "$CERTS/$SERVICE.p12" \
    -storepass "$PASS" \
    -storetype PKCS12 \
    -dname "CN=$SERVICE,O=ClearFlow,C=US"

  # (b) Generate CSR
  echo "      Generating CSR..."
  keytool -certreq \
    -alias "$SERVICE" \
    -keystore "$CERTS/$SERVICE.p12" \
    -storepass "$PASS" \
    -file "$CERTS/$SERVICE.csr"

  # (c) Sign CSR with CA
  echo "      Signing certificate with CA..."
  keytool -gencert \
    -alias clearflow-ca \
    -keystore "$CERTS/clearflow-ca.p12" \
    -storepass "$PASS" \
    -infile "$CERTS/$SERVICE.csr" \
    -outfile "$CERTS/$SERVICE.crt" \
    -validity 365 \
    -rfc

  # (d) Import CA cert into service keystore (establish chain of trust)
  echo "      Importing CA cert into service keystore..."
  keytool -import \
    -alias clearflow-ca \
    -keystore "$CERTS/$SERVICE.p12" \
    -storepass "$PASS" \
    -file "$CERTS/clearflow-ca.crt" \
    -noprompt

  # (e) Import signed service certificate into service keystore
  echo "      Importing signed service certificate..."
  keytool -import \
    -alias "$SERVICE" \
    -keystore "$CERTS/$SERVICE.p12" \
    -storepass "$PASS" \
    -file "$CERTS/$SERVICE.crt" \
    -noprompt

  echo "      $SERVICE keystore ready: certs/$SERVICE.p12"
done

# ── Step 3: Build shared truststore ────────────────────────
echo ""
echo "[3/3] Building shared truststore (certs/clearflow-truststore.p12)..."

# Import CA cert once into the shared truststore
keytool -import \
  -alias clearflow-ca \
  -keystore "$CERTS/clearflow-truststore.p12" \
  -storepass "$PASS" \
  -storetype PKCS12 \
  -file "$CERTS/clearflow-ca.crt" \
  -noprompt

echo "      Truststore ready: certs/clearflow-truststore.p12"

# ── Summary ────────────────────────────────────────────────
echo ""
echo "======================================================"
echo "  Certificate Generation Complete"
echo "======================================================"
echo ""
echo "  Generated files in: $CERTS/"
echo ""
echo "  CA:"
echo "    clearflow-ca.p12        — CA keystore"
echo "    clearflow-ca.crt        — CA certificate (PEM)"
echo ""
echo "  Per-service keystores (PKCS12, password: clearflow):"
for SERVICE in "${SERVICES[@]}"; do
  echo "    $SERVICE.p12"
done
echo ""
echo "  Shared truststore:"
echo "    clearflow-truststore.p12 — contains the CA cert; trusted by all services"
echo ""
echo "  To start ClearFlow with mTLS:"
echo "    bash start_live_traffic_tls.sh"
echo ""
echo "  To activate TLS on a single service manually:"
echo "    SPRING_PROFILES_ACTIVE=dev,ssl java -jar <service>.jar"
echo ""
echo "  Note: Set CLEARFLOW_CERTS_DIR to override the default certs/ path."
echo "        Default path resolved from each service's working directory."
