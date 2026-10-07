#!/bin/bash
# Monitors phase1_generate for completion. Exits when the PID is gone.

PID="$1"
LOG="$2"
OUTDIR="$3"
POLL=300  # 5 min

if [ -z "$PID" ]; then echo "Usage: $0 <pid> <logfile> <outdir>"; exit 1; fi

while kill -0 "$PID" 2>/dev/null; do
    sleep "$POLL"
    COUNT=$(ls "$OUTDIR" 2>/dev/null | wc -l)
    echo "[$(date '+%H:%M')] generate: $COUNT done, pid $PID alive"
done

echo "[$(date '+%H:%M')] GENERATE FINISHED. Checking results..."
tail -5 "$LOG"
ls "$OUTDIR" 2>/dev/null | wc -l