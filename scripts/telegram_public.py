"""Read public Telegram HTML, preserving source timestamps and display counters.

No Exa, account, Telegram API, translation service, or broker dependency.
Full source text is an ephemeral Actions artifact; the public evidence index
contains identifiers, checksums, short excerpts and structured revision values.
"""
from __future__ import annotations

import hashlib
import re
import socket
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urljoin, urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener

KST = timezone(timedelta(hours=9))
CHANNELS = '''faststocknews insidertracking corevalue yeouidostory2 bornlupin
one_going yeouido_lab bullishbee11 gaoshoukorea faststocknewsusa tazastock
growthresearch ym_research bulls_pirates shmstory realtime_stock_news kwusa
hs_academy bumgore hanachina brain_and_body_research aetherjapanresearch
hedgecat0301 ehdwl pharmbiohana sypark_strategy habit4117 meritz_research
magonia_b jeilstock jstockclass stock_messenger pikachu_aje HanaResearch
kimcharger TNBfolio earlystock1 huhpharm meritz_tech easobi daegurr
macrojunglemicrolens sejongdata2013 smallcap tlsrltnf awake_realtimecheck egzion
cahier_de_market eqmirae survival_DoPB report_figure_by_offset yieldnspread
shinhanresearch athletes_village bio_shinhan goupstock rafikiresearch
maddingStock globaletfi'''.split()
assert len(CHANNELS) == len({c.lower() for c in CHANNELS}) == 59
POST_ID = re.compile(r'^([A-Za-z0-9_]{5,32})/([1-9][0-9]*)$')
VOID = {'br', 'img', 'hr', 'input', 'meta', 'link', 'source', 'area', 'wbr', 'embed', 'param', 'col'}
TOPICS = re.compile(r'메모리|디램|낸드|반도체|파운드리|웨이퍼|전공정|후공정|팹리스|유리기판|'
                    r'인공지능|생성형|거대언어|데이터\s*센터|엔비디아|하이닉스|마이크론|삼성전자|'
                    r'광통신|광반도체|실리콘\s*포토닉스|'
                    r'\b(?:AI|HBM\w*|DRAM|NAND|DDR\w*|LPDDR\w*|GDDR\w*|memory|'
                    r'semiconductor\w*|chip\w*|TSMC|NVIDIA|NVDA|AMD|ASML|AVGO|INTC|'
                    r'Micron|GPU|CPU|ASIC|CoWoS|CoPoS|CPO|EML|LLM\w*|GPT\w*|'
                    r'ChatGPT|OpenAI|Anthropic|Claude|Gemini|artificial intelligence|'
                    r'data\s*cent(?:er|re)s?)\b', re.I)
REVISION = re.compile(r'영업(?:이익|익).*컨센.*(?:리비전|수정)|'
                      r'컨센.*(?:리비전|수정).*영업(?:이익|익)', re.S)
REVISION_ROW = re.compile(
    r'(?m)^\s*(?P<rank>\d+)\.\s+(?P<company>[^\n]+?)\s+`?(?P<ticker>\d{6})`?\s+'
    r'(?P<change_percent>[+\-−]?\d[\d,.]*\s*%)\s+'
    r'(?P<before>[+\-−]?\s*\d[\d,.]*\s*(?:조원|억원|백만원|원))\s*[→➡➝]\s*'
    r'(?P<after>[+\-−]?\s*\d[\d,.]*\s*(?:조원|억원|백만원|원))\s*'
    r'\((?P<change_absolute>[^)]+)\)')


def now_kst():
    return datetime.now(KST)


def timestamp(value):
    try:
        result = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return result.astimezone(KST) if result.tzinfo is not None else None
    except (ValueError, TypeError):
        return None


def views_estimate(display):
    match = re.fullmatch(r'(\d+(?:\.\d+)?)([KMB]?)', re.sub(r'[\s,\u2009\u202f]', '', display), re.I)
    return float(Decimal(match[1]) * {'': 1, 'K': 1000, 'M': 1000000, 'B': 1000000000}[match[2].upper()]) if match else None


def preview_url(url, channel=None):
    p = urlsplit(url)
    allowed = {c.lower() for c in CHANNELS} | {'searfin'}
    match = re.fullmatch(r'/s/([A-Za-z0-9_]{5,32})/?', p.path)
    if (p.scheme != 'https' or p.netloc != 't.me' or not match
            or match[1].lower() not in allowed
            or (channel and match[1].lower() != channel.lower())):
        raise ValueError('not an approved public channel preview')
    q = parse_qs(p.query)
    if p.fragment or set(q) - {'before'} or ('before' in q and not re.fullmatch(r'[1-9][0-9]*', q['before'][0])):
        raise ValueError('invalid public preview pagination')
    return url


class PublicRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        preview_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_public_html(url):
    preview_url(url)
    req = Request(url, headers={'User-Agent': 'Mozilla/5.0 DayTradingRadar-PublicEvidence/1',
                                'Accept-Language': 'ko-KR,ko;q=0.9,en;q=0.7'})
    for attempt in range(2):
        try:
            with build_opener(PublicRedirect()).open(req, timeout=12) as response:
                preview_url(response.geturl())
                raw = response.read(4_000_001)
            if len(raw) > 4_000_000:
                raise ValueError('public preview exceeds size limit')
            text = raw.decode('utf-8', errors='strict')
            # A 200 status may still be an outage or interstitial, never an empty day.
            if not re.search(r'data-post\s*=', text):
                raise ValueError('public preview has no message identifiers (possibly unavailable)')
            return text
        except (HTTPError, URLError, TimeoutError, socket.timeout) as exc:
            retryable = not isinstance(exc, HTTPError) or exc.code in (408, 429, 500, 502, 503, 504)
            if attempt or not retryable:
                raise
            time.sleep(0.5)
    raise AssertionError('unreachable')


@dataclass
class Node:
    tag: str
    attrs: dict = field(default_factory=dict)
    children: list = field(default_factory=list)

    def has(self, name):
        return name in self.attrs.get('class', '').split()

    def walk(self):
        yield self
        for child in self.children:
            if isinstance(child, Node):
                yield from child.walk()

    def text(self):
        if self.tag == 'br':
            return '\n'
        if self.tag == 'img':
            return self.attrs.get('alt', '') if self.has('emoji') else ''
        if self.tag in ('script', 'style'):
            return ''
        return ''.join(child.text() if isinstance(child, Node) else child for child in self.children)


