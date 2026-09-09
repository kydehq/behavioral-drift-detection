#!/usr/bin/env bash
# Build the paper PDF from the markdown source.
#
# Pipeline: pandoc -> standalone HTML with print.css -> headless Chrome print.
# Chosen over pdflatex because the paper contains Unicode (Žliobaitė, Çağatan,
# ≈) that pdflatex rejects without extra packages.
#
# Requirements: pandoc, google-chrome (or chromium — adjust CHROME below).
set -euo pipefail

cd "$(dirname "$0")"

SRC=behavioral-drift-detection-survey.md
OUT=behavioral-drift-detection-survey.pdf
CHROME="${CHROME:-google-chrome}"
TMP_HTML="$(mktemp --suffix=.html)"
trap 'rm -f "$TMP_HTML"' EXIT

pandoc "$SRC" \
  --standalone \
  --embed-resources \
  --css=print.css \
  --metadata pagetitle="Behavioral Drift in Autonomous LLM-driven Systems" \
  -o "$TMP_HTML"

"$CHROME" \
  --headless=new \
  --disable-gpu \
  --no-sandbox \
  --no-pdf-header-footer \
  --print-to-pdf="$OUT" \
  "file://$TMP_HTML"

echo "Wrote $OUT"
