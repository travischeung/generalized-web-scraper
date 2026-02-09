"""
Tests for html_parser.extract_metadata, html_parser.extract_distilled_content,
and html_parser.get_hybrid_context.

Covers JSON-LD extraction, meta tags (og:*, name), data-* product attributes,
Trafilatura-based main-content extraction to Markdown, and truth_sheet
extraction from Product JSON-LD.
"""

import json
import tempfile
import unittest
from pathlib import Path

from html_parser import extract_metadata, extract_distilled_content, get_hybrid_context


def _write_html(path: Path, html: str) -> None:
    path.write_text(html, encoding="utf-8", errors="replace")


class TestExtractMetadataStructure(unittest.TestCase):
    """Output structure and edge cases."""

    def test_return_structure(self) -> None:
        """Result has json_ld, meta, and product_attributes keys."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", delete=False, encoding="utf-8"
        ) as f:
            f.write("<!DOCTYPE html><html><body></body></html>")
            path = Path(f.name)
        try:
            out = extract_metadata(path)
            self.assertIn("json_ld", out)
            self.assertIn("meta", out)
            self.assertIn("product_attributes", out)
            self.assertIsInstance(out["json_ld"], list)
            self.assertIsInstance(out["meta"], dict)
            self.assertIsInstance(out["product_attributes"], dict)
        finally:
            path.unlink(missing_ok=True)

    def test_empty_html_returns_empty_containers(self) -> None:
        """Minimal HTML yields empty list/dicts."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", delete=False, encoding="utf-8"
        ) as f:
            f.write("<!DOCTYPE html><html><head></head><body></body></html>")
            path = Path(f.name)
        try:
            out = extract_metadata(path)
            self.assertEqual(out["json_ld"], [])
            self.assertEqual(out["meta"], {})
            self.assertEqual(out["product_attributes"], {})
        finally:
            path.unlink(missing_ok=True)

    def test_file_not_found_raises(self) -> None:
        """Missing file raises FileNotFoundError."""
        path = Path("/nonexistent/path/to/file.html")
        with self.assertRaises(FileNotFoundError):
            extract_metadata(path)


