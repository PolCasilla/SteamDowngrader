from datetime import datetime, timezone
import pathlib
import tempfile
import unittest

from src.steamdb import (
    parse_patchnotes_rss,
    parse_steamdb_manifest_date,
    load_cache,
    save_to_cache,
    resolve_build_depots,
)


class TestSteamDB(unittest.TestCase):
    def test_parse_patchnotes_rss(self):
        sample = (
            b'<rss version="2.0"><channel>'
            b'<item><guid isPermaLink="false">build#16965472</guid>'
            b"<description>Assassin's Creed Origins - Title Update 1.62 (SteamDB Build 16965472)</description>"
            b"<pubDate>Tue, 14 Jan 2025 14:00:28 +0000</pubDate></item>"
            b'<item><guid isPermaLink="false">build#13275841</guid>'
            b"<description>SteamDB Build 13275841</description>"
            b"<pubDate>Tue, 30 Jan 2024 14:20:24 +0000</pubDate></item>"
            b"</channel></rss>"
        )
        builds = parse_patchnotes_rss(sample)
        self.assertEqual(len(builds), 2)
        self.assertEqual(builds[0]["build_id"], "16965472")
        self.assertEqual(builds[0]["title"], "Assassin's Creed Origins - Title Update 1.62")
        self.assertEqual(builds[1]["build_id"], "13275841")
        self.assertEqual(builds[1]["title"], "No title")

    def test_parse_steamdb_manifest_date(self):
        dt = parse_steamdb_manifest_date("14 January 2025 14:00:28 UTC")
        self.assertEqual(dt.year, 2025)
        self.assertEqual(dt.month, 1)
        self.assertEqual(dt.day, 14)
        self.assertEqual(dt.hour, 14)
        self.assertEqual(dt.minute, 0)
        self.assertEqual(dt.second, 28)
        self.assertEqual(dt.tzinfo, timezone.utc)

    def test_cache_load_and_save(self):
        with tempfile.TemporaryDirectory() as td:
            cache_file = pathlib.Path(td) / "test_cache.json"
            # Non-existent returns empty dict
            self.assertEqual(load_cache(cache_file), {})

            # Corrupted returns empty dict
            cache_file.write_text("not json", encoding="utf-8")
            self.assertEqual(load_cache(cache_file), {})

            # Save and load valid entries
            rows = [{"manifest": "111222333444555", "date": "14 January 2025 14:00:28 UTC"}]
            save_to_cache(cache_file, "582161", rows)

            loaded = load_cache(cache_file)
            self.assertIn("582161", loaded)
            self.assertEqual(len(loaded["582161"]), 1)
            self.assertEqual(loaded["582161"][0]["manifest"], "111222333444555")
            self.assertEqual(loaded["582161"][0]["dt"].year, 2025)

    def test_resolve_build_depots(self):
        depots = [{"id": "582161", "manifest": "current_man"}]
        manifests = {
            "582161": [
                {
                    "manifest": "target_build_match",
                    "dt": datetime(2025, 1, 14, 14, 0, tzinfo=timezone.utc),
                    "build_id": "16965472",
                },
                {
                    "manifest": "target_date_match",
                    "dt": datetime(2024, 1, 30, 14, 0, tzinfo=timezone.utc),
                    "build_id": None,
                },
            ]
        }

        # Case 1: matches by build_id
        b1 = {
            "build_id": "16965472",
            "dt": datetime(2025, 1, 14, 14, 5, tzinfo=timezone.utc),
        }
        plan1 = resolve_build_depots(b1, depots, manifests)
        self.assertEqual(plan1[0]["target"], "target_build_match")

        # Case 2: matches by cutoff date when build_id not linked
        b2 = {
            "build_id": "13275841",
            "dt": datetime(2024, 1, 30, 14, 5, tzinfo=timezone.utc),
        }
        plan2 = resolve_build_depots(b2, depots, manifests)
        self.assertEqual(plan2[0]["target"], "target_date_match")

        # Case 3: single manifest fallback
        plan3 = resolve_build_depots(
            {"build_id": "999", "dt": datetime(2020, 1, 1, tzinfo=timezone.utc)},
            depots,
            {"582161": [{"manifest": "only_one", "dt": datetime(2025, 1, 1, tzinfo=timezone.utc), "build_id": None}]},
        )
        self.assertEqual(plan3[0]["target"], "only_one")


if __name__ == "__main__":
    unittest.main()
