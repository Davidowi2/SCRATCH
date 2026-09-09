"""
fingerprint_v2.py — Fingerprint collision rule for the Popcorn Machine.

Amendment: When a kernel's mechanism_hash matches BOTH a LIVE and a DEAD row,
flag both, require declared parent_id, and apply the death scope.
This prevents H-004/H-005 (EURUSD stop-dial) from being blocked by H-003's ghost.

Unit tests:
  T1: H-003 computes mechanism_hash == H-001's stored hash
  T2: H-003 parameter_hash != H-001's
  T3: synthetic probe vs H-002 (MECHANISM-DEAD, no parent_id) -> BLOCKED
  T4: H-003 (parent_id=H-001, pre-declared replication) -> FLAGGED, ALLOWED
  T5: H-004 probe (parent_id=H-001) -> ROUTES to H-001 (LIVE), NOT blocked by H-003 (DEAD, different instrument)
  T6: H-004 probe WITHOUT parent_id -> BLOCKED (matches both LIVE H-001 and DEAD H-003)
"""

import hashlib
import json
from typing import Any


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def mechanism_hash(params: dict) -> str:
    vector = {
        "signal_family": params.get("signal_family", ""),
        "entry_trigger_class": params.get("entry_trigger_class", ""),
        "exit_logic_class": params.get("exit_logic_class", ""),
        "session_window": sorted(params.get("session_hours", [])),
        "timeframe_class": params.get("timeframe", ""),
        "instrument_class": params.get("instrument_class", ""),
    }
    return hashlib.sha256(_canonical(vector).encode()).hexdigest()


def parameter_hash(params: dict) -> str:
    mh = mechanism_hash(params)
    exact = {
        "pair": params.get("pair", ""),
        "thresholds": params.get("thresholds", {}),
        "bands": params.get("bands", {}),
        "stop_mult": params.get("stop_mult", 0),
        "max_hold": params.get("max_hold", 0),
        "friction_pips": params.get("friction_pips", 0),
    }
    return hashlib.sha256((mh + _canonical(exact)).encode()).hexdigest()


def full_fingerprint(params: dict) -> tuple[str, str]:
    return mechanism_hash(params), parameter_hash(params)


def check_graveyard_collision(params: dict, graveyard: list[dict]) -> dict:
    """
    Check if a kernel collides with graveyard entries.

    Returns:
        {
            "status": "OK" | "BLOCKED" | "FLAGGED",
            "message": str,
            "matches": list of matching rows
        }
    """
    mh = mechanism_hash(params)
    ph = parameter_hash(params)

    matching_rows = [row for row in graveyard if row.get("mechanism_hash") == mh]

    if not matching_rows:
        return {"status": "OK", "message": "No mechanism collision", "matches": []}

    # Check for dead matches
    dead_matches = [row for row in matching_rows if "DEAD" in row.get("status", "")]
    live_matches = [row for row in matching_rows if "LIVE" in row.get("status", "")]

    if dead_matches and not live_matches:
        return {
            "status": "BLOCKED",
            "message": f"Matches dead mechanism(s): {[r['kernel_id'] for r in dead_matches]}",
            "matches": dead_matches,
        }

    if live_matches and dead_matches:
        # Collision: both live and dead matches
        # Require parent_id to route to the live parent
        declared_parent = params.get("parent_id")
        if not declared_parent:
            return {
                "status": "BLOCKED",
                "message": f"Hash matches both LIVE ({[r['kernel_id'] for r in live_matches]}) and DEAD ({[r['kernel_id'] for r in dead_matches]}). parent_id required to route to live parent.",
                "matches": matching_rows,
            }
        # Check if declared parent matches a live entry
        parent_match = [r for r in live_matches if r["kernel_id"] == declared_parent]
        if not parent_match:
            return {
                "status": "BLOCKED",
                "message": f"parent_id={declared_parent} does not match any live mechanism.",
                "matches": matching_rows,
            }
        return {
            "status": "FLAGGED",
            "message": f"Matches LIVE {parent_match[0]['kernel_id']} (parent_id verified). Death scoped to {[r['kernel_id'] for r in dead_matches]}.",
            "matches": matching_rows,
        }

    if live_matches and not dead_matches:
        return {
            "status": "FLAGGED",
            "message": f"Matches LIVE mechanism(s): {[r['kernel_id'] for r in live_matches]}",
            "matches": live_matches,
        }

    return {"status": "OK", "message": "No collision", "matches": []}


