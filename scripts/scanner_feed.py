#!/usr/bin/env python3
"""Reference downloader for the domestic Telegram report; local scanner integration required."""
import argparse
import json
import os
import tempfile
import time
from datetime import datetime, time as clock_time, timezone, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

try:
    from .validate_report import validate_report
except ImportError:
    from validate_report import validate_report

KST = timezone(timedelta(hours=9))
BASE_URL = "https://raw.githubusercontent.com/33hankei-afk/radar-telegram-reports/main/latest.json"


def fetch_report(timeout=15):
    """Fetch validated report. Raises if remote missing/invalid; never invent missing data."""
    url = BASE_URL + "?nocache=" + str(time.time_ns())
    req = Request(url, headers={"User-Agent": "radar-telegram-scanner/1.0", "Cache-Control": "no-cache"})
    with urlopen(req, timeout=timeout) as response:
        data = json.load(response)
    errors = validate_report(data)
    if errors:
        raise ValueError("remote report invalid: " + "; ".join(errors))
    return data


def refresh_cache(target, require_today_after_21=True, now=None):
    """Return (state, data). Write atomically only if a valid/new report is present.

    States: updated, unchanged, not_yet_published. Call at startup, then periodically
    after 21:00 KST while app is open, and from manual refresh button.
    """
    target = Path(target)
    now = now or datetime.now(KST)
    if now.utcoffset() != timedelta(hours=9):
        raise ValueError("now must be an aware KST datetime")
    data = fetch_report()
    if require_today_after_21 and now.time() >= clock_time(21, 0) and data["date_kst"] != now.date().isoformat():
        return "not_yet_published", data
    serialized = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    old = target.read_text(encoding="utf-8") if target.exists() else None
    if serialized == old:
        return "unchanged", data
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".radar-", suffix=".json", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(serialized)
        os.replace(temp_name, target)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    return "updated", data


def main():
    p = argparse.ArgumentParser(description="Fetch latest verified domestic community report")
    p.add_argument("--output", type=Path, default=Path("domestic_telegram_latest.json"))
    p.add_argument("--allow-previous-day", action="store_true")
    args = p.parse_args()
    try:
        state, data = refresh_cache(args.output, not args.allow_previous_day)
        print(json.dumps({"state": state, "date_kst": data["date_kst"],
                          "observed_at_kst": data["observed_at_kst"],
                          "entries": len(data["entries"]),
                          "output": str(args.output)}, ensure_ascii=False))
        return 0 if state in ("updated", "unchanged") else 2
    except (HTTPError, URLError, OSError, ValueError, json.JSONDecodeError) as e:
        print(json.dumps({"state": "error", "detail": str(e)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
