import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from validate_report import validate_report


def document():
    return {'schema': 'telegram_summaries_v1', 'date_kst': '2026-10-20',
            'observed_at_kst': '2026-10-21T12:45:00+09:00', 'coverage_note': '복구',
            'recovery': {'target_date_kst': '2026-10-20', 'recollected_at_kst': '2026-10-21T12:45:00+09:00',
                         'reason': '실제 원문 재조회'},
            'entries': [{'channel': 'faststocknews', 'post_id': '123', 'url': 'https://t.me/faststocknews/123',
                         'published_at_kst': '2026-10-20T12:00:00+09:00', 'views_display': '1.2K',
                         'title': '검증', 'summary_ko': '검증'}]}


class RecoveryTests(unittest.TestCase):
    def test_actual_recollection_is_allowed_without_changing_post_day(self):
        self.assertEqual(validate_report(document()), [])

    def test_unmarked_date_shift_and_wrong_post_day_are_rejected(self):
        doc = document(); doc.pop('recovery')
        self.assertTrue(validate_report(doc))
        doc = document(); doc['entries'][0]['published_at_kst'] = '2026-10-21T12:00:00+09:00'
        self.assertTrue(validate_report(doc))

    def test_recovery_timestamp_and_day_must_match(self):
        for change in ({'target_date_kst': '2026-10-19'}, {'recollected_at_kst': '2026-10-20T21:00:00+09:00'}, {'reason': ''}):
            doc = document(); doc['recovery'].update(change)
            self.assertTrue(validate_report(doc))


if __name__ == '__main__':
    unittest.main()
