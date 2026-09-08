#!/bin/bash
# Robust watchdog for Dukascopy downloads
# Auto-restarts on failure, logs progress, handles rate limiting

cd /c/Users/Legacy/Documents/SCRATCH

SYMBOL="${1:-GBPUSD}"
START="${2:-2021-01-01}"
END="${3:-2025-05-31}"
DELAY="${4:-12}"
MAX_RESTARTS=200
RESTART_COUNT=0
LOG="research/data/watchdog_${SYMBOL}.log"

echo "[$(date)] Watchdog started: $SYMBOL $START..$END delay=${DELAY}s" | tee -a $LOG

while [ $RESTART_COUNT -lt $MAX_RESTARTS ]; do
    echo "[$(date)] Attempt $((RESTART_COUNT+1)): starting download..." | tee -a $LOG
    
    venv/Scripts/python research/data/download_dukascopy.py \
        --symbol $SYMBOL --start $START --end $END --delay $DELAY \
        >> research/data/download_progress.log 2>&1
    
    EXIT_CODE=$?
    
    if [ $EXIT_CODE -eq 0 ]; then
        FILES=$(ls research/data/raw/${SYMBOL}_H1/ 2>/dev/null | wc -l)
        echo "[$(date)] COMPLETE! $FILES files downloaded." | tee -a $LOG
        break
    fi
    
    RESTART_COUNT=$((RESTART_COUNT+1))
    FILES=$(ls research/data/raw/${SYMBOL}_H1/ 2>/dev/null | wc -l)
    echo "[$(date)] Died (exit $EXIT_CODE) after $FILES files. Restart $RESTART_COUNT/$MAX_RESTARTS in 120s..." | tee -a $LOG
    sleep 120
done

if [ $RESTART_COUNT -ge $MAX_RESTARTS ]; then
    echo "[$(date)] FAILED: max restarts reached. Manual intervention needed." | tee -a $LOG
fi
