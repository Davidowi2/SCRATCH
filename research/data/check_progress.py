"""
Periodic download progress check.
Run this every 30 minutes via Windows Task Scheduler.
"""
import os
import time
from datetime import datetime

os.chdir(r"C:\Users\Legacy\Documents\SCRATCH")

# Check files
d = "research/data/raw/EURUSD_H1"
files = [f for f in os.listdir(d) if f.endswith(".csv")] if os.path.isdir(d) else []
years = {}
for f in files:
    y = f[:4]
    years[y] = years.get(y, 0) + 1

# Check status file
status = "unknown"
if os.path.exists("research/data/download_status.txt"):
    with open("research/data/download_status.txt") as f:
        status = f.read().strip()

# Check if process is running
import subprocess
try:
    result = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq pythonw.exe", "/FO", "CSV"],
        capture_output=True, text=True
    )
    running = "pythonw.exe" in result.stdout
except:
    running = False

print(f"Time: {datetime.now().isoformat()}")
print(f"Files: {len(files)}")
print(f"Years: {years}")
print(f"Status: {status}")
print(f"Process running: {running}")