class TestJsonLdExtraction(unittest.TestCase):
    """JSON-LD script extraction."""

    def test_json_ld_single_object(self) -> None:
        """Single JSON object in script is appended as one item."""
        ld = {"@context": "https://schema.org", "@type": "Product", "name": "Test"}
        html = f"""<!DOCTYPE html><html><head>
        <script type="application/ld+json">{json.dumps(ld)}</script>
        </head><body></body></html>"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", delete=False, encoding="utf-8"
        ) as f:
            f.write(html)
            path = Path(f.name)
        try:
            out = extract_metadata(path)
            self.assertEqual(len(out["json_ld"]), 1)
            self.assertEqual(out["json_ld"][0]["@type"], "Product")
            self.assertEqual(out["json_ld"][0]["name"], "Test")
        finally:
            path.unlink(missing_ok=True)

    def test_json_ld_array_extended(self) -> None:
        """Array in script is extended into json_ld (no nested list)."""
        ld_list = [
            {"@type": "Product", "name": "A"},
            {"@type": "Organization", "name": "B"},
        ]
        html = f"""<!DOCTYPE html><html><head>
        <script type="application/ld+json">{json.dumps(ld_list)}</script>
        </head><body></body></html>"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", delete=False, encoding="utf-8"
        ) as f:
            f.write(html)
            path = Path(f.name)
        try:
            out = extract_metadata(path)
            self.assertEqual(len(out["json_ld"]), 2)
            self.assertEqual(out["json_ld"][0]["name"], "A")
            self.assertEqual(out["json_ld"][1]["name"], "B")
        finally:
            path.unlink(missing_ok=True)

    def test_json_ld_invalid_skipped(self) -> None:
        """Invalid JSON in ld+json script is skipped without failing."""
        html = """<!DOCTYPE html><html><head>
        <script type="application/ld+json">{ invalid json }</script>
        <script type="application/ld+json">{"valid": true}</script>
        </head><body></body></html>"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", delete=False, encoding="utf-8"
        ) as f:
            f.write(html)
            path = Path(f.name)
        try:
            out = extract_metadata(path)
            self.assertEqual(len(out["json_ld"]), 1)
            self.assertEqual(out["json_ld"][0]["valid"], True)
        finally:
            path.unlink(missing_ok=True)

    def test_json_ld_empty_script_skipped(self) -> None:
        """Empty or whitespace-only script content is skipped."""
        html = """<!DOCTYPE html><html><head>
        <script type="application/ld+json"></script>
        <script type="application/ld+json">   </script>
        </head><body></body></html>"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", delete=False, encoding="utf-8"
        ) as f:
            f.write(html)
            path = Path(f.name)
        try:
            out = extract_metadata(path)
            self.assertEqual(out["json_ld"], [])
        finally:
            path.unlink(missing_ok=True)

    def test_other_script_types_ignored(self) -> None:
        """Only application/ld+json scripts are parsed for JSON-LD."""
        html = """<!DOCTYPE html><html><head>
        <script type="text/javascript">{"@type": "Product"}</script>
        </head><body></body></html>"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", delete=False, encoding="utf-8"
        ) as f:
            f.write(html)
            path = Path(f.name)
        try:
            out = extract_metadata(path)
            self.assertEqual(out["json_ld"], [])
        finally:
            path.unlink(missing_ok=True)


class TestMetaExtraction(unittest.TestCase):
    """Meta tags (og:*, name, etc.)."""

    def test_meta_og_and_name_extracted(self) -> None:
        """og: and name meta tags are extracted; keys lowercased."""
        html = """<!DOCTYPE html><html><head>
        <meta property="og:title" content="Product Title"/>
        <meta property="og:image" content="https://example.com/img.png"/>
        <meta name="description" content="A product description"/>
        </head><body></body></html>"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", delete=False, encoding="utf-8"
        ) as f:
            f.write(html)
            path = Path(f.name)
        try:
            out = extract_metadata(path)
            self.assertEqual(out["meta"]["og:title"], "Product Title")
            self.assertEqual(out["meta"]["og:image"], "https://example.com/img.png")
            self.assertEqual(out["meta"]["description"], "A product description")
        finally:
            path.unlink(missing_ok=True)

    def test_meta_first_wins(self) -> None:
        """First occurrence of a key is kept; duplicates not overwritten."""
        html = """<!DOCTYPE html><html><head>
        <meta property="og:title" content="First"/>
        <meta property="og:title" content="Second"/>
        </head><body></body></html>"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", delete=False, encoding="utf-8"
        ) as f:
            f.write(html)
            path = Path(f.name)
        try:
            out = extract_metadata(path)
            self.assertEqual(out["meta"]["og:title"], "First")
        finally:
            path.unlink(missing_ok=True)

    def test_meta_without_content_skipped(self) -> None:
        """Meta tags without content are not added."""
        html = """<!DOCTYPE html><html><head>
        <meta property="og:title"/>
        <meta name="description" content="Has content"/>
        </head><body></body></html>"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", delete=False, encoding="utf-8"
        ) as f:
            f.write(html)
            path = Path(f.name)
        try:
            out = extract_metadata(path)
            self.assertNotIn("og:title", out["meta"])
            self.assertEqual(out["meta"]["description"], "Has content")
        finally:
            path.unlink(missing_ok=True)


