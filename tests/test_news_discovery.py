import json
import unittest
from datetime import date
from pathlib import Path

from tools.news_discovery import (
    PILOT_BAND_IDS,
    article_page_metadata,
    canonical_url,
    candidate_review_reason,
    communities_for_targeted_search,
    community_name_match,
    discover_gdelt_articles,
    discover_meta_posts,
    employment_item,
    ensure_registry,
    extract_html_candidates,
    is_supported_update,
    generic_news_title,
    generic_news_item,
    merge_articles,
    parse_date_text,
    prune_invalid_generated_articles,
)


ROOT = Path(__file__).resolve().parents[1]


class NewsDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.community = {
            "bandId": 361,
            "communityName": "Cowessess First Nation",
            "aliases": ["Cowessess", "CFN"],
        }
        self.source = {
            "type": "Official First Nation Website",
            "name": "Cowessess First Nation",
            "url": "https://cowessessfn.com/",
            "status": "verified",
            "adapter": "html",
            "official": True,
        }

    def test_extracts_dated_community_updates(self):
        html = """
        <html><body>
          <article>
            <time datetime="2026-07-28"></time>
            <a href="/ventures-update/">Cowessess Ventures LTD. Update</a>
            <p>The Nation published an update about its economic development work.</p>
          </article>
          <article>
            <span>Jul 24, 2026</span>
            <a href="/hospital-claim/">Federal Indian Hospital Settlement Claim</a>
          </article>
        </body></html>
        """
        rows = extract_html_candidates(
            html, "https://cowessessfn.com/", self.community, self.source
        )
        self.assertEqual(2, len(rows))
        self.assertEqual("2026-07-28", rows[0]["publishedAt"])
        self.assertEqual("Business & Economic Development", rows[0]["category"])
        self.assertEqual(0.98, rows[0]["communityConfidence"])

    def test_refuses_routine_or_undated_material(self):
        html = """
        <html><body>
          <article><span>Jul 28, 2026</span><a href="/birthday/">Happy birthday!</a></article>
          <article><a href="/housing/">Housing program update</a></article>
        </body></html>
        """
        self.assertEqual(
            [],
            extract_html_candidates(
                html, "https://cowessessfn.com/", self.community, self.source
            ),
        )
        self.assertFalse(is_supported_update("Like and share this contest"))
        self.assertFalse(
            is_supported_update("Employment Opportunity - Housing Coordinator")
        )
        self.assertTrue(
            employment_item(
                "Community Power Representative - Part-Time Contract (Apply July 31)",
                "https://example.com/careers-community-power-representative",
            )
        )
        self.assertFalse(
            employment_item(
                "High School Teacher creates new student opportunities",
                "https://example.com/news/teacher-profile",
            )
        )
        self.assertTrue(generic_news_title("Upcoming Events - Muskoday First Nation"))
        self.assertTrue(generic_news_title("Piapot First Nation Official Website"))
        self.assertTrue(
            generic_news_item(
                {
                    "title": "Onion Lake",
                    "communityName": "Onion Lake Cree Nation",
                }
            )
        )
        self.assertTrue(
            employment_item(
                "Family Shelter Group Program Coordinator *CLOSED*",
                "https://example.com/group-program-coordinator",
            )
        )

    def test_article_metadata_uses_explicit_publication_date(self):
        markup = """
        <html><head>
          <meta property="og:title" content="Community water project update">
          <meta property="article:published_time" content="2026-08-02T09:00:00-06:00">
          <meta property="og:description" content="The Nation published a project update.">
          <link rel="canonical" href="/news/water-project">
        </head><body><h1>Community water project update</h1></body></html>
        """
        metadata = article_page_metadata(markup, "https://example.com/news/water-project")
        self.assertEqual("2026-08-02", metadata["published"])
        self.assertEqual("article:published_time", metadata["dateSource"])
        self.assertEqual(
            "https://example.com/news/water-project", metadata["canonical"]
        )

    def test_article_metadata_does_not_treat_any_visible_date_as_published(self):
        markup = """
        <html><head><title>Housing services</title></head>
        <body><h1>Housing services</h1><p>Applications close September 4, 2026.</p></body>
        </html>
        """
        metadata = article_page_metadata(markup, "https://example.com/housing")
        self.assertIsNone(metadata["published"])

    def test_deduplicates_cross_posted_story_and_prefers_official_source(self):
        news_item = {
            "bandId": 361,
            "communityName": "Cowessess First Nation",
            "title": "Cowessess announces new housing project",
            "publishedAt": "2026-05-01",
            "sourceType": "Traditional News",
            "sourceName": "Local News",
            "url": "https://example.com/cowessess-housing",
        }
        official = {
            **news_item,
            "sourceType": "Official First Nation Website",
            "sourceName": "Cowessess First Nation",
            "url": "https://cowessessfn.com/housing-project/",
        }
        merged, accepted = merge_articles([news_item], [official])
        self.assertEqual(1, len(merged))
        self.assertEqual("Official First Nation Website", merged[0]["sourceType"])
        self.assertEqual(1, len(merged[0]["alternateSources"]))
        self.assertEqual([], accepted)

    def test_registry_covers_every_tracked_band(self):
        data = json.loads((ROOT / "data.json").read_text(encoding="utf-8"))
        news = json.loads((ROOT / "news-data.json").read_text(encoding="utf-8"))
        registry = ensure_registry(data, news, {"communities": []})
        self.assertEqual(len(data["bands"]), len(registry["communities"]))
        self.assertEqual(
            {str(band["id"]) for band in data["bands"]},
            {str(item["bandId"]) for item in registry["communities"]},
        )
        self.assertTrue(
            all(item["discoveryQueries"] for item in registry["communities"])
        )

    def test_date_and_url_normalization(self):
        self.assertEqual(("2026-06-01", "month"), parse_date_text("June 2026 Newsletter"))
        self.assertEqual(
            ("2026-07-28", "day"), parse_date_text("20260728T134500Z")
        )
        self.assertEqual(
            "https://example.com/news?a=1",
            canonical_url("https://EXAMPLE.com/news/?utm_source=x&a=1#top"),
        )

    def test_pilot_has_five_varied_communities(self):
        self.assertEqual(5, len(PILOT_BAND_IDS))

    def test_targeted_search_requires_exact_community_name(self):
        self.assertTrue(
            community_name_match(
                self.community,
                "Cowessess First Nation announces a housing development",
            )
        )
        self.assertFalse(
            community_name_match(
                self.community,
                "A Saskatchewan community announces a housing development",
            )
        )

    def test_gdelt_discovery_keeps_original_strongly_matched_url(self):
        class FakeFetcher:
            def get(self, url, headers=None):
                payload = {
                    "articles": [
                        {
                            "title": "Cowessess First Nation announces housing development",
                            "url": "https://example.com/cowessess-housing",
                            "domain": "example.com",
                            "seendate": "20260728T134500Z",
                        },
                        {
                            "title": "Housing development announced in Saskatchewan",
                            "url": "https://example.com/weak-match",
                            "domain": "example.com",
                            "seendate": "20260728T134500Z",
                        },
                    ]
                }
                return json.dumps(payload).encode(), url, "application/json"

        rows = discover_gdelt_articles(FakeFetcher(), self.community)
        self.assertEqual(1, len(rows))
        self.assertEqual(
            "https://example.com/cowessess-housing", rows[0]["url"]
        )
        self.assertEqual(0.86, rows[0]["communityConfidence"])

    def test_targeted_search_rotates_undercovered_communities(self):
        communities = [
            {"bandId": 1, "communityName": "One"},
            {"bandId": 2, "communityName": "Two"},
            {"bandId": 3, "communityName": "Three"},
        ]
        selected, cursor = communities_for_targeted_search(
            communities,
            [{"bandId": 1, "publishedAt": "2999-01-01"}],
            limit=1,
            pilot=False,
            cursor=1,
        )
        self.assertEqual([3], [item["bandId"] for item in selected])
        self.assertEqual(0, cursor)

    def test_meta_token_is_sent_as_header_not_committed_in_url(self):
        class FakeFetcher:
            request = None

            def get(self, url, headers=None, respect_robots=True):
                self.request = (url, headers, respect_robots)
                payload = {
                    "data": [
                        {
                            "message": "Housing program update is now available.",
                            "created_time": "2026-07-28T13:45:00Z",
                            "permalink_url": "https://www.facebook.com/example/posts/1",
                        }
                    ]
                }
                return json.dumps(payload).encode(), url, "application/json"

        fetcher = FakeFetcher()
        source = {
            "type": "Facebook",
            "name": "Cowessess First Nation",
            "pageHandle": "cowessessfn",
            "official": True,
        }
        rows = discover_meta_posts(fetcher, self.community, source, "secret-token")
        url, headers, respect_robots = fetcher.request
        self.assertNotIn("secret-token", url)
        self.assertEqual("Bearer secret-token", headers["Authorization"])
        self.assertFalse(respect_robots)
        self.assertEqual(1, len(rows))

    def test_future_event_date_is_not_kept_as_publication_date(self):
        retained, removed = prune_invalid_generated_articles(
            [
                {
                    "title": "Future community meeting",
                    "publishedAt": "2026-09-09",
                    "discoveredAt": "2026-07-29T00:00:00Z",
                },
                {
                    "title": "Manually verified scheduled item",
                    "publishedAt": "2026-09-09",
                },
                {
                    "title": "Current update",
                    "publishedAt": "2026-07-29",
                    "discoveredAt": "2026-07-29T00:00:00Z",
                },
            ],
            date(2026, 7, 29),
        )
        self.assertEqual(
            ["Manually verified scheduled item", "Current update"],
            [item["title"] for item in retained],
        )
        self.assertEqual(["Future community meeting"], [item["title"] for item in removed])

    def test_prunes_legacy_evergreen_and_jobs_rows_from_news(self):
        retained, removed = prune_invalid_generated_articles(
            [
                {
                    "title": "Employment Opportunity - Housing Coordinator",
                    "publishedAt": "2026-07-20",
                    "discoveredAt": "2026-07-20T00:00:00Z",
                    "sourceType": "Official First Nation Website",
                },
                {
                    "title": "Housing services",
                    "publishedAt": "2026-07-20",
                    "discoveredAt": "2026-07-20T00:00:00Z",
                    "sourceType": "Official First Nation Website",
                },
                {
                    "title": "Verified infrastructure announcement",
                    "publishedAt": "2026-07-20",
                    "discoveredAt": "2026-07-20T00:00:00Z",
                    "sourceType": "Official First Nation Website",
                    "dateSource": "article:published_time",
                },
            ],
            date(2026, 8, 1),
        )
        self.assertEqual(["Verified infrastructure announcement"], [item["title"] for item in retained])
        self.assertEqual(2, len(removed))

    def test_non_https_candidate_is_sent_to_review(self):
        reason = candidate_review_reason(
            {
                "url": "http://example.com/community-update",
                "publishedAt": "2026-07-28",
                "communityConfidence": 0.98,
            },
            date(2026, 7, 29),
            0.82,
        )
        self.assertEqual("Original source URL is not HTTPS", reason)


if __name__ == "__main__":
    unittest.main()
