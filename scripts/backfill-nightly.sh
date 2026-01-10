#!/usr/bin/env zsh

cd /Volumes/1TB/dev/quant-vibe
source venv/bin/activate
python ./scripts/backfill/backfill_stream_greeks.py --mark-expired && \
python ./scripts/backfill/backfill_stream_greeks.py --active-only --batch-size 500