class TestProductAttributes(unittest.TestCase):
    """data-* attribute harvesting for product-related keys."""

    def test_product_attributes_harvested(self) -> None:
        """data-* containing product, price, sku, id, image, brand are captured."""
        html = """<!DOCTYPE html><html><body>
        <div data-product-id="123" data-price="99.99" data-sku="SKU-X"
             data-image="https://example.com/p.jpg" data-brand="Nike"></div>
        </body></html>"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", delete=False, encoding="utf-8"
        ) as f:
            f.write(html)
            path = Path(f.name)
        try:
            out = extract_metadata(path)
            self.assertEqual(out["product_attributes"]["data-product-id"], "123")
            self.assertEqual(out["product_attributes"]["data-price"], "99.99")
            self.assertEqual(out["product_attributes"]["data-sku"], "SKU-X")
            self.assertEqual(out["product_attributes"]["data-image"], "https://example.com/p.jpg")
            self.assertEqual(out["product_attributes"]["data-brand"], "Nike")
        finally:
            path.unlink(missing_ok=True)

    def test_product_attributes_irrelevant_ignored(self) -> None:
        """data-* that don't contain product/price/sku/id/image/brand are ignored."""
        html = """<!DOCTYPE html><html><body>
        <div data-foo="bar" data-analytics-id="a1"></div>
        </body></html>"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", delete=False, encoding="utf-8"
        ) as f:
            f.write(html)
            path = Path(f.name)
        try:
            out = extract_metadata(path)
            # analytics-id contains "id" so it is included
            self.assertIn("data-analytics-id", out["product_attributes"])
            self.assertNotIn("data-foo", out["product_attributes"])
        finally:
            path.unlink(missing_ok=True)

    def test_product_attributes_value_coerced_to_str(self) -> None:
        """Attribute values are stored as strings."""
        html = """<!DOCTYPE html><html><body>
        <div data-product-id="456"></div>
        </body></html>"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", delete=False, encoding="utf-8"
        ) as f:
            f.write(html)
            path = Path(f.name)
        try:
            out = extract_metadata(path)
            self.assertEqual(out["product_attributes"]["data-product-id"], "456")
            self.assertIsInstance(out["product_attributes"]["data-product-id"], str)
        finally:
            path.unlink(missing_ok=True)


class TestExtractDistilledContent(unittest.TestCase):
    """Trafilatura-based main-content extraction to Markdown."""

    def test_return_type_is_str(self) -> None:
        """Result is always a string."""
        html = """<!DOCTYPE html><html><body><article><p>Hello world.</p></article></body></html>"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", delete=False, encoding="utf-8"
        ) as f:
            f.write(html)
            path = Path(f.name)
        try:
            out = extract_distilled_content(path)
            self.assertIsInstance(out, str)
        finally:
            path.unlink(missing_ok=True)

    def test_empty_html_returns_empty_string(self) -> None:
        """Empty HTML body yields empty string."""
        html = """<!DOCTYPE html><html><head></head><body></body></html>"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", delete=False, encoding="utf-8"
        ) as f:
            f.write(html)
            path = Path(f.name)
        try:
            out = extract_distilled_content(path)
            self.assertEqual(out, "")
        finally:
            path.unlink(missing_ok=True)

    def test_whitespace_only_returns_empty_string(self) -> None:
        """HTML that is only whitespace yields empty string."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", delete=False, encoding="utf-8"
        ) as f:
            f.write("   \n\t  ")
            path = Path(f.name)
        try:
            out = extract_distilled_content(path)
            self.assertEqual(out, "")
        finally:
            path.unlink(missing_ok=True)

    def test_file_not_found_raises(self) -> None:
        """Missing file raises FileNotFoundError."""
        path = Path("/nonexistent/path/to/file.html")
        with self.assertRaises(FileNotFoundError):
            extract_distilled_content(path)

    def test_html_with_main_content_returns_markdown(self) -> None:
        """Article-like HTML produces non-empty Markdown with main text."""
        html = """<!DOCTYPE html><html><head><title>Test</title></head><body>
        <nav>Menu</nav>
        <main><article><h1>Product Name</h1><p>This is the main product description.</p></article></main>
        <footer>Footer</footer>
        </body></html>"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", delete=False, encoding="utf-8"
        ) as f:
            f.write(html)
            path = Path(f.name)
        try:
            out = extract_distilled_content(path)
            self.assertIsInstance(out, str)
            self.assertGreater(len(out.strip()), 0)
            # Trafilatura often keeps main content; exact format may vary
            self.assertTrue(
                "Product Name" in out or "product description" in out.lower(),
                f"Expected main content in output: {out!r}",
            )
        finally:
            path.unlink(missing_ok=True)

    def test_minimal_html_returns_string(self) -> None:
        """HTML with little or no main content still returns a string (possibly empty)."""
        html = """<!DOCTYPE html><html><head><script>var x=1;</script></head>
        <body><nav><a href="/">Home</a></nav></body></html>"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", delete=False, encoding="utf-8"
        ) as f:
            f.write(html)
            path = Path(f.name)
        try:
            out = extract_distilled_content(path)
            self.assertIsInstance(out, str)
            # Trafilatura may return "" or a short extraction; both are valid
        finally:
            path.unlink(missing_ok=True)

    def test_utf8_content_read_correctly(self) -> None:
        """UTF-8 characters in HTML are preserved in extracted Markdown."""
        html = """<!DOCTYPE html><html><body><article><p>Café résumé — 日本語</p></article></body></html>"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", delete=False, encoding="utf-8"
        ) as f:
            f.write(html)
            path = Path(f.name)
        try:
            out = extract_distilled_content(path)
            self.assertIsInstance(out, str)
            # At least one of the UTF-8 snippets should appear
            self.assertTrue(
                "Café" in out or "résumé" in out or "日本語" in out,
                f"Expected UTF-8 content in output: {out!r}",
            )
        finally:
            path.unlink(missing_ok=True)


