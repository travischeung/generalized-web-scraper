"""
Image URL extraction and async filtering for the product extraction pipeline.

Responsibilities:
- Extract candidate image URLs from HTML (img, srcset, meta, JSON-LD).
- Filter to product-quality images: ~1:1 aspect, both sides ≥ MIN_SIDE, valid types.
"""

from __future__ import annotations

import asyncio
import io
import logging
import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Tuple

import aiohttp
from PIL import Image
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

if TYPE_CHECKING:
    from models import Product


# Product-quality criteria per plan: ~1:1 aspect, both sides ≥ 500px, valid image types.
MIN_SIDE = 500
ASPECT_LOW, ASPECT_HIGH = 0.8, 1.25  # aspect ratio tolerance around 1:1
VALID_IMAGE_TYPES = {"jpeg", "jpg", "png", "webp"}


# --- Helpers functions --- 
def _normalize_url(url: str, base: Optional[str]) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    if base and not url.startswith(("http://", "https://", "//")):
        return urljoin(base, url)
    if url.startswith("//"):
        return "https:" + url
    return url

def _parse_best_from_srcset(srcset_str: str) -> str | None:
    if not srcset_str:
        return None
    candidates = []
    for entry in srcset_str.split(','):
        parts = entry.strip().split()
        if not parts:
            continue
        url = parts[0].strip()
        if not url:
            continue

        score = 0        
        if len(parts) > 1:
            descriptor = parts[1].lower()
            # Extract digits from '1200w' or '2x'
            nums = re.findall(r'\d+', descriptor)
            if nums:
                score = int(nums[0])
        
        candidates.append({"url": url, "score": score})

    if not candidates:
        return None

    # Sort by score descending; among ties, first in srcset is kept.
    best = sorted(candidates, key=lambda x: x['score'], reverse=True)[0]
    return best["url"]

def _dedupe_images(urls: list[str]) -> list[str]:
    """
    Groups images by their base identity to avoid redundant resolutions 
    (e.g., shoe-100x100.jpg and shoe-max.jpg are treated as the same asset).
    """
    if not urls:
        return []
    best_candidates = {}

    for url in urls:
            # Strip query params and resolution-specific suffixes
            base = url.split("?")[0]
            identity = re.sub(
                r'[-_](\d+x\d+|thumb|small|medium|max|large|original)', 
                '', base, flags=re.IGNORECASE
            )
            # Prioritize the version with the longest URL (likely containing higher-res markers)
            if identity not in best_candidates or len(url) > len(best_candidates[identity]):
                best_candidates[identity] = url
    return list[str](best_candidates.values())

# --- Image processing ---

def _collect_image_urls_and_metadata(
    html_path: Path, base_url: Optional[str] = None
) -> tuple[list[str], dict[str, str]]:
    """
    Single-pass HTML traversal to collect:
      - candidate image URLs
      - lightweight per-image hints (alt text, meta source, json-ld origin)

    Public helpers `extract_image_urls` and `extract_image_metadata` build on top
    of this to keep responsibilities clear and the API small.
    """
    html_content = html_path.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(html_content, "html.parser")
    base = base_url
    if not base:
        base_tag = soup.find("base", attrs={"href": True})
        if base_tag:
            base = base_tag.get("href")

    seen: set[str] = set()
    urls: list[str] = []
    hints: dict[str, str] = {}

    def add_url(raw_url: str) -> Optional[str]:
        """Normalize and register a URL, returning the normalized value or None."""
        url = _normalize_url(raw_url, base)
        if not url.startswith(("http://", "https://", "//")):
            return None
        if not urlparse(url).path.strip("/"):
            return None
        if url not in seen:
            seen.add(url)
            urls.append(url)
        return url

    def add_hint(raw_url: str, label: str) -> None:
        """Attach a human-ish label to a URL for LLM reasoning."""
        if not label:
            return
        url = _normalize_url(raw_url, base)
        if not url.startswith(("http://", "https://", "//")):
            return
        if not urlparse(url).path.strip("/"):
            return
        label = label.strip()
        if not label:
            return
        prev = hints.get(url)
        if not prev:
            hints[url] = label
        elif label not in prev:
            hints[url] = f"{prev}; {label}"

    # <img> tags: collect URLs plus alt-text hints when available.
    for img in soup.find_all("img"):
        alt_text = img.get("alt") or ""
        for attr in ("src", "data-src", "data-lazy-src", "data-original"):
            img_url = img.get(attr)
            if not img_url:
                continue
            normalized = add_url(img_url)
            if alt_text and normalized:
                add_hint(normalized, alt_text)
        for attr in ("srcset", "data-srcset"):
            img_url = img.get(attr)
            if not img_url:
                continue
            best_url = _parse_best_from_srcset(img_url)
            if best_url:
                normalized = add_url(best_url)
                if alt_text and normalized:
                    add_hint(normalized, alt_text)

    # Meta tags: og:image / twitter:image
    for meta in soup.find_all("meta"):
        key = (meta.get("property") or meta.get("name") or "").strip().lower()
        if key in ("og:image", "og:image:secure_url", "twitter:image"):
            img_url = meta.get("content")
            if img_url:
                normalized = add_url(img_url)
                if normalized:
                    add_hint(normalized, key)

    # JSON-LD images: also mark as coming from structured data.
    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string
        if not raw or not raw.strip():
            continue
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                items = [x for x in data if isinstance(x, dict)]
            elif isinstance(data, dict):
                items = [data]
            else:
                continue

            for item in items:
                for key in ("image", "images"):
                    val = item.get(key)
                    if val is None:
                        continue
                    if isinstance(val, str):
                        normalized = add_url(val)
                        if normalized:
                            add_hint(normalized, "json-ld image")
                    elif isinstance(val, dict) and "url" in val:
                        normalized = add_url(val["url"])
                        if normalized:
                            add_hint(normalized, "json-ld image")
                    elif isinstance(val, list):
                        for v in val:
                            if isinstance(v, str):
                                normalized = add_url(v)
                                if normalized:
                                    add_hint(normalized, "json-ld image")
                            elif isinstance(v, dict) and "url" in v:
                                normalized = add_url(v["url"])
                                if normalized:
                                    add_hint(normalized, "json-ld image")
        except (json.JSONDecodeError, TypeError):
            continue

    return (urls, hints)