# ---------------------------------------------------------------------------
# Unit tests T1-T6
# ---------------------------------------------------------------------------

def run_tests():
    passed = 0
    failed = 0

    # Reference params
    h001_params = {
        "signal_family": "mean_reversion",
        "entry_trigger_class": "z_score_threshold",
        "exit_logic_class": "revert_to_band",
        "session_hours": [22, 23, 0, 1, 2, 3, 4, 5, 6],
        "timeframe": "H1",
        "instrument_class": "FX_major",
        "pair": "EURUSD",
        "thresholds": {"z_entry": 2.0, "z_exit": 1.0},
        "bands": {"ma_period": 20, "sd_mult": 1.0},
        "stop_mult": 1.5,
        "max_hold": 8,
        "friction_pips": 0.5,
    }

    h003_params = dict(h001_params, pair="GBPUSD")

    h002_params = {
        "signal_family": "continuation",
        "entry_trigger_class": "z_score_threshold",
        "exit_logic_class": "revert_to_band",
        "session_hours": [22, 23, 0, 1, 2, 3, 4, 5, 6],
        "timeframe": "H1",
        "instrument_class": "FX_major",
        "pair": "EURUSD",
        "thresholds": {"z_entry": 2.5, "z_exit": 1.0},
        "bands": {"ma_period": 20, "sd_mult": 1.0},
        "stop_mult": 2.0,
        "max_hold": 24,
        "friction_pips": 0.5,
    }

    h004_params = dict(h001_params, stop_mult=0.75, parent_id="H-001")

    # Simulated graveyard
    graveyard = [
        {"kernel_id": "H-001", "status": "LIVE", "mechanism_hash": mechanism_hash(h001_params)},
        {"kernel_id": "H-003", "status": "MECHANISM-DEAD (scoped to GBPUSD)", "mechanism_hash": mechanism_hash(h003_params)},
        {"kernel_id": "H-002", "status": "MECHANISM-DEAD", "mechanism_hash": mechanism_hash(h002_params)},
    ]

    # T1: H-003 mechanism_hash == H-001
    if mechanism_hash(h003_params) == mechanism_hash(h001_params):
        print(f"T1 PASS: H-003 mechanism_hash == H-001")
        passed += 1
    else:
        print(f"T1 FAIL")
        failed += 1

    # T2: H-003 parameter_hash != H-001
    if parameter_hash(h003_params) != parameter_hash(h001_params):
        print(f"T2 PASS: H-003 parameter_hash != H-001")
        passed += 1
    else:
        print(f"T2 FAIL")
        failed += 1

    # T3: Synthetic probe vs H-002 (no parent_id) -> BLOCKED
    h002_probe = dict(h002_params)
    h002_probe.pop("parent_id", None)
    result = check_graveyard_collision(h002_probe, graveyard)
    if result["status"] == "BLOCKED":
        print(f"T3 PASS: H-002 probe BLOCKED")
        passed += 1
    else:
        print(f"T3 FAIL: {result}")
        failed += 1

    # T4: H-003 (parent_id=H-001, pre-declared) -> FLAGGED
    h003_probe = dict(h003_params, parent_id="H-001")
    result = check_graveyard_collision(h003_probe, graveyard)
    if result["status"] == "FLAGGED":
        print(f"T4 PASS: H-003 FLAGGED as sibling")
        passed += 1
    else:
        print(f"T4 FAIL: {result}")
        failed += 1

    # T5: H-004 probe (parent_id=H-001) -> ROUTES to H-001, NOT blocked by H-003
    result = check_graveyard_collision(h004_params, graveyard)
    if result["status"] == "FLAGGED":
        print(f"T5 PASS: H-004 routes to H-001 (LIVE parent), not blocked by H-003")
        passed += 1
    else:
        print(f"T5 FAIL: {result}")
        failed += 1

    # T6: H-004 probe WITHOUT parent_id -> BLOCKED (matches both LIVE H-001 and DEAD H-003)
    h004_no_parent = dict(h004_params)
    h004_no_parent.pop("parent_id", None)
    result = check_graveyard_collision(h004_no_parent, graveyard)
    if result["status"] == "BLOCKED":
        print(f"T6 PASS: H-004 without parent_id BLOCKED (collision)")
        passed += 1
    else:
        print(f"T6 FAIL: {result}")
        failed += 1

    total = passed + failed
    print(f"\nResults: {passed}/{total} passed, {failed} failed")
    return passed, failed, total


if __name__ == "__main__":
    run_tests()
