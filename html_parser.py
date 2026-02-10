"""
Hybrid Product Distillation Pipeline (Textual Pass)

This module converts messy HTML into high-signal Markdown by combining 
deterministic metadata extraction with heuristic content distillation.

Pipeline flows as follows:
1. Deterministic Extraction (BeautifulSoup): Harvest machine-readable 
   metadata (JSON-LD, OpenGraph) that heuristics may discard.
2. Heuristic Distillation (Trafilatura): Extract the 'core' product story 
   and specs while stripping navigation, ads, and boilerplate.

Output:
A condensed Markdown and metadata context for token-optimized AI hydration.
"""

from __future__ import annotations

import json
from pathlib import Path
from bs4 import BeautifulSoup
import trafilatura

# Helper functions for parsing messy web data
def _to_list(val):
    """Normalize value to list: None -> [], str -> [str], iterable -> list, else [val]."""
    if val is None:
        return []
    if isinstance(val, str):
        return [val]
    try:
        return list(val)
    except (TypeError, ValueError):
        return [val]

def _norm_float(val):
    """Parse value to float or None."""
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None

def _extract_product_from_embedded(data: dict) -> dict:
    """
    Extract product-like data from embedded JSON (Next.js, Nuxt, or heuristic).
    Returns dict with colors, variants, image_urls (only non-empty fields).
    """
    result: dict = {"colors": [], "variants": [], "image_urls": []}

    # Next.js: props.pageProps or props.__N_PAGE_PROPS__
    props = data.get("props") or {}
    page_props = props.get("pageProps") or props.get("__N_PAGE_PROPS__") or props
    if page_props and isinstance(page_props, dict):
        _harvest_colorway_images(page_props, result)

    # Nuxt: data or data.data
    nuxt = data.get("data")
    if isinstance(nuxt, dict):
        _harvest_colorway_images(nuxt.get("data", nuxt) if isinstance(nuxt.get("data"), dict) else nuxt, result)

    # Heuristic: recursive search for product-like keys
    if not result["colors"] and not result["variants"] and not result["image_urls"]:
        _heuristic_search(data, result, depth=0, max_depth=4)

    return {k: v for k, v in result.items() if v}

def _harvest_colorway_images(obj: dict, out: dict) -> None:
    """Extract from colorwayImages (Nike-style) or similar structures."""
    colorways = obj.get("colorwayImages") or obj.get("colorways") or obj.get("variants") or []
    if not isinstance(colorways, list):
        return
    for cw in colorways:
        if not isinstance(cw, dict):
            continue
        color = (cw.get("colorDescription") or cw.get("color") or cw.get("name")) and str(cw.get("colorDescription") or cw.get("color") or cw.get("name", "")).strip()
        im = cw.get("image")
        img = cw.get("squarishImg") or cw.get("portraitImg") or (im.get("url") or im.get("contentUrl") if isinstance(im, dict) else im)
        img = img.strip() if isinstance(img, str) else None
        if color and color not in out["colors"]:
            out["colors"].append(color)
        if img and img not in out["image_urls"]:
            out["image_urls"].append(img)
        out["variants"].append({
            "sku": cw.get("sku") or cw.get("id") or None,
            "color": color or None,
            "size": None,
            "price": _norm_float(cw.get("price")),
            "image_url": img,
        })

_PRODUCT_KEYS = frozenset({"colorDescription", "colorwayImages", "color", "variants", "hasVariant", "products", "productGroups", "image", "images"})

def _heuristic_search(obj: dict, out: dict, depth: int, max_depth: int) -> None:
    """Recursively search for product-like keys; harvest when found."""
    if depth >= max_depth or not isinstance(obj, dict):
        return
    for key, val in obj.items():
        if key not in _PRODUCT_KEYS:
            continue
        if key in ("colorwayImages", "colorways", "variants", "hasVariant", "products"):
            if isinstance(val, list) and val and isinstance(val[0], dict):
                _harvest_colorway_images({"colorwayImages": val}, out)
        elif key in ("color", "colorDescription") and val:
            s = str(val).strip()
            if s and s not in out["colors"]:
                out["colors"].append(s)
        elif key in ("image", "images"):
            for u in _to_list(val):
                u = u if isinstance(u, str) else (u.get("url") or u.get("contentUrl") if isinstance(u, dict) else None)
                if u and isinstance(u, str) and u.strip() and u not in out["image_urls"]:
                    out["image_urls"].append(u.strip())
        if isinstance(val, dict):
            _heuristic_search(val, out, depth + 1, max_depth)
        elif isinstance(val, list) and val and isinstance(val[0], dict):
            for item in val[:10]:
                _heuristic_search(item, out, depth + 1, max_depth)

