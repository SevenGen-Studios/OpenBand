import unittest
from datetime import date

from tools.events_discovery import (
    choose_event_date,
    event_category,
    event_dates,
    event_status,
    extract_html_events,
    is_publishable_event,
    merge_events,
)


COMMUNITY = {
    "bandId": 378,
    "communityName": "Carry the Kettle Nakoda Nation",
    "aliases": ["CTK"],
}
SOURCE = {
    "type": "Official First Nation Website",
    "name": "Carry the Kettle Nakoda Nation",
    "official": True,
    "associationConfidence": 1.0,
}


class EventDateTests(unittest.TestCase):
    def test_explicit_date_range(self):
        self.assertEqual(
            event_dates("Annual Powwow August 21-23, 2026", date(2026, 8, 13)),
            [("2026-08-21", "2026-08-23")],
        )

    def test_yearless_flyer_uses_nearest_viable_year(self):
        self.assertEqual(
            choose_event_date("Treaty Day September 4", "Treaty Day September 4", date(2026, 8, 13)),
            ("2026-09-04", None),
        )

    def test_publication_date_does_not_beat_upcoming_event_date(self):
        self.assertEqual(
            choose_event_date(
                "Community gathering",
                "Posted August 1, 2026. Join us September 12, 2026 at 10:00 AM.",
                date(2026, 8, 13),
            ),
            ("2026-09-12", None),
        )

    def test_explicit_year_beats_yearless_calendar_heading(self):
        self.assertEqual(
            choose_event_date(
                "Sep 10 Wellness clinic Wednesday, September 10, 2025",
                "Sep 10 Wellness clinic Wednesday, September 10, 2025",
                date(2026, 8, 13),
            ),
            (None, None),
        )

    def test_first_event_date_beats_later_agenda_date(self):
        self.assertEqual(
            choose_event_date(
                "Sep 12 Annual General Meeting Saturday, September 12, 2026",
                "Agenda will be posted after August 18, 2026.",
                date(2026, 8, 13),
            ),
            ("2026-09-12", None),
        )

    def test_statuses(self):
        today = date(2026, 8, 13)
        self.assertEqual(event_status("2026-08-13", None, today), "Ongoing")
        self.assertEqual(event_status("2026-08-20", None, today), "Upcoming")
        self.assertEqual(event_status("2026-08-01", None, today), "Recently held")