class TestGetHybridContext(unittest.TestCase):
    """Tests for get_hybrid_context: return structure, truth_sheet extraction from Product JSON-LD."""

    def test_return_structure(self) -> None:
        """Result has truth_sheet and md_content keys."""
        html = """<!DOCTYPE html><html><body><p>Content</p></body></html>"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", delete=False, encoding="utf-8"
        ) as f:
            f.write(html)
            path = Path(f.name)
        try:
            out = get_hybrid_context(path)
            self.assertIn("truth_sheet", out)
            self.assertIn("md_content", out)
            self.assertIsInstance(out["truth_sheet"], dict)
            self.assertIsInstance(out["md_content"], str)
        finally:
            path.unlink(missing_ok=True)

    def test_file_not_found_raises(self) -> None:
        """Missing file raises FileNotFoundError."""
        path = Path("/nonexistent/path/to/file.html")
        with self.assertRaises(FileNotFoundError):
            get_hybrid_context(path)

    def test_no_product_json_ld_yields_pruned_truth_sheet(self) -> None:
        """HTML with no Product JSON-LD yields empty or minimal truth_sheet (pruned)."""
        html = """<!DOCTYPE html><html><head>
        <script type="application/ld+json">{"@type": "Organization", "name": "Acme"}</script>
        </head><body><p>Content</p></body></html>"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", delete=False, encoding="utf-8"
        ) as f:
            f.write(html)
            path = Path(f.name)
        try:
            out = get_hybrid_context(path)
            ts = out["truth_sheet"]
            # Pruning removes None, [], {} - so no Product means empty or minimal
            self.assertIsInstance(ts, dict)
            for v in ts.values():
                self.assertNotIn(v, [None, [], {}], f"Pruned truth_sheet should not contain {v}")
        finally:
            path.unlink(missing_ok=True)

    def test_product_json_ld_extracts_name_description_category(self) -> None:
        """Product JSON-LD extracts name, description, category."""
        ld = {
            "@type": "Product",
            "name": "Test Product",
            "description": "A test description.",
            "category": "Electronics",
        }
        html = f"""<!DOCTYPE html><html><head>
        <script type="application/ld+json">{json.dumps(ld)}</script>
        </head><body><p>Content</p></body></html>"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", delete=False, encoding="utf-8"
        ) as f:
            f.write(html)
            path = Path(f.name)
        try:
            out = get_hybrid_context(path)
            ts = out["truth_sheet"]
            self.assertEqual(ts["name"], "Test Product")
            self.assertEqual(ts["description"], "A test description.")
            self.assertEqual(ts["category"], "Electronics")
        finally:
            path.unlink(missing_ok=True)

    def test_product_json_ld_brand_as_dict(self) -> None:
        """Brand as schema.org dict {name: X} is extracted."""
        ld = {"@type": "Product", "name": "X", "brand": {"@type": "Brand", "name": "Nike"}}
        html = f"""<!DOCTYPE html><html><head>
        <script type="application/ld+json">{json.dumps(ld)}</script>
        </head><body></body></html>"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", delete=False, encoding="utf-8"
        ) as f:
            f.write(html)
            path = Path(f.name)
        try:
            out = get_hybrid_context(path)
            self.assertEqual(out["truth_sheet"]["brand"], "Nike")
        finally:
            path.unlink(missing_ok=True)

    def test_product_json_ld_brand_as_string(self) -> None:
        """Brand as plain string is extracted."""
        ld = {"@type": "Product", "name": "X", "brand": "Adidas"}
        html = f"""<!DOCTYPE html><html><head>
        <script type="application/ld+json">{json.dumps(ld)}</script>
        </head><body></body></html>"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", delete=False, encoding="utf-8"
        ) as f:
            f.write(html)
            path = Path(f.name)
        try:
            out = get_hybrid_context(path)
            self.assertEqual(out["truth_sheet"]["brand"], "Adidas")
        finally:
            path.unlink(missing_ok=True)

    def test_product_json_ld_price_from_offers(self) -> None:
        """Price extracted from offers.price and offers.priceCurrency."""
        ld = {
            "@type": "Product",
            "name": "X",
            "offers": {"@type": "Offer", "price": "99.99", "priceCurrency": "USD"},
        }
        html = f"""<!DOCTYPE html><html><head>
        <script type="application/ld+json">{json.dumps(ld)}</script>
        </head><body></body></html>"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", delete=False, encoding="utf-8"
        ) as f:
            f.write(html)
            path = Path(f.name)
        try:
            out = get_hybrid_context(path)
            price = out["truth_sheet"]["price"]
            self.assertIsInstance(price, dict)
            self.assertEqual(price["price"], 99.99)
            self.assertEqual(price["currency"], "USD")
        finally:
            path.unlink(missing_ok=True)

    def test_product_json_ld_key_features_from_positive_notes(self) -> None:
        """key_features extracted from positiveNotes list."""
        ld = {
            "@type": "Product",
            "name": "X",
            "positiveNotes": ["Feature one", "Feature two"],
        }
        html = f"""<!DOCTYPE html><html><head>
        <script type="application/ld+json">{json.dumps(ld)}</script>
        </head><body></body></html>"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", delete=False, encoding="utf-8"
        ) as f:
            f.write(html)
            path = Path(f.name)
        try:
            out = get_hybrid_context(path)
            self.assertEqual(out["truth_sheet"]["key_features"], ["Feature one", "Feature two"])
        finally:
            path.unlink(missing_ok=True)

    def test_product_json_ld_image_urls(self) -> None:
        """image_urls extracted from image or images."""
        ld = {
            "@type": "Product",
            "name": "X",
            "images": ["https://example.com/a.jpg", "https://example.com/b.jpg"],
        }
        html = f"""<!DOCTYPE html><html><head>
        <script type="application/ld+json">{json.dumps(ld)}</script>
        </head><body></body></html>"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", delete=False, encoding="utf-8"
        ) as f:
            f.write(html)
            path = Path(f.name)
        try:
            out = get_hybrid_context(path)
            self.assertEqual(
                out["truth_sheet"]["image_urls"],
                ["https://example.com/a.jpg", "https://example.com/b.jpg"],
            )
        finally:
            path.unlink(missing_ok=True)

    def test_product_json_ld_colors(self) -> None:
        """colors extracted from color (string or list)."""
        ld = {"@type": "Product", "name": "X", "color": "Red"}
        html = f"""<!DOCTYPE html><html><head>
        <script type="application/ld+json">{json.dumps(ld)}</script>
        </head><body></body></html>"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", delete=False, encoding="utf-8"
        ) as f:
            f.write(html)
            path = Path(f.name)
        try:
            out = get_hybrid_context(path)
            self.assertEqual(out["truth_sheet"]["colors"], ["Red"])
        finally:
            path.unlink(missing_ok=True)

    def test_product_json_ld_variants_single_sku_fallback(self) -> None:
        """When no hasVariant, product sku yields single variant."""
        ld = {
            "@type": "Product",
            "name": "X",
            "sku": "SKU-123",
            "offers": {"@type": "Offer", "price": "49.00", "priceCurrency": "USD"},
            "image": "https://example.com/img.jpg",
        }
        html = f"""<!DOCTYPE html><html><head>
        <script type="application/ld+json">{json.dumps(ld)}</script>
        </head><body></body></html>"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", delete=False, encoding="utf-8"
        ) as f:
            f.write(html)
            path = Path(f.name)
        try:
            out = get_hybrid_context(path)
            variants = out["truth_sheet"]["variants"]
            self.assertEqual(len(variants), 1)
            self.assertEqual(variants[0]["sku"], "SKU-123")
            self.assertEqual(variants[0]["price"], 49.0)
            self.assertEqual(variants[0]["image_url"], "https://example.com/img.jpg")
        finally:
            path.unlink(missing_ok=True)

    def test_product_json_ld_variants_has_variant(self) -> None:
        """hasVariant yields multiple variants with sku, color, size, price, image_url."""
        ld = {
            "@type": "Product",
            "name": "X",
            "hasVariant": [
                {"@type": "Product", "sku": "V1", "color": "Black", "size": "M", "price": "29.99"},
                {"@type": "Product", "sku": "V2", "color": "White", "image": "https://example.com/v2.jpg"},
            ],
        }
        html = f"""<!DOCTYPE html><html><head>
        <script type="application/ld+json">{json.dumps(ld)}</script>
        </head><body></body></html>"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", delete=False, encoding="utf-8"
        ) as f:
            f.write(html)
            path = Path(f.name)
        try:
            out = get_hybrid_context(path)
            variants = out["truth_sheet"]["variants"]
            self.assertEqual(len(variants), 2)
            self.assertEqual(variants[0]["sku"], "V1")
            self.assertEqual(variants[0]["color"], "Black")
            self.assertEqual(variants[0]["size"], "M")
            self.assertEqual(variants[0]["price"], 29.99)
            self.assertEqual(variants[1]["sku"], "V2")
            self.assertEqual(variants[1]["color"], "White")
            self.assertEqual(variants[1]["image_url"], "https://example.com/v2.jpg")
        finally:
            path.unlink(missing_ok=True)

    def test_md_content_returned(self) -> None:
        """md_content is returned as markdown string from Trafilatura."""
        html = """<!DOCTYPE html><html><body>
        <main><article><h1>Product</h1><p>Main content here.</p></article></main>
        </body></html>"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", delete=False, encoding="utf-8"
        ) as f:
            f.write(html)
            path = Path(f.name)
        try:
            out = get_hybrid_context(path)
            md = out["md_content"]
            self.assertIsInstance(md, str)
            self.assertTrue(
                "Product" in md or "Main content" in md or "content" in md.lower(),
                f"Expected main content in md_content: {md!r}",
            )
        finally:
            path.unlink(missing_ok=True)

    def test_product_in_list_type(self) -> None:
        """Product with @type as list ['Product'] is recognized."""
        ld = {"@type": ["Product", "Thing"], "name": "ListTypeProduct"}
        html = f"""<!DOCTYPE html><html><head>
        <script type="application/ld+json">{json.dumps(ld)}</script>
        </head><body></body></html>"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", delete=False, encoding="utf-8"
        ) as f:
            f.write(html)
            path = Path(f.name)
        try:
            out = get_hybrid_context(path)
            self.assertEqual(out["truth_sheet"]["name"], "ListTypeProduct")
        finally:
            path.unlink(missing_ok=True)

    def test_image_object_with_content_url(self) -> None:
        """ImageObject with contentUrl (no url) is extracted."""
        ld = {
            "@type": "Product",
            "name": "X",
            "image": [{"@type": "ImageObject", "contentUrl": "https://example.com/img.jpg"}],
        }
        html = f"""<!DOCTYPE html><html><head>
        <script type="application/ld+json">{json.dumps(ld)}</script>
        </head><body></body></html>"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", delete=False, encoding="utf-8"
        ) as f:
            f.write(html)
            path = Path(f.name)
        try:
            out = get_hybrid_context(path)
            self.assertIn("image_urls", out["truth_sheet"])
            self.assertIn("https://example.com/img.jpg", out["truth_sheet"]["image_urls"])
        finally:
            path.unlink(missing_ok=True)

    def test_video_as_array(self) -> None:
        """video as array of VideoObjects uses first element."""
        ld = {
            "@type": "Product",
            "name": "X",
            "video": [{"@type": "VideoObject", "embedUrl": "https://example.com/video"}],
        }
        html = f"""<!DOCTYPE html><html><head>
        <script type="application/ld+json">{json.dumps(ld)}</script>
        </head><body></body></html>"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", delete=False, encoding="utf-8"
        ) as f:
            f.write(html)
            path = Path(f.name)
        try:
            out = get_hybrid_context(path)
            self.assertEqual(out["truth_sheet"]["video_url"], "https://example.com/video")
        finally:
            path.unlink(missing_ok=True)

    def test_additional_property_as_single_object(self) -> None:
        """additionalProperty as single dict (not list) is handled."""
        ld = {
            "@type": "Product",
            "name": "X",
            "additionalProperty": {"@type": "PropertyValue", "name": "Prop", "value": "Val"},
        }
        html = f"""<!DOCTYPE html><html><head>
        <script type="application/ld+json">{json.dumps(ld)}</script>
        </head><body></body></html>"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", delete=False, encoding="utf-8"
        ) as f:
            f.write(html)
            path = Path(f.name)
        try:
            out = get_hybrid_context(path)
            self.assertIn("key_features", out["truth_sheet"])
            self.assertIn("Val", out["truth_sheet"]["key_features"])
        finally:
            path.unlink(missing_ok=True)

    def test_positive_notes_as_dict_items(self) -> None:
        """positiveNotes with dict items {name: X} extracts name."""
        ld = {
            "@type": "Product",
            "name": "X",
            "positiveNotes": [
                {"@type": "ListItem", "name": "Feature A"},
                "Feature B",
            ],
        }
        html = f"""<!DOCTYPE html><html><head>
        <script type="application/ld+json">{json.dumps(ld)}</script>
        </head><body></body></html>"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", delete=False, encoding="utf-8"
        ) as f:
            f.write(html)
            path = Path(f.name)
        try:
            out = get_hybrid_context(path)
            kf = out["truth_sheet"]["key_features"]
            self.assertIn("Feature A", kf)
            self.assertIn("Feature B", kf)
        finally:
            path.unlink(missing_ok=True)


class TestExtractMetadataIntegration(unittest.TestCase):
    """Run against real data files if present."""

    def test_data_dir_article_structure(self) -> None:
        """Parse data/article.html and assert expected keys and types."""
        data_dir = Path(__file__).resolve().parent.parent / "data"
        article_path = data_dir / "article.html"
        if not article_path.exists():
            self.skipTest("data/article.html not found")
        out = extract_metadata(article_path)
        self.assertIsInstance(out["json_ld"], list)
        self.assertIsInstance(out["meta"], dict)
        self.assertIsInstance(out["product_attributes"], dict)
        # Article.com product pages typically have og/twitter meta
        self.assertGreater(len(out["meta"]), 0)


class TestExtractDistilledContentIntegration(unittest.TestCase):
    """Run extract_distilled_content against real data files if present."""

    def test_data_dir_returns_markdown_string(self) -> None:
        """Parse data/article.html and assert result is non-empty Markdown string."""
        data_dir = Path(__file__).resolve().parent.parent / "data"
        article_path = data_dir / "article.html"
        if not article_path.exists():
            self.skipTest("data/article.html not found")
        out = extract_distilled_content(article_path)
        self.assertIsInstance(out, str)
        self.assertGreater(len(out.strip()), 0)


class TestGetHybridContextIntegration(unittest.TestCase):
    """Run get_hybrid_context against real data files if present."""

    def test_ace_html_truth_sheet_populated(self) -> None:
        """Parse data/ace.html and assert truth_sheet has Product fields."""
        data_dir = Path(__file__).resolve().parent.parent / "data"
        ace_path = data_dir / "ace.html"
        if not ace_path.exists():
            self.skipTest("data/ace.html not found")
        out = get_hybrid_context(ace_path)
        ts = out["truth_sheet"]
        self.assertIn("name", ts)
        self.assertIn("price", ts)
        self.assertIn("brand", ts)
        self.assertEqual(ts["brand"], "DeWalt")
        self.assertIn("key_features", ts)
        self.assertGreater(len(ts["key_features"]), 0)
        self.assertIn("image_urls", ts)
        self.assertGreater(len(ts["image_urls"]), 0)
        self.assertIn("variants", ts)
        self.assertGreater(len(ts["variants"]), 0)

    def test_get_hybrid_context_returns_md_content(self) -> None:
        """Parse data/ace.html and assert md_content is non-empty."""
        data_dir = Path(__file__).resolve().parent.parent / "data"
        ace_path = data_dir / "ace.html"
        if not ace_path.exists():
            self.skipTest("data/ace.html not found")
        out = get_hybrid_context(ace_path)
        self.assertIsInstance(out["md_content"], str)
        self.assertGreater(len(out["md_content"].strip()), 0)