# Pick out the high value metadata before the heuristic distillation process.
def extract_metadata(html_path: Path) -> dict:
    """
    Extract high-certainty machine-readable data (JSON-LD, OpenGraph, Twitter, data-*) using BeautifulSoup. 
    Returns a dict of metadata.
    """
    html_content = html_path.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(html_content, "html.parser")
    output: dict = {
        "json_ld": [],
        "embedded_json": [],
        "meta": {},
        "product_attributes": {},
    }

    # JSON-LD: highest value machine readable metadata. typically used for SEO for merchant sites.
    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string
        if not raw or not raw.strip():
            continue
        try:
            data = json.loads(raw)
            # Prevent nested lists if the json-ld data is already a list.
            if isinstance(data, list):
                output["json_ld"].extend(data)
            else:
                output["json_ld"].append(data)
        except (json.JSONDecodeError, TypeError):
            continue

    # Embedded JSON: Next.js, Nuxt, and other application/json scripts.
    for script in soup.find_all("script", type="application/json"):
        raw = script.string
        if not raw or not raw.strip():
            continue
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                output["embedded_json"].append(data)
        except (json.JSONDecodeError, TypeError):
            continue

    # Check for high value tags ie: "og:*", "product:*", "twitter:*", and "name"
    for tag in soup.find_all("meta"):
        if "property" not in tag.attrs and "name" not in tag.attrs:
            continue
        key = (tag.get("property") or tag.get("name") or "").strip().lower()
        content = tag.get("content")
        if key and content is not None and key not in output["meta"]:
            output["meta"][key] = content.strip()
    
    # Check all tags for common data-* attributes, a convention used by ecommerce sites that may contain product data.
    for tag in soup.find_all(True):
        if not any(cur_key.startswith("data-") for cur_key in tag.attrs):
            continue
        for key, val in tag.attrs.items():
            # iterate through the attributes in the tag for relevant content
            if not key.startswith("data-") or val is None:
                continue
            cur_key = key.lower()
            if any(
                x in cur_key
                for x in ("product", "price", "sku", "id", "image", "brand")
            ):
                output["product_attributes"][key] = str(val)
    
    return output

# Extract main content as Markdown using Trafilatura (Reader Mode heuristics).
def extract_distilled_content(html_path: Path) -> str:
    """
    Extract main content as Markdown using Trafilatura (Reader Mode heuristics). 
    Returns markdown-formatted string.
    """
    html_content = html_path.read_text(encoding="utf-8", errors="replace")
    if not html_content.strip():
        return ""
    result = trafilatura.extract(
        html_content,
        output_format="markdown",
        include_links=True,
        include_images=True,
        include_tables=True,
        favor_recall=True,
    )
    return result or ""

