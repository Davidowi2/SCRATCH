#!/bin/bash
# Watchdog: auto-restart the download if it dies
cd /c/Users/Legacy/Documents/SCRATCH

MAX_RESTARTS=100
RESTART_COUNT=0

while [ $RESTART_COUNT -lt $MAX_RESTARTS ]; do
    echo "[$(date)] Starting download attempt $((RESTART_COUNT+1))..."
    python research/data/download_dukascopy.py --start 2021-01-01 --end 2025-12-31
    EXIT_CODE=$?
    
    if [ $EXIT_CODE -eq 0 ]; then
        echo "[$(date)] Download completed successfully!"
        break
    fi
    
    RESTART_COUNT=$((RESTART_COUNT+1))
    echo "[$(date)] Download died (exit $EXIT_CODE). Restart $RESTART_COUNT/$MAX_RESTARTS in 60s..."
    sleep 60
done

echo "[$(date)] Watchdog finished. Total files:"
ls research/data/raw/EURUSD_H1/ | wc -l
