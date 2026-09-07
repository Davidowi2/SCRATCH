"""
Robust download wrapper with auto-restart.
Survives network errors and runs detached from terminal.
"""
import subprocess
import sys
import time
import os
from datetime import datetime

os.chdir(r"C:\Users\Legacy\Documents\SCRATCH")
SCRIPT = "research/data/download_dukascopy.py"
MAX_RESTARTS = 200
RESTART_DELAY = 30  # seconds between restarts
STATUS_FILE = "research/data/download_status.txt"

def count_files():
    d = "research/data/raw/EURUSD_H1"
    return len([f for f in os.listdir(d) if f.endswith(".csv")]) if os.path.isdir(d) else 0

def update_status(msg):
    with open(STATUS_FILE, "w") as f:
        f.write(f"{datetime.now().isoformat()} | files={count_files()} | {msg}\n")

restart = 0
while restart < MAX_RESTARTS:
    restart += 1
    update_status(f"Starting attempt {restart}/{MAX_RESTARTS}")
    print(f"[{datetime.now():%H:%M:%S}] Attempt {restart}: downloading...", flush=True)
    
    try:
        result = subprocess.run(
            [sys.executable, SCRIPT, "--start", "2021-01-01", "--end", "2025-12-31"],
            timeout=7200,  # 2 hour max per attempt
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            update_status("COMPLETED SUCCESSFULLY")
            print("DONE!", flush=True)
            sys.exit(0)
        else:
            update_status(f"Died (exit {result.returncode}), restarting in {RESTART_DELAY}s")
    except subprocess.TimeoutExpired:
        update_status("Timed out after 2h, restarting")
    except Exception as e:
        update_status(f"Exception: {e}, restarting")
    
    time.sleep(RESTART_DELAY)

update_status("MAX RESTARTS REACHED")
print("FAILED: max restarts reached", file=sys.stderr)