# Stage 1: Contextual Anchoring
# Extracts high-fidelity deterministic data (JSON-LD) to anchor the AI hydration stage.
# Adheres to Schema.org standards to ensure cross-merchant compatibility.
def get_hybrid_context(html_path: Path) -> dict:
    """
    Unified entrypoint for stage 1 of pipeline.
    Returns a dict with 'truth_sheet', 'md_content', and 'product_json_ld'
    """
    raw_meta = extract_metadata(html_path)
    md_content = extract_distilled_content(html_path)

    # Extract the relevant data from the json_ld. eCommerce conventions dictate that the "@type" value will be "Products".
    # NB: Truth sheet will be filled following the conventions outlined on https://schema.org/Product.
    json_ld_list = raw_meta.get("json_ld") or []
    json_ld = {}
    for script in json_ld_list:
        obj_type = script.get("@type", "")
        if obj_type == "Product" or (isinstance(obj_type, list) and "Product" in obj_type):
            json_ld = script
            break

    # Build truth_sheet from json_ld, following Product/ProductVariant schema.
    # Leave values None or empty when not present in json_ld.
    truth_sheet: dict = {
        "name": json_ld.get("name") or None,
        "price": None,
        "description": json_ld.get("description") or None,
        "key_features": [],
        "image_urls": [],
        "video_url": None,
        "category": json_ld.get("category") or None,
        "brand": None,
        "colors": [],
        "variants": [],
    }

    # brand: schema.org uses { "@type": "Brand", "name": "X" } or plain string
    brand_val = json_ld.get("brand")
    if isinstance(brand_val, dict) and brand_val.get("name"):
        truth_sheet["brand"] = str(brand_val["name"]).strip() or None
    elif isinstance(brand_val, str) and brand_val.strip():
        truth_sheet["brand"] = brand_val.strip()

    # price: from offers (single object or array)
    offers = json_ld.get("offers")
    if offers is not None:
        offer_list = offers if isinstance(offers, list) else [offers]
        for offer in offer_list:
            if not isinstance(offer, dict):
                continue
            price_val = _norm_float(offer.get("price"))
            if price_val is not None:
                currency = offer.get("priceCurrency") or "USD"
                truth_sheet["price"] = {
                    "price": price_val,
                    "currency": str(currency).strip() if currency else "USD",
                    "compare_at_price": _norm_float(offer.get("highPrice")),
                }
                break

    # key_features: positiveNotes (list of strings or {name} dicts) or additionalProperty
    notes = json_ld.get("positiveNotes")
    if isinstance(notes, list):
        for x in notes:
            if x is None:
                continue
            s = str(x.get("name", x)).strip() if isinstance(x, dict) else str(x).strip()
            if s:
                truth_sheet["key_features"].append(s)
    add_props = json_ld.get("additionalProperty") or []
    if not truth_sheet["key_features"]:
        add_props = add_props if isinstance(add_props, list) else ([add_props] if isinstance(add_props, dict) else [])
        for p in add_props:
            if isinstance(p, dict):
                val = p.get("value") or p.get("name")
                if val is not None and str(val).strip():
                    truth_sheet["key_features"].append(str(val).strip())

    # image_urls: from JSON-LD (fallback when Verified Media is empty or sparse)
    imgs = json_ld.get("images") or json_ld.get("image")
    for u in _to_list(imgs):
        if isinstance(u, str):
            u = u.strip() if u else None
        elif isinstance(u, dict):
            raw = u.get("url") or u.get("contentUrl")
            u = raw.strip() if isinstance(raw, str) else None
        else:
            u = str(u).strip() if u is not None else None
        if u and u not in truth_sheet["image_urls"]:
            truth_sheet["image_urls"].append(u)
    if not truth_sheet["image_urls"] and json_ld.get("image"):
        u = json_ld["image"]
        u = u.strip() if isinstance(u, str) else None
        if u:
            truth_sheet["image_urls"].append(u)
    # Drop non-product paths (e.g. email signup) so we don't feed bad URLs to the LLM.
    from image_processor import _drop_non_product_urls
    truth_sheet["image_urls"] = _drop_non_product_urls(truth_sheet["image_urls"])
    # When JSON-LD had no product image (or only bad ones), use og:image as fallback (e.g. L.L.Bean).
    if not truth_sheet["image_urls"]:
        og_image = (raw_meta.get("meta") or {}).get("og:image")
        if isinstance(og_image, str) and og_image.strip():
            truth_sheet["image_urls"].append(og_image.strip())

    # video_url: schema.org video can be string, VideoObject {embedUrl, contentUrl}, or array
    vid = json_ld.get("video")
    if isinstance(vid, list) and vid:
        vid = vid[0]
    if isinstance(vid, dict):
        vid = vid.get("embedUrl") or vid.get("contentUrl")
    truth_sheet["video_url"] = vid.strip() if isinstance(vid, str) else None

    # colors
    color_val = json_ld.get("color")
    truth_sheet["colors"] = [str(x).strip() for x in _to_list(color_val) if x is not None and str(x).strip()]

    # variants: hasVariant or similar
    has_variant = json_ld.get("hasVariant", [])
    variant_list = has_variant if isinstance(has_variant, list) else [has_variant]
    for v in variant_list:
        if not isinstance(v, dict):
            continue
        var = {
            "sku": v.get("sku") or None,
            "color": v.get("color") or None,
            "size": v.get("size") or v.get("width") or None,
            "price": _norm_float(v.get("price")),
            "image_url": None,
        }
        v_img = v.get("image") or v.get("image_url")
        if v_img:
            v_url = v_img if isinstance(v_img, str) else (v_img.get("url") or v_img.get("contentUrl") if isinstance(v_img, dict) else None)
            var["image_url"] = v_url.strip() if isinstance(v_url, str) else None
        truth_sheet["variants"].append(var)

    # If no hasVariant but product has sku, treat as single variant
    if not truth_sheet["variants"] and json_ld.get("sku"):
        truth_sheet["variants"].append({
            "sku": json_ld.get("sku"),
            "color": json_ld.get("color") or None,
            "size": None,
            "price": truth_sheet["price"]["price"] if isinstance(truth_sheet.get("price"), dict) else None,
            "image_url": truth_sheet["image_urls"][0] if truth_sheet["image_urls"] else None,
        })

    # Merge embedded JSON (Next.js, Nuxt, heuristic) into truth_sheet when fields are empty
    for emb in raw_meta.get("embedded_json") or []:
        extracted = _extract_product_from_embedded(emb)
        if not extracted.get("image_urls") and not extracted.get("colors") and not extracted.get("variants"):
            continue
        if not truth_sheet["colors"] and extracted.get("colors"):
            truth_sheet["colors"] = extracted["colors"]
        if not truth_sheet["variants"] and extracted.get("variants"):
            truth_sheet["variants"] = extracted["variants"]
        if not truth_sheet["image_urls"] and extracted.get("image_urls"):
            truth_sheet["image_urls"] = extracted["image_urls"]
        elif extracted.get("image_urls"):
            for u in extracted["image_urls"]:
                if u and u not in truth_sheet["image_urls"]:
                    truth_sheet["image_urls"].append(u)
    truth_sheet["image_urls"] = _drop_non_product_urls(truth_sheet["image_urls"])

    return {
        "truth_sheet": truth_sheet,
        "md_content": md_content,
        "product_json_ld": json_ld_list
    }
