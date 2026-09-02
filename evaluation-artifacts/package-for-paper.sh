#!/bin/bash
# Package all evaluation artifacts for paper submission

set -e

OUTPUT_ZIP="clearflow-evaluation-artifacts-$(date +%Y%m%d_%H%M%S).zip"

echo "Packaging ClearFlow evaluation artifacts..."
echo "Target: $OUTPUT_ZIP"

# Collect from parent directory
cd ..

# Include these directories and files
FILES_TO_INCLUDE=(
  "evaluation-artifacts/COLLECTION_MANIFEST.md"
  "evaluation-artifacts/batch_100k_eval_run.log"
  "evaluation-artifacts/smoke_test_output.txt"
  "evaluation-artifacts/graphify-out/"
  "evaluation-artifacts/grafana/"
  "evaluation-artifacts/mcp-outputs/"
  "dev-logs/"
  "generate_summary_*.csv"
  "TEST_RESULTS_100K_FAILURE.md"
  "CLEARFLOW_TECHNICAL_GUIDE.md"
)

# Create temp directory for packaging
TEMP_DIR=$(mktemp -d)
trap "rm -rf $TEMP_DIR" EXIT

# Copy files
for item in "${FILES_TO_INCLUDE[@]}"; do
  if [ -e "$item" ]; then
    mkdir -p "$TEMP_DIR/clearflow-artifacts/$(dirname $item)"
    cp -r "$item" "$TEMP_DIR/clearflow-artifacts/$item"
  fi
done

# Create zip
cd "$TEMP_DIR"
zip -r "$OUTPUT_ZIP" clearflow-artifacts/

# Move to evaluation-artifacts/
mv "$OUTPUT_ZIP" ../evaluation-artifacts/

echo "✓ Packaged: evaluation-artifacts/$OUTPUT_ZIP"
echo "Size: $(du -h ../evaluation-artifacts/$OUTPUT_ZIP | cut -f1)"
echo ""
echo "Ready for paper submission or upload to repository."
