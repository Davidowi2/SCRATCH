#!/usr/bin/env python3
"""Ad-hoc cointegration check for BTC-ETH. Not part of factory permanently."""
import csv, sys, os, statistics
from datetime import datetime, timezone
from statsmodels.tsa.stattools import adfuller

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

def load_daily(path):
    rows = []
    with open(path, newline='', encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ts = datetime.strptime(row["timestamp_utc"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            rows.append({"time": ts, "close": float(row["close"])})
    return sorted(rows, key=lambda r: r["time"])

btc = load_daily("research/data/crypto/btcusdt_daily_2019_2025.csv")
eth = load_daily("research/data/crypto/ethusdt_daily_2020_2025.csv")

btc_d = {b["time"].date(): b["close"] for b in btc if datetime(2021,1,1,tzinfo=timezone.utc) <= b["time"] <= datetime(2023,12,31,23,59,59,tzinfo=timezone.utc)}
eth_d = {e["time"].date(): e["close"] for e in eth if datetime(2021,1,1,tzinfo=timezone.utc) <= e["time"] <= datetime(2023,12,31,23,59,59,tzinfo=timezone.utc)}
common = sorted(set(btc_d.keys()) & set(eth_d.keys()))
btc_x = [btc_d[d] for d in common]
eth_y = [eth_d[d] for d in common]

n = len(btc_x)
mean_btc = sum(btc_x)/n
mean_eth = sum(eth_y)/n
beta = sum((btc_x[i]-mean_btc)*(eth_y[i]-mean_eth) for i in range(n)) / sum((btc_x[i]-mean_btc)**2 for i in range(n))
alpha = mean_eth - beta * mean_btc
residuals = [eth_y[i] - (alpha + beta*btc_x[i]) for i in range(n)]

adf_res = adfuller(residuals, autolag="AIC")
crit = adf_res[4]
print("OLS: alpha=%.4f, beta=%.6f" % (alpha, beta))
print("Residual std=%.4f" % statistics.stdev(residuals))
print("ADF stat=%.4f, p-value=%.6f" % (adf_res[0], adf_res[1]))
for k in sorted(crit.keys()):
    print("  crit %s%%: %.3f" % (k, crit[k]))

if adf_res[1] < 0.05:
    print("VERDICT: COINTEGRATED (p<0.05) — proceed to S-020")
else:
    print("VERDICT: NOT COINTEGRATED (p>=0.05) — STOP Track B")

adf_btc = adfuller(btc_x, autolag="AIC")
adf_eth = adfuller(eth_y, autolag="AIC")
print("ADF BTC: stat=%.4f, p=%.6f" % (adf_btc[0], adf_btc[1]))
print("ADF ETH: stat=%.4f, p=%.6f" % (adf_eth[0], adf_eth[1]))
