#!/usr/bin/env bash
# Build a paper PDF from its markdown source.
#
# Usage: ./build-pdf.sh [path/to/paper.md]
#   no argument: behavioral-drift-detection-survey.md (the survey)
#   follow-up:   ./build-pdf.sh ../paper-followup/observability-ladder.md
#
# Pipeline: pandoc -> standalone HTML with print.css -> headless Chrome print.
# Chosen over pdflatex because the papers contain Unicode (Žliobaitė, Çağatan,
# ≈) that pdflatex rejects without extra packages. print.css is shared; the
# PDF lands next to the source, figures resolve relative to it.
#
# Requirements: pandoc, google-chrome (or chromium — set CHROME).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC="$(realpath "${1:-$SCRIPT_DIR/behavioral-drift-detection-survey.md}")"
OUT="${SRC%.md}.pdf"
TITLE="$(sed -n 's/^# //p' "$SRC" | head -1)"
CHROME="${CHROME:-google-chrome}"
TMP_HTML="$(mktemp --suffix=.html)"
trap 'rm -f "$TMP_HTML"' EXIT

cd "$(dirname "$SRC")"

pandoc "$SRC" \
  --standalone \
  --embed-resources \
  --css="$SCRIPT_DIR/print.css" \
  --metadata pagetitle="$TITLE" \
  -o "$TMP_HTML"

"$CHROME" \
  --headless=new \
  --disable-gpu \
  --no-sandbox \
  --no-pdf-header-footer \
  --print-to-pdf="$OUT" \
  "file://$TMP_HTML"

echo "Wrote $OUT"