class PageParser(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.root = Node('root')
        self.stack = [self.root]
        self.feed(source)
        self.close()

    def handle_starttag(self, tag, attrs):
        child = Node(tag, dict(attrs))
        self.stack[-1].children.append(child)
        if tag not in VOID:
            self.stack.append(child)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.stack.pop()

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def revision_values(text):
    rows = []
    period = re.search(r'12MF|\d{2,4}\s*[.년/-]?\s*[1-4]\s*Q|\d{2,4}년?\s*[1-4]분기|\d{4}년|연간|분기', text, re.I)
    basis = re.search(r'(\d{4}[-.]\d{1,2}[-.]\d{1,2})\s*대비', text)
    for match in REVISION_ROW.finditer(text):
        sections = list(re.finditer('상향|하향', text[:match.start()]))
        if not sections:
            continue
        rows.append({**match.groupdict(), 'direction': sections[-1][0],
                     'period': period[0] if period else '', 'basis_date': basis[1] if basis else ''})
    return rows


def parse_page(source, requested_channel, observed_at):
    root = PageParser(source).root
    posts, warnings, older = [], [], None
    for node in root.walk():
        href = node.attrs.get('href', '')
        if '?before=' in href:
            candidate = urljoin('https://t.me', href)
            try:
                preview_url(candidate, requested_channel)
                older = candidate
            except ValueError:
                pass
        if not node.has('tgme_widget_message') or not node.attrs.get('data-post'):
            continue
        match = POST_ID.fullmatch(node.attrs['data-post'])
        if not match or match[1].lower() != requested_channel.lower():
            warnings.append('message identifier/channel mismatch')
            continue
        channel, post_id = match.groups()
        children = list(node.walk())
        footer = [n for n in children if n.has('tgme_widget_message_date')]
        times = [n for f in footer for n in f.walk() if n.tag == 'time']
        published = timestamp(times[-1].attrs.get('datetime')) if times else None
        expected = f'https://t.me/{channel}/{post_id}'
        permalinks = [f.attrs.get('href', '').rstrip('/') for f in footer]
        valid_link = any(url.lower() == expected.lower() for url in permalinks)
        counters = [n.text().strip() for n in children if n.has('tgme_widget_message_views')]
        counter = counters[-1] if counters else ''
        body = '\n'.join(n.text() for n in children if n.has('tgme_widget_message_text')).strip()
        pinned = any(n.has('tgme_widget_message_pinned') or n.has('tgme_widget_message_pin') for n in children)
        media = any(n.has('tgme_widget_message_error') or n.has('tgme_widget_message_photo_wrap')
                    or n.has('tgme_widget_message_video_wrap') or n.has('tgme_widget_message_document_wrap') for n in children)
        problems = []
        if not published:
            problems.append('absolute publication timestamp missing')
        if not valid_link:
            problems.append('original permalink mismatch')
        if views_estimate(counter) is None:
            problems.append('view counter missing/invalid')
        posts.append({'channel': channel, 'post_id': post_id, 'url': expected,
                      'published_at_kst': published.isoformat() if published else '',
                      'observed_at_kst': observed_at.astimezone(KST).isoformat(),
                      'views_display': counter, 'body_text': body,
                      'body_sha256': hashlib.sha256(body.encode()).hexdigest(),
                      'pinned': pinned, 'needs_media_review': media or not body,
                      'verified': not problems, 'problems': problems,
                      'related': bool(TOPICS.search(body)),
                      'is_revision': channel.lower() == 'searfin' and bool(REVISION.search(body)),
                      'revision_rows': revision_values(body) if channel.lower() == 'searfin' and REVISION.search(body) else []})
    return posts, older, warnings


def collect_channel(channel, day, cutoff, fetch=fetch_public_html, clock=now_kst,
                    max_pages=40, deadline=None):
    start = datetime.combine(day, datetime.min.time(), tzinfo=KST)
    end = min(cutoff, start + timedelta(days=1) - timedelta(microseconds=1))
    state = {'channel': channel, 'status': 'partial', 'pages': 0, 'verified_posts': 0,
             'unknown_dates': 0, 'missing_views': 0, 'media_review': 0,
             'boundary_verified': False, 'warnings': [], 'window_end_kst': end.isoformat()}
    posts, seen, unknown = {}, set(), set()
    url = f'https://t.me/s/{channel}'
    try:
        while url:
            if deadline and time.monotonic() >= deadline:
                state['warnings'].append('execution time limit before day boundary')
                break
            if url in seen or state['pages'] >= max_pages:
                state['warnings'].append('repeated page or pagination safety limit')
                break
            seen.add(url)
            source = fetch(url)
            observed = clock()
            page, older, warnings = parse_page(source, channel, observed)
            state['pages'] += 1
            state['warnings'].extend(warnings)
            if not page:
                state['warnings'].append('no original public posts; absence of posts is unverified')
                break
            ordinary = []
            for post in page:
                stamp = timestamp(post['published_at_kst'])
                if not stamp:
                    unknown.add(post['post_id'])
                    continue
                if not post['pinned']:
                    ordinary.append((int(post['post_id']), stamp))
                if start <= stamp <= end:
                    if post['verified']:
                        posts.setdefault(post['url'], {**post, 'source_page_url': url})
                    else:
                        state['missing_views'] += int('view counter missing/invalid' in post['problems'])
                        state['warnings'].append('#' + post['post_id'] + ': ' + ', '.join(post['problems']))
            if ordinary and (min(ordinary)[1] < start or min(ordinary)[0] == 1):
                state['boundary_verified'] = True
                state['status'] = 'complete' if not unknown and not state['warnings'] else 'partial'
                break
            if not older:
                state['warnings'].append('older link missing before verified midnight boundary')
                break
            minimum = min(int(p['post_id']) for p in page if not p['pinned']) if ordinary else min(int(p['post_id']) for p in page)
            if int(parse_qs(urlsplit(older).query)['before'][0]) > minimum:
                state['warnings'].append('pagination does not move backwards')
                break
            url = older
            time.sleep(0.15)
    except Exception as exc:
        # Avoid leaking headers, credentials, arbitrary response text or page instructions.
        state['warnings'].append('public read failed: ' + type(exc).__name__ +
                                 (f' HTTP {exc.code}' if isinstance(exc, HTTPError) else '') +
                                 (': ' + str(exc) if isinstance(exc, ValueError) else ''))
        state['status'] = 'partial' if posts else 'failed'
    values = sorted(posts.values(), key=lambda p: (p['published_at_kst'], int(p['post_id'])))
    state.update(verified_posts=len(values), unknown_dates=len(unknown),
                 media_review=sum(p['needs_media_review'] for p in values),
                 checked_at_kst=clock().isoformat())
    if not values and not state['boundary_verified']:
        state['status'] = 'failed'
    return values, state


def public_post(post):
    """Keep public evidence small; full bodies are only in an expiring artifact."""
    fields = ('channel', 'post_id', 'url', 'published_at_kst', 'observed_at_kst',
              'views_display', 'body_sha256', 'source_page_url', 'needs_media_review',
              'related', 'is_revision', 'revision_rows')
    result = {key: post[key] for key in fields}
    text = post['body_text']
    match = TOPICS.search(text)
    offset = max(0, text.rfind('\n', 0, match.start()) + 1) if match else 0
    result['source_excerpt'] = ' '.join(text[offset:].split()[:24])[:450]
    result['excerpt_complete'] = text.strip() == result['source_excerpt']
    return result
