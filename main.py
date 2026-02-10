import ai
import argparse
import asyncio
import json
import logging
from pathlib import Path
from pydantic import ValidationError

from html_parser import get_hybrid_context
from image_processor import get_filtered_media
from models import Product, DEFAULT_PRODUCT

ai_instructions = """
# Role
You are a Senior Data Integrity Agent. Your task is to reconcile raw web extraction data into a single, high-fidelity JSON Product Object.

# Inputs
1. **Truth Sheet**: Structured data from Schema.org JSON-LD (when present). Many pages use other data, so the Truth Sheet may be missing or wrong for some fields. Evaluate it per field before trusting it.
2. **Product Context (Markdown)**: Distilled main content of the page. Use for any field when the Truth Sheet is missing, incomplete, or unreliable for that field.
3. **Product JSON-LD**: Array of all schema.org JSON-LD scripts from the page (Product, ProductGroup, Organization, BreadcrumbList, etc.). Use the block(s) that contain product data; price may be in offers or hasVariant[].offers.
4. **Verified Media**: Image URLs that passed quality gates. Prefer these for image_urls.
5. **Image Candidates**: Page image URLs that passed the non-product path filter. Use when Verified Media is empty.
6. **Image Metadata**: Optional per-image hints (alt text, OpenGraph source, or structured-data origin) keyed by URL, to help distinguish true product photos from brand or certification logos.

# Instructions
- **Judge the Truth Sheet first (for every field)**: Before using the Truth Sheet for price, name, brand, images, etc., evaluate whether it is complete and reliable for this page. Use the Truth Sheet for a field only when it passes that bar; when it's missing, empty, or clearly wrong for the page, use Product Context (Markdown) or other inputs instead. Do this evaluation for every field—not only when the Truth Sheet looks obviously sparse.
- **Reconciliation**: Fill any field from Product Context when the Truth Sheet doesn't provide good data for that field. Do not default to zero or empty when the page clearly has the information in Markdown.
- **Sanity-check every field**: For each output field (name, price, category, brand, etc.), if the value from one input looks wrong—e.g. an ID instead of a label (numeric-only category), a placeholder, or clearly not user-facing—ignore it and resolve that field from other inputs (Truth Sheet, JSON-LD, Embedded JSON, Product Context). Prefer human-readable, display-ready values over raw IDs or internal codes.
- **Image Selection**: Populate image_urls from Verified Media when non-empty; when empty, choose from Image Candidates (and/or truth sheet image_urls / variant image_url). **Prioritize PRODUCT-ONLY images** (product on clean/white background; no models or lifestyle). Exclude marketing, banner, email-signup imagery, and **exclude partner/certification logos and third-party brand logos**—include only images that show the product itself. Use the `image_metadata` hints (alt text or source labels) to prefer images whose hints describe the product (e.g. “Miller Cotton Lyocell Trousers”) over those that look like logos, badges, or social/shipping icons. **Backfill**: If the product has no image_urls but one or more variants have image_url, set image_urls from those variant image_url(s) (e.g. include the first variant’s image_url so the base product has at least one image).
- **Formatting**: Output ONLY valid JSON. No prose.
- **Constraint**: For critical fields (**name**, **price**, **description**), if a value is not found in any input, return `null` and do **not** invent it. For high-level display fields (e.g. **category**, **brand**, **key_features**), you may make conservative, well-supported inferences from the product name, description, headings, or breadcrumbs when structured data is missing or clearly wrong, but prefer explicit labels when they exist.

# Schema Requirements
{
  "name": "string",
  "brand": "string",
  "price": {"price": number, "currency": "string", "compare_at_price": number | null},
  "description": "string (concise, focus on specs)",
  "key_features": ["list", "of", "key", "points"],
  "primary_image": "url",
  "gallery": ["url", "url"]
}

# Input Data
For each field, use the Truth Sheet only when it is present and reliable; otherwise use Product Context (Markdown).

<truth_sheet>
{{truth_sheet}}
</truth_sheet>

<product_context>
{{markdown}}
</product_context>

<product_json_ld>
{{product_json_ld}}
</product_json_ld>

<verified_media>
{{verified_images}}
</verified_media>

<image_candidates>
{{image_candidates}}
</image_candidates>

<image_metadata>
{{image_metadata}}
</image_metadata>

# Response
"""

async def run_pipeline(html_path: str):
    path = Path(html_path)
    try:
        context, media = await asyncio.gather(
            asyncio.to_thread(get_hybrid_context, path),
            get_filtered_media(path),
        )
    except Exception as e:
        logging.warning("Pipeline context/media failed for %s: %s", html_path, e)
        return DEFAULT_PRODUCT

    truth_sheet = context["truth_sheet"]
    markdown = context["md_content"]
    product_json_ld = context.get("product_json_ld", [])
    verified_images = media["images"]
    image_candidates = media.get("candidates", [])
    image_metadata = media.get("candidate_metadata", [])

    try:
        response = await ai.responses(
            "gpt-5-nano",
            [
                {
                    "role": "system",
                    "content": ai_instructions
                        .replace("{{truth_sheet}}", str(truth_sheet))
                        .replace("{{markdown}}", markdown)
                        .replace("{{product_json_ld}}", json.dumps(product_json_ld))
                        .replace("{{verified_images}}", str(verified_images))
                        .replace("{{image_candidates}}", str(image_candidates))
                        .replace("{{image_metadata}}", json.dumps(image_metadata))
                }
            ],
            text_format=Product
        )
    except ValidationError as e:
        logging.warning("Schema validation failed for %s: %s", html_path, e)
        return DEFAULT_PRODUCT
    except Exception as e:
        logging.warning("AI request failed for %s: %s", html_path, e)
        return DEFAULT_PRODUCT
    if not response.image_urls and truth_sheet.get("image_urls"):
        response = response.model_copy(update={"image_urls": truth_sheet["image_urls"][:1]})

    return response



async def run_all_pipelines(html_paths: list[str]):
    tasks = [run_pipeline(path) for path in html_paths]
    return await asyncio.gather(*tasks, return_exceptions=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run product extraction pipeline on data/*.html")
    parser.add_argument(
        "--export",
        type=str,
        metavar="PATH",
        help="Write successful products to JSON (e.g. output/products.json) with an 'id' per product",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    sample_files = sorted(str(file_path) for file_path in Path("data").glob("*.html"))
    results = asyncio.run(run_all_pipelines(sample_files))

    for path, result in zip(sample_files, results):
        if isinstance(result, BaseException):
            logging.error(f"Failed {path}: {result}")
        else:
            name = getattr(result, "name", str(result)[:50])
            logging.info(f"Result for {path}: {name}")

    if args.export:
        products = [
            res for res in results
            if not isinstance(res, BaseException) and isinstance(res, Product)
        ]
        out_path = Path(args.export)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        payload = []
        for i, p in enumerate(products):
            d = p.model_dump()
            d["id"] = i
            payload.append(d)
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        logging.info(f"Exported {len(payload)} products to {out_path}")