# --- Async image filtering ---

logger = logging.getLogger(__name__)

# Bytes to fetch for header-based dimension checks (enough for JPEG/PNG/WebP/GIF headers).
_HEADER_READ_SIZE = 64 * 1024


def _is_valid_image_type(url: str) -> bool:
    """Check URL path extension is in VALID_IMAGE_TYPES."""
    path = urlparse(url).path.lower()
    ext = path.rsplit(".", 1)[-1] if "." in path else ""
    return ext in VALID_IMAGE_TYPES


def _passes_quality(w: int, h: int) -> bool:
    """True if both sides ≥ MIN_SIDE and aspect in [ASPECT_LOW, ASPECT_HIGH]."""
    if w < MIN_SIDE or h < MIN_SIDE:
        return False
    aspect = w / h if h else 0
    return ASPECT_LOW <= aspect <= ASPECT_HIGH


async def _get_img_dims(session: aiohttp.ClientSession, url: str) -> Optional[Tuple[int, int]]:
    """
    Fetch enough bytes to read image dimensions via PIL. No quality checks or judgements are made yet.
    Return (width, height) or None on failure.
    """
    try:
        async with session.get(url) as resp:
            if resp.status != 200:
                return None
            data = await resp.content.read(_HEADER_READ_SIZE)
        img = Image.open(io.BytesIO(data))
        width, height = img.size
        return (width, height)
    except Exception as e:
        logger.debug("Image dimension retrieval failed for %s: '%s'.", url, e)
        return None


async def filter_image_urls(
    urls: list[str],
    *,
    max_concurrent: int = 10,
) -> list[str]:
    """
    Async filter candidate URLs to product-quality images:
    both sides ≥ MIN_SIDE, aspect in [ASPECT_LOW, ASPECT_HIGH], valid image types.
    """
    img_urls = [url for url in urls if _is_valid_image_type(url)]
    if not img_urls:
        return []

    sem = asyncio.Semaphore(max_concurrent)

    async def check(session: aiohttp.ClientSession, url: str) -> Optional[str]:
        async with sem:
            dims = await _get_img_dims(session, url)
        
        if dims and _passes_quality(dims[0], dims[1]):
            return url
        return None

    async def run() -> list[str]:
        async with aiohttp.ClientSession() as session:
            # Fire all checks concurrently; order of results matches order of img_urls candidates.
            results = await asyncio.gather(*[check(session, url) for url in img_urls])
        # Drop failures and non–product-quality images (None).
        return [r for r in results if r is not None]

    return await run()


# Case-insensitive; edit here to add/remove. Used so we never fetch or pass these to the model.
NON_PRODUCT_PATH_SUBSTRINGS = ("email_sign_up", "EMAILprompt", "sign_up", "banner", "promo", "logo")


def _drop_non_product_urls(
    urls: list[str],
    blocklist: tuple[str, ...] | None = None,
) -> list[str]:
    """Drop URLs whose path contains any blocklist substring. Used in pipeline and in product normalization."""
    blocklist = blocklist or NON_PRODUCT_PATH_SUBSTRINGS
    if not urls:
        return []
    kept = []
    for u in urls:
        path = (urlparse(u).path or "").lower()
        if not any(sub.lower() in path for sub in blocklist):
            kept.append(u)
    return kept


# Stage 2 of the data ingestion pipeline
async def get_filtered_media(html_path: Path, base_url: Optional[str] = None) -> dict:
    """
    Unified entrypoint for stage 2 of pipeline.
    Extracts candidate images from HTML and metadata, drops non-product paths (email/banner/promo),
    then async filters for high-fidelity product shots (dimensions, aspect).

    Returns:
        images: URLs that passed dimension/aspect checks (verified product-quality).
        candidates: All URLs that passed the path filter, before dimension check. Passed to the LLM
                    so it can reason over them when verified is empty (e.g. og:image that failed fetch).
    """
    candidate_urls, metadata_by_url = _collect_image_urls_and_metadata(html_path, base_url=base_url)
    candidate_urls = _drop_non_product_urls(candidate_urls)
    if not candidate_urls:
        return {"images": [], "candidates": [], "candidate_metadata": []}
    filtered_images = await filter_image_urls(candidate_urls)
    return {
        "images": filtered_images,
        "candidates": candidate_urls,
        "candidate_metadata": [
            {"url": u, "hint": metadata_by_url.get(u, "")} for u in candidate_urls
        ],
    }
    