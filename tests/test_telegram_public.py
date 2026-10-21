import sys
import unittest
from datetime import datetime, date
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from telegram_public import KST, CHANNELS, parse_page, collect_channel, public_post, preview_url, revision_values
from collect_telegram_public import collect, read_request

NOW = datetime(2026, 10, 21, 12, 0, tzinfo=KST)


def widget(number, stamp, text='HBM 서버 메모리', counter='1.2K', channel='faststocknews', footer=None):
    return (f'<div class="tgme_widget_message" data-post="{channel}/{number}">'
            '<div class="tgme_widget_message_forwarded_from"><time datetime="2020-01-01T00:00:00Z"></time></div>'
            f'<div class="tgme_widget_message_text">{text}</div>'
            f'<span class="tgme_widget_message_views">{counter}</span>'
            f'<a class="tgme_widget_message_date" href="{footer or f"https://t.me/{channel}/{number}"}">'
            f'<time datetime="{stamp}">12:00</time></a></div>')


class PublicSourceTests(unittest.TestCase):
    def test_exact_footer_time_and_counter(self):
        posts, _, _ = parse_page(widget(2, '2026-10-20T15:01:00Z'), 'faststocknews', NOW)
        self.assertEqual(posts[0]['published_at_kst'], '2026-10-21T00:01:00+09:00')
        self.assertEqual(posts[0]['views_display'], '1.2K')
        self.assertTrue(posts[0]['verified'])

    def test_naive_date_and_forged_permalink_are_not_verified(self):
        for stamp, footer in [('12:00', None), ('2026-10-21T12:00:00', None),
                              ('2026-10-21T01:00:00Z', 'https://t.me/faststocknews/999')]:
            posts, _, _ = parse_page(widget(2, stamp, footer=footer), 'faststocknews', NOW)
            self.assertFalse(posts[0]['verified'])

    def test_pagination_reaches_midnight_and_excludes_other_days(self):
        page = widget(11, '2026-10-21T01:00:00Z') + '<a href="/s/faststocknews?before=11">older</a>'
        old = widget(10, '2026-10-20T15:01:00Z') + widget(9, '2026-10-20T14:59:59Z')
        posts, state = collect_channel('faststocknews', date(2026, 10, 21), NOW,
                                      fetch=lambda u: old if '?before=' in u else page, clock=lambda: NOW)
        self.assertEqual([p['post_id'] for p in posts], ['10', '11'])
        self.assertEqual(state['status'], 'complete')
        self.assertEqual(state['pages'], 2)

    def test_http200_outage_is_not_an_empty_day(self):
        posts, state = collect_channel('faststocknews', NOW.date(), NOW,
                                      fetch=lambda u: '<h1>Site Unavailable</h1>', clock=lambda: NOW)
        self.assertEqual(posts, [])
        self.assertEqual(state['status'], 'failed')
        self.assertFalse(state['boundary_verified'])

    def test_empty_today_requires_a_previous_day_boundary(self):
        posts, state = collect_channel('faststocknews', NOW.date(), NOW,
                                      fetch=lambda u: widget(10, '2026-10-20T01:00:00Z'), clock=lambda: NOW)
        self.assertEqual(posts, [])
        self.assertEqual(state['status'], 'complete')

    def test_missing_views_never_enters_verified_posts(self):
        source = widget(11, '2026-10-21T01:00:00Z', counter='') + widget(10, '2026-10-20T01:00:00Z')
        posts, state = collect_channel('faststocknews', NOW.date(), NOW, fetch=lambda u: source, clock=lambda: NOW)
        self.assertEqual(posts, [])
        self.assertEqual(state['status'], 'partial')
        self.assertEqual(state['missing_views'], 1)

    def test_no_older_link_is_partial_not_complete(self):
        posts, state = collect_channel('faststocknews', NOW.date(), NOW,
                                      fetch=lambda u: widget(10, '2026-10-21T01:00:00Z'), clock=lambda: NOW)
        self.assertEqual(len(posts), 1)
        self.assertEqual(state['status'], 'partial')

    def test_recovery_uses_actual_observation_and_original_day(self):
        posts, state = collect_channel('faststocknews', date(2026, 10, 20), NOW,
                                      fetch=lambda u: widget(10, '2026-10-20T01:00:00Z') + widget(9, '2026-10-19T01:00:00Z'),
                                      clock=lambda: NOW)
        self.assertEqual(posts[0]['observed_at_kst'], NOW.isoformat())
        self.assertTrue(posts[0]['published_at_kst'].startswith('2026-10-20'))
        self.assertTrue(state['window_end_kst'].startswith('2026-10-20'))

    def test_unapproved_urls_and_stale_requests_rejected(self):
        for url in ('https://example.org/s/faststocknews', 'https://t.me/joinchat/a',
                    'https://t.me/s/unlistedhandle', 'https://t.me/s/faststocknews?before=bad'):
            with self.assertRaises(ValueError):
                preview_url(url)
        with self.assertRaises(ValueError):
            read_request({'schema': 'telegram_collection_request_v1', 'request_id': 'test-123456',
                          'date_kst': '2026-10-10', 'requested_at_kst': NOW.isoformat()}, NOW)

    def test_revision_keeps_rounded_source_values_and_separate_rounds(self):
        body = ('12MF 영업이익 컨센서스 리비전 2026-10-19 대비\n상향 TOP1\n'
                '1. NC `036570` +3.2% 5,994억원 → 6,184억원 (+189억원)\n'
                '하향 TOP1\n1. NAVER `035420` -0.2% 2.54조원 → 2.54조원 (-63억원)')
        rows = revision_values(body)
        self.assertEqual([r['direction'] for r in rows], ['상향', '하향'])
        self.assertEqual(rows[0]['change_absolute'], '+189억원')
        self.assertEqual(rows[1]['before'], rows[1]['after'])
        self.assertEqual(rows[0]['basis_date'], '2026-10-19')

    def test_public_index_has_short_excerpt_and_no_full_body(self):
        posts, _, _ = parse_page(widget(10, '2026-10-21T01:00:00Z', 'HBM ' + '단어 ' * 100), 'faststocknews', NOW)
        row = public_post({**posts[0], 'source_page_url': 'https://t.me/s/faststocknews'})
        self.assertNotIn('body_text', row)
        self.assertLessEqual(len(row['source_excerpt'].split()), 24)
        self.assertFalse(row['excerpt_complete'])

    def test_all_channels_checkpoint_and_no_report_overwrite(self):
        class MemoryWriter:
            def __init__(self):
                self.files = {}
                self.checked = []
            def write(self, path, value):
                self.assert_path(path)
                self.files[path] = value.copy()
                if '/status/' in path:
                    self.checked.append(value['checked_channels'])
            def assert_path(self, path):
                assert path.startswith('collection/')
        writer = MemoryWriter()
        def fetch(url):
            channel = url.split('/s/')[1].split('?')[0]
            return widget(2, '2026-10-21T01:00:00Z', channel=channel) + widget(1, '2026-10-20T01:00:00Z', channel=channel)
        with TemporaryDirectory() as folder:
            result = collect({'schema': 'telegram_collection_request_v1', 'request_id': 'test-123456',
                              'date_kst': NOW.date().isoformat(), 'requested_at_kst': NOW.isoformat()},
                             writer, folder, fetch=fetch, clock=lambda: NOW)
            self.assertTrue((Path(folder) / 'full_source.json').is_file())
        self.assertEqual(result['verified_full_channels'], 59)
        self.assertEqual(result['checked_channels'], 59)
        self.assertEqual(result['verified_posts'], 60)
        self.assertEqual(writer.checked[:2], [0, 4])
        self.assertFalse(result['report_published'])


if __name__ == '__main__':
    unittest.main()
