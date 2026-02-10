"""
Happy-path tests for html_parser using sample HTML files in data/.
"""

import unittest
from pathlib import Path

from html_parser import get_hybrid_context

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

class TestHtmlParserHappyPath(unittest.TestCase):
    """Single happy path: get_hybrid_context on each data/*.html returns valid structure."""

    def test_sample_files_return_hybrid_context(self) -> None:
        """Each HTML file in data/ yields truth_sheet, md_content, product_json_ld."""
        html_files = sorted(f for f in DATA_DIR.glob("*.html"))
        self.assertGreater(len(html_files), 0, "No data/*.html files found")

        for path in html_files:
            with self.subTest(path=path.name):
                out = get_hybrid_context(path)
                self.assertIn("truth_sheet", out)
                self.assertIn("md_content", out)
                self.assertIn("product_json_ld", out)
                ts = out["truth_sheet"]
                self.assertIsInstance(ts, dict)
                self.assertIsInstance(out["md_content"], str)
                self.assertIsInstance(out["product_json_ld"], list)
                # Truth sheet has expected keys
                for key in ("name", "price", "description", "key_features", "image_urls", "category", "brand", "variants"):
                    self.assertIn(key, ts, f"truth_sheet missing key {key!r} for {path.name}")

        # At least one file should have a populated product (e.g. ace.html has JSON-LD Product)
        any_populated = False
        for path in html_files:
            out = get_hybrid_context(path)
            ts = out["truth_sheet"]
            if ts.get("name") and (ts.get("image_urls") or ts.get("brand") or ts.get("price")):
                any_populated = True
                break
        self.assertTrue(any_populated, "At least one sample file should yield a populated truth_sheet")

    def test_ace_hardware_truth_sheet_fields(self) -> None:
        """Ace Hardware (ace.html) truth_sheet has correct name, brand, category, price, key_features, image_urls, variants."""
        ace_path = DATA_DIR / "ace.html"
        self.assertTrue(ace_path.exists(), "data/ace.html not found")
        out = get_hybrid_context(ace_path)
        ts = out["truth_sheet"]

        self.assertEqual(ts["name"], "DeWalt 20V MAX 1/2 in. Brushed Cordless Compact Drill Kit (Battery &amp; Charger)")
        self.assertEqual(ts["brand"], "DeWalt")
        self.assertEqual(ts["category"], "Cordless Compact Drill")

        self.assertIsInstance(ts["price"], dict)
        self.assertEqual(ts["price"]["price"], 129.0)
        self.assertEqual(ts["price"]["currency"], "USD")

        self.assertIsInstance(ts["description"], str)
        self.assertIn("DCD771C2", ts["description"])
        self.assertIn("Lithium Ion", ts["description"])

        kf = ts["key_features"]
        self.assertEqual(len(kf), 4)
        self.assertIn("Compact, lightweight design fits into tight areas", kf)
        self.assertIn("Ergonomic handle delivers comfort and control", kf)

        urls = ts["image_urls"]
        self.assertGreaterEqual(len(urls), 1)
        self.assertTrue(any("cdn-tp6.mozu.com" in u for u in urls), "Expected at least one Mozu CDN image URL")

        variants = ts["variants"]
        self.assertGreaterEqual(len(variants), 1)
        self.assertEqual(variants[0]["sku"], "2385458")
        self.assertEqual(variants[0]["price"], 129.0)

    def test_nike_truth_sheet_fields(self) -> None:
        """Nike (nike.html) uses ProductGroup JSON-LD, not Product; image_urls from og:image, other fields empty."""
        nike_path = DATA_DIR / "nike.html"
        self.assertTrue(nike_path.exists(), "data/nike.html not found")
        out = get_hybrid_context(nike_path)
        ts = out["truth_sheet"]
        json_ld = out["product_json_ld"]

        self.assertEqual(len(json_ld), 1)
        self.assertEqual(json_ld[0].get("@type"), "ProductGroup")

        self.assertIsNone(ts.get("name"))
        self.assertIsNone(ts.get("brand"))
        self.assertIsNone(ts.get("price"))
        self.assertIsNone(ts.get("category"))

        urls = ts["image_urls"]
        self.assertIsNotNone(urls)
        self.assertGreaterEqual(len(urls), 1)
        self.assertTrue(any("nike.com" in u for u in urls), "Expected at least one Nike image URL (e.g. og:image)")

    def test_adaysmarch_truth_sheet_fields(self) -> None:
        """A Day's March (adaysmarch.html) truth_sheet has correct name, brand, price, description, image_urls, variants."""
        adaysmarch_path = DATA_DIR / "adaysmarch.html"
        self.assertTrue(adaysmarch_path.exists(), "data/adaysmarch.html not found")
        out = get_hybrid_context(adaysmarch_path)
        ts = out["truth_sheet"]

        self.assertEqual(ts["name"], "Miller Cotton Lyocell Trousers")
        self.assertEqual(ts["brand"], "A Day's March")
        self.assertIsInstance(ts["price"], dict)
        self.assertEqual(ts["price"]["price"], 170.0)
        self.assertEqual(ts["price"]["currency"], "USD")

        self.assertIsInstance(ts["description"], str)
        self.assertIn("TENCEL", ts["description"])
        self.assertIn("Lyocell", ts["description"])

        urls = ts["image_urls"]
        self.assertGreaterEqual(len(urls), 1)
        self.assertTrue(any("centracdn.net" in u for u in urls), "Expected centracdn image URL")

        variants = ts["variants"]
        self.assertGreaterEqual(len(variants), 1)
        self.assertEqual(variants[0]["sku"], "10280550")
        self.assertEqual(variants[0]["price"], 170.0)
