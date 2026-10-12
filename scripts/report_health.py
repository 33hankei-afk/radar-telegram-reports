#!/usr/bin/env python3
"""Check GitHub report publication, independent of the ChatGPT scheduler.

A successful invocation proves the files' presence and structural validity only.
It does not prove that all 59 Telegram channels were collected.
"""
from __future__ import annotations
import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from validate_report import validate_report

KST = timezone(timedelta(hours=9))


def inspect(root: Path, now: datetime) -> dict:
    day = now.astimezone(KST).date().isoformat()
    result = {
        "check_date_kst": day,
        "checked_at_kst": now.astimezone(KST).isoformat(timespec="seconds"),
        "status": "missing",
        "report_date_kst": None,
        "entry_count": 0,
        "verified_full_channels": None,
        "ranking_complete": None,
        "latest_report_url": "https://github.com/33hankei-afk/radar-telegram-reports/blob/main/latest.md",
        "errors": [],
        "note": "This checks publication and schema, not Telegram source authenticity or PC installation."
    }
    latest_json, latest_md = root / "latest.json", root / "latest.md"
    if not latest_json.is_file() or not latest_md.is_file():
        result["errors"].append("latest.json or latest.md missing")
        return result
    try:
        obj = json.loads(latest_json.read_text(encoding="utf-8"))
        markdown = latest_md.read_text(encoding="utf-8")
        result["report_date_kst"] = obj.get("date_kst")
        result["entry_count"] = len(obj.get("entries", [])) if isinstance(obj.get("entries"), list) else 0
        coverage = obj.get("coverage", {})
        if isinstance(coverage, dict):
            result["verified_full_channels"] = coverage.get("verified_full_channels")
            result["ranking_complete"] = coverage.get("ranking_complete")
        errors = validate_report(obj, markdown)
        report_day = obj.get("date_kst")
        archived_json = root / "reports" / (str(report_day) + ".json")
        archived_md = root / "reports" / (str(report_day) + ".md")
        if not archived_json.is_file() or not archived_md.is_file():
            errors.append("matching reports/YYYY-MM-DD.json and .md are missing")
        else:
            archived = json.loads(archived_json.read_text(encoding="utf-8"))
            if archived != obj:
                errors.append("latest.json differs from dated JSON report")
            errors.extend(validate_report(archived, archived_md.read_text(encoding="utf-8")))
        if errors:
            result["status"] = "invalid"
            result["errors"] = errors[:30]
        elif report_day != day:
            result["status"] = "stale"
            result["errors"] = [f"today {day}, latest report {report_day}"]
        else:
            result["status"] = "published_partial" if (
                result["verified_full_channels"] != 59 or result["ranking_complete"] is not True
            ) else "published"
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        result["status"] = "invalid"
        result["errors"] = [type(exc).__name__ + ": " + str(exc)[:250]]
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, default=Path("status/latest.json"))
    parser.add_argument("--as-of", help="YYYY-MM-DD for repeatable offline tests")
    args = parser.parse_args()
    now = datetime.now(KST)
    if args.as_of:
        from datetime import date, time
        now = datetime.combine(date.fromisoformat(args.as_of), time(21, 35), tzinfo=KST)
    result = inspect(args.root, now)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("check_date_kst", "status", "report_date_kst", "entry_count", "errors")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