class EventExtractionTests(unittest.TestCase):
    def test_json_ld_event_is_extracted(self):
        html = """
        <html><head><script type="application/ld+json">
        {"@context":"https://schema.org","@type":"Event","name":"Annual Community Powwow",
         "startDate":"2026-08-21","endDate":"2026-08-23",
         "location":{"@type":"Place","name":"Community Grounds"},
         "url":"https://example.org/powwow","description":"Everyone is welcome."}
        </script></head><body></body></html>
        """
        events, _, _ = extract_html_events(
            html, "https://example.org/events", COMMUNITY, SOURCE, date(2026, 8, 13)
        )
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["startDate"], "2026-08-21")
        self.assertEqual(events[0]["category"], "Culture & Language")
        self.assertEqual(events[0]["location"], "Community Grounds")
        self.assertEqual(events[0]["extractionMethod"], "json-ld")

    def test_dated_event_card_is_extracted(self):
        html = """
        <article class="event-card">
          <h2>Community Health Fair</h2>
          <p>Date: September 9, 2026</p><p>Location: Community Hall</p>
          <a href="/health-fair">Event details</a>
        </article>
        """
        events, follow, _ = extract_html_events(
            html, "https://example.org/events", COMMUNITY, SOURCE, date(2026, 8, 13)
        )
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["startDate"], "2026-09-09")
        self.assertEqual(events[0]["category"], "Health & Wellness")
        self.assertEqual(events[0]["location"], "Community Hall")
        self.assertIn("https://example.org/health-fair", follow)

    def test_job_posting_is_not_an_event(self):
        html = """
        <article class="event-card"><h2>Employment Opportunity</h2>
        <p>Job posting closes September 9, 2026.</p><a href="/job">Read more</a></article>
        """
        events, _, _ = extract_html_events(
            html, "https://example.org", COMMUNITY, SOURCE, date(2026, 8, 13)
        )
        self.assertEqual(events, [])

    def test_merge_deduplicates_same_source_event(self):
        item = {
            "id": "one", "bandId": 378, "title": "Annual Powwow",
            "startDate": "2026-08-21", "sourceUrl": "https://example.org/powwow",
            "description": "Event date: August 21, 2026", "confidence": 0.9,
            "extractionMethod": "html",
        }
        duplicate = {**item, "id": "two", "confidence": 0.95}
        rows = merge_events([item], [duplicate], date(2026, 8, 13))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["confidence"], 0.95)

    def test_merge_deduplicates_one_source_url_across_dates(self):
        first = {
            "id": "one", "bandId": 378, "title": "Annual Powwow August 21, 2026",
            "startDate": "2026-08-21", "sourceUrl": "https://example.org/powwow",
            "description": "Event date: August 21, 2026", "confidence": 0.9,
            "extractionMethod": "html",
        }
        duplicate = {
            **first, "id": "two", "startDate": "2026-08-23",
            "title": "Annual Powwow August 21-23, 2026", "endDate": "2026-08-23",
        }
        rows = merge_events([], [first, duplicate], date(2026, 8, 13))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["endDate"], "2026-08-23")

    def test_stored_html_date_must_match_source_year(self):
        stale = {
            "id": "stale", "bandId": 378,
            "title": "Sep 10 Wellness clinic Wednesday, September 10, 2025",
            "startDate": "2026-09-10", "sourceUrl": "https://example.org/clinic",
            "description": "Sep 10 Wellness clinic Wednesday, September 10, 2025",
            "confidence": 0.9, "extractionMethod": "html",
        }
        self.assertFalse(is_publishable_event(stale))

    def test_stored_html_date_must_match_first_event_date(self):
        wrong = {
            "id": "wrong", "bandId": 378,
            "title": "Sep 12 Annual General Meeting Saturday, September 12, 2026",
            "startDate": "2026-08-18", "sourceUrl": "https://example.org/agm",
            "description": "Agenda will be posted after August 18, 2026.",
            "confidence": 0.9, "extractionMethod": "html",
        }
        self.assertFalse(is_publishable_event(wrong))

    def test_merge_rejects_archive_and_job_false_positives(self):
        archive = {
            "id": "archive", "bandId": 378, "title": "Older Posts",
            "startDate": "2026-08-21", "sourceUrl": "https://example.org/category/events",
            "description": "Powwow August 21, 2026", "confidence": 0.9,
            "extractionMethod": "html",
        }
        job = {
            "id": "job", "bandId": 378, "title": "Job Opportunity - SaskPower",
            "startDate": "2026-08-21", "sourceUrl": "https://example.org/job",
            "description": "Community job posting closes August 21, 2026", "confidence": 0.9,
            "extractionMethod": "html",
        }
        self.assertEqual(merge_events([], [archive, job], date(2026, 8, 13)), [])

    def test_scripts_and_styles_do_not_create_events(self):
        html = """
        <html><head><title>About the Nation</title><style>.event { color: red; }</style>
        <script>var today = 'August 13, 2026'; var powwow = true;</script></head>
        <body><p>Community history and contact information.</p></body></html>
        """
        events, _, _ = extract_html_events(
            html, "https://example.org/about", COMMUNITY, SOURCE, date(2026, 8, 13)
        )
        self.assertEqual(events, [])


class EventCategoryTests(unittest.TestCase):
    def test_categories(self):
        self.assertEqual(event_category("Three-day wacipi"), "Culture & Language")
        self.assertEqual(event_category("Youth hockey tournament"), "Youth & Family")
        self.assertEqual(event_category("Annual general meeting"), "Governance & Meetings")


if __name__ == "__main__":
    unittest.main()
