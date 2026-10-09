#!/usr/bin/env python3
"""Validate verified-public-post daily Telegram reports; no third-party packages."""
import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

URL = re.compile(r"^https://t\.me/([A-Za-z0-9_]+)/([1-9][0-9]*)$")
KST = timedelta(hours=9)


def validate_report(data, markdown=None):
    errors = []
    if not isinstance(data, dict):
        return ["root must be an object"]
    if data.get("schema") != "telegram_summaries_v1":
        errors.append("schema must be telegram_summaries_v1")
    try:
        day = date.fromisoformat(data["date_kst"])
        if day.isoformat() != data["date_kst"]:
            raise ValueError("invalid date format")
    except (KeyError, TypeError, ValueError):
        errors.append("date_kst must be YYYY-MM-DD")
        day = None

    def validate_time(value, context, require_day=True):
        if not isinstance(value, str):
            errors.append(f"{context}: timestamp is required")
            return
        try:
            t = datetime.fromisoformat(value)
            if t.utcoffset() != KST:
                errors.append(f"{context}: timezone must be +09:00")
            elif require_day and day and t.date() != day:
                errors.append(f"{context}: date must match date_kst")
        except ValueError:
            errors.append(f"{context}: invalid ISO 8601 timestamp")

    validate_time(data.get("observed_at_kst"), "observed_at_kst")
    if not isinstance(data.get("coverage_note"), str):
        errors.append("coverage_note must be a string")
    entries = data.get("entries")
    if not isinstance(entries, list):
        errors.append("entries must be an array")
        entries = []
    url_index = {}
    for idx, item in enumerate(entries):
        where = f"entries[{idx}]"
        if not isinstance(item, dict):
            errors.append(f"{where}: must be an object")
            continue
        channel = item.get("channel")
        post_id = item.get("post_id")
        url = item.get("url")
        if not isinstance(channel, str) or not re.fullmatch(r"[A-Za-z0-9_]{5,}", channel):
            errors.append(f"{where}: invalid verified channel handle")
        if not isinstance(post_id, str) or not re.fullmatch(r"[1-9][0-9]*", post_id):
            errors.append(f"{where}: invalid post_id")
        m = URL.fullmatch(url) if isinstance(url, str) else None
        if not m:
            errors.append(f"{where}: invalid direct Telegram URL")
        elif channel != m.group(1) or post_id != m.group(2):
            errors.append(f"{where}: URL does not match channel/post_id")
        elif url in url_index:
            errors.append(f"{where}: duplicate post URL {url}")
        else:
            url_index[url] = item
        if not isinstance(item.get("views_display"), str) or not item["views_display"].strip():
            errors.append(f"{where}: observed views_display is required")
        validate_time(item.get("published_at_kst"), f"{where}.published_at_kst")
        for field in ("title", "summary_ko"):
            if not isinstance(item.get(field), str):
                errors.append(f"{where}: {field} must be a string")

    top20 = data.get("top20_urls", [])
    themes = data.get("theme_urls", [])
    for field, urls in (("top20_urls", top20), ("theme_urls", themes)):
        if not isinstance(urls, list):
            errors.append(f"{field}: must be an array")
            continue
        if field == "top20_urls" and len(urls) > 20:
            errors.append("top20_urls: more than 20")
        if len(set(map(str, urls))) != len(urls):
            errors.append(f"{field}: duplicate URL")
        for url in urls:
            if url not in url_index:
                errors.append(f"{field}: missing verified entry for {url}")
    for field in ("consensus_up", "consensus_down"):
        items = data.get(field, [])
        if not isinstance(items, list):
            errors.append(f"{field}: must be an array")
            continue
        for i, item in enumerate(items):
            where = f"{field}[{i}]"
            if not isinstance(item, dict):
                errors.append(f"{where}: must be an object")
                continue
            if item.get("url") not in url_index:
                errors.append(f"{where}: missing verified entry for URL")
            elif (item.get("channel") != url_index[item["url"]].get("channel") or
                  item.get("post_id") != url_index[item["url"]].get("post_id")):
                errors.append(f"{where}: channel/post_id mismatch")
            if not isinstance(item.get("company"), str) or not item["company"].strip():
                errors.append(f"{where}: company is required")
            validate_time(item.get("published_at_kst"), f"{where}.published_at_kst")

    coverage = data.get("coverage")
    if coverage is not None:
        if not isinstance(coverage, dict):
            errors.append("coverage must be an object")
        else:
            if coverage.get("target_channels") != 59:
                errors.append("coverage.target_channels must be 59")
            verified = coverage.get("verified_full_channels")
            if verified is not None and (type(verified) is not int or not 0 <= verified <= 59):
                errors.append("coverage.verified_full_channels must be 0..59")
            if coverage.get("observed_post_count") is not None and coverage["observed_post_count"] != len(entries):
                errors.append("coverage.observed_post_count must equal len(entries)")
    if markdown is not None:
        for url in set((top20 if isinstance(top20, list) else []) +
                       (themes if isinstance(themes, list) else []) +
                       [r.get("url") for f in ("consensus_up", "consensus_down")
                        for r in (data.get(f, []) if isinstance(data.get(f, []), list) else [])
                        if isinstance(r, dict)]):
            if isinstance(url, str) and f"[{url}]({url})" not in markdown:
                errors.append(f"markdown must show clickable FULL original URL: {url}")
    return errors


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("json_file", type=Path)
    parser.add_argument("--markdown", type=Path)
    args = parser.parse_args()
    try:
        data = json.loads(args.json_file.read_text(encoding="utf-8"))
        md = args.markdown.read_text(encoding="utf-8") if args.markdown else None
        errors = validate_report(data, md)
    except (OSError, UnicodeError, json.JSONDecodeError) as e:
        errors = [str(e)]
    if errors:
        print("INVALID REPORT:", file=sys.stderr)
        for err in errors:
            print(" - " + err, file=sys.stderr)
        return 1
    print("VALID REPORT:", args.json_file)
    return 0


if __name__ == "__main__":
    sys.exit(main())
