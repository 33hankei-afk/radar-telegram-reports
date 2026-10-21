#!/usr/bin/env python3
"""On-demand public evidence for the existing ChatGPT daily report task.

This is source collection, never a replacement GPT report. It cannot overwrite
latest.json/latest.md or reports/. No new scheduled task is created.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from telegram_public import CHANNELS, collect_channel, now_kst, public_post, timestamp

REPOSITORY = '33hankei-afk/radar-telegram-reports'


def read_request(obj, now):
    if not isinstance(obj, dict) or obj.get('schema') != 'telegram_collection_request_v1':
        raise ValueError('invalid collection request schema')
    ident = obj.get('request_id', '')
    if not isinstance(ident, str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,80}', ident):
        raise ValueError('invalid request ID')
    day = date.fromisoformat(obj['date_kst'])
    if day.isoformat() != obj['date_kst'] or not timedelta(0) <= now.date() - day <= timedelta(days=2):
        raise ValueError('only current day or two-day recovery is supported')
    requested = timestamp(obj.get('requested_at_kst'))
    if not requested or requested > now + timedelta(minutes=5) or now - requested > timedelta(hours=2):
        raise ValueError('stale/future request: create a fresh ID with the actual current time')
    return ident, day


class GithubEvidenceWriter:
    """Write only collection/ via the runner's scoped built-in token."""
    def __init__(self, token):
        if not token:
            raise ValueError('GitHub Actions token unavailable')
        self.token = token

    def api(self, path, method='GET', value=None):
        if not path.startswith('collection/') or '..' in path:
            raise ValueError('evidence writer is restricted to collection/')
        url = 'https://api.github.com/repos/' + REPOSITORY + '/contents/' + quote(path, safe='/')
        if method == 'GET':
            url += '?ref=main'
        payload = json.dumps(value).encode() if value is not None else None
        req = Request(url, data=payload, method=method, headers={
            'Authorization': 'Bearer ' + self.token, 'Accept': 'application/vnd.github+json',
            'User-Agent': 'DayTradingRadar-Evidence/1', 'X-GitHub-Api-Version': '2022-11-28',
            'Content-Type': 'application/json'})
        with urlopen(req, timeout=20) as response:
            return json.load(response)

    def read(self, path):
        try:
            value = self.api(path)
        except HTTPError as exc:
            if exc.code == 404:
                return None, None
            raise
        return json.loads(base64.b64decode(value['content'])), value['sha']

    def write(self, path, value):
        raw = (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()
        for attempt in range(2):
            _, sha = self.read(path)
            document = {'message': 'Record public Telegram evidence ' + value.get('stage', ''),
                        'branch': 'main', 'content': base64.b64encode(raw).decode()}
            if sha:
                document['sha'] = sha
            try:
                self.api(path, 'PUT', document)
                check, _ = self.read(path)
                if check != value:
                    raise ValueError('evidence file read-back mismatch')
                return
            except HTTPError as exc:
                if attempt or exc.code not in (409, 422, 500, 502, 503, 504):
                    raise
        raise AssertionError('unreachable')


def collect(request, writer, artifact_dir, fetch=None, clock=now_kst):
    started = clock()
    ident, day = read_request(request, started)
    status_path = 'collection/status/' + ident + '.json'
    evidence_path = 'collection/snapshots/' + ident + '.json'
    if hasattr(writer, 'read'):
        previous, _ = writer.read(status_path)
        if previous is not None:
            if previous.get('stage') == 'finished':
                print('Request already finished; preserve its actual observation and counters.', flush=True)
                return previous
            raise ValueError('request ID already in use; create a fresh request ID')
    state = {'schema': 'telegram_collection_status_v1', 'request_id': ident,
             'date_kst': day.isoformat(), 'execution_date_kst': started.date().isoformat(),
             'status': 'running', 'stage': 'started', 'started_at_kst': started.isoformat(),
             'updated_at_kst': started.isoformat(), 'ended_at_kst': None,
             'checked_channels': 0, 'verified_full_channels': 0, 'verified_posts': 0,
             'searfin_status': 'pending', 'failed_channels': [], 'errors': [],
             'evidence_path': evidence_path, 'report_published': False}
    # A failed start write is retried once; never collect with a false start record.
    for attempt in range(2):
        try:
            writer.write(status_path, state)
            break
        except Exception:
            if attempt:
                raise
    posts, coverage = [], []
    artifact = Path(artifact_dir) / 'full_source.json'
    artifact.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + 8 * 60

    def evidence():
        return {'schema': 'telegram_public_evidence_v1', 'request_id': ident,
                'date_kst': day.isoformat(), 'started_at_kst': started.isoformat(),
                'observed_at_kst': clock().isoformat(), 'cutoff_at_kst': started.isoformat(),
                'text_only': True, 'report_published': False,
                'coverage': coverage, 'posts': [public_post(post) for post in posts],
                'note': 'Public HTML metadata verified. Short excerpts are evidence, not GPT summaries. '
                        'Full text is an expiring Actions artifact. Images/attachments need separate review.'}

    def checkpoint(final=False):
        domestic = [row for row in coverage if row['channel'] != 'searfin']
        state.update(checked_channels=len(domestic),
                     verified_full_channels=sum(row['status'] == 'complete' for row in domestic),
                     verified_posts=len(posts),
                     failed_channels=[r['channel'] for r in coverage if r['status'] == 'failed'],
                     updated_at_kst=clock().isoformat(),
                     searfin_status=next((r['status'] for r in coverage if r['channel'] == 'searfin'), 'pending'))
        for row in coverage:
            for warning in row['warnings']:
                detail = row['channel'] + ': ' + warning
                if detail not in state['errors']:
                    state['errors'].append(detail)
        if final:
            state.update(stage='finished', ended_at_kst=clock().isoformat(),
                         status=('complete' if len(coverage) == 60 and all(r['status'] == 'complete' for r in coverage)
                                 else 'partial' if posts else 'failed'))
        else:
            state['stage'] = 'collecting'
        # Publish the independently verified prefix before marking it available.
        writer.write(evidence_path, evidence())
        writer.write(status_path, state)
        writer.write('collection/latest.json', {**state, 'status_path': status_path})

    failure = None
    try:
        # SEARFin is early in the first small batch; never count it as channel 60/59.
        channels = ['searfin'] + CHANNELS
        with ThreadPoolExecutor(max_workers=2) as pool:
            for offset in range(0, len(channels), 5):
                batch = channels[offset:offset + 5]
                def work(channel):
                    args = {'clock': clock, 'deadline': deadline}
                    if fetch is not None:
                        args['fetch'] = fetch
                    return collect_channel(channel, day, started, **args)
                for values, row in pool.map(work, batch):
                    posts.extend(values)
                    coverage.append(row)
                if offset == 0 or (offset // 5) % 2 == 0:
                    checkpoint()
                print(json.dumps({'processed': len(coverage), 'verified_posts': len(posts),
                                  'full_channels': sum(r['status'] == 'complete' for r in coverage)}, ensure_ascii=False), flush=True)
        checkpoint(final=True)
    except Exception as exc:
        failure = exc
        state.update(status='failed', stage='collecting', updated_at_kst=clock().isoformat(),
                     ended_at_kst=clock().isoformat())
        state['errors'].append('collector/checkpoint failed: ' + type(exc).__name__)
        try:
            writer.write(status_path, state)
        except Exception:
            print('FINAL EVIDENCE STATUS WRITE FAILED', flush=True)
    finally:
        # This directory is uploaded as an authenticated Actions artifact, not committed.
        artifact.write_text(json.dumps({**evidence(), 'posts': posts}, ensure_ascii=False), encoding='utf-8')
    if failure:
        raise failure
    return state


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--request', type=Path, default=Path('collection/request.json'))
    parser.add_argument('--artifact-dir', default='collection-private')
    args = parser.parse_args()
    request = json.loads(args.request.read_text(encoding='utf-8'))
    result = collect(request, GithubEvidenceWriter(os.environ.get('GH_EVIDENCE_TOKEN', '')), args.artifact_dir)
    print(json.dumps({key: result[key] for key in ('request_id', 'status', 'checked_channels',
                                                  'verified_full_channels', 'verified_posts', 'failed_channels')}))
    if result['status'] == 'failed':
        raise SystemExit('No original posts verified; report/latest files were not changed.')


if __name__ == '__main__':
    main()
