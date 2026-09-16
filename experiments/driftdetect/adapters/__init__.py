"""Adapters: external trace formats -> boundary call record ledgers.

Each adapter converts one public data source into the CallRecord JSONL that
every detector consumes, plus a labels sidecar holding the source's ground
truth (which must never enter the ledger itself — detectors are only allowed
to see what crosses the system boundary).

Convention per adapter module:
- ``convert_run(...)``: one source run -> (records, label dict)
- a CLI (``python3 -m driftdetect.adapters.<source> <src> -o <outdir>``)
  writing per-agent ledgers, labels, and a manifest with sha256 fingerprints
  so a verdict can name the exact input it was computed from.
"""
