"""
Scrape recipe steps + Budget Bytes categories for all titles in recipes_enriched.csv.
Merges into enriched data and saves as recipes_with_steps.csv.

Per recipe:
  - HTML fetch  → extract steps from wprm-recipe-instruction elements
  - WP REST API → extract category IDs, mapped to a simplified label
"""

import re
import time
import json
import logging
from pathlib import Path
from xml.etree import ElementTree as ET

import requests
from bs4 import BeautifulSoup
import pandas as pd
from tqdm import tqdm

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}
SLEEP_SEC = 1.5
DATA_DIR = Path(__file__).parent
ENRICHED_CSV = DATA_DIR / "recipes_enriched.csv"
OUT_CSV = DATA_DIR / "recipes_with_steps.csv"
SITEMAP_CACHE = DATA_DIR / "sitemap_urls.json"

# WP category ID → simplified meal-planning label (first match wins)
_CATEGORY_PRIORITY: list[tuple[int, str]] = [
    (3639,  "side_dish"),
    (12,    "breakfast"),
    (10061, "snack"),       # appetizers
    (33,    "dessert"),
    (44,    "drink"),
    (32,    "main_dish"),   # soups → lunch/dinner
    (37,    "main_dish"),   # salads → lunch/dinner
    (6,     "main_dish"),   # explicit main-dish
]
_FALLBACK_CATEGORY = "main_dish"


def title_to_slug(title: str) -> str:
    slug = title.lower()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"\s+", "-", slug.strip())
    slug = re.sub(r"-+", "-", slug)
    return slug


def get_sitemap_urls() -> dict[str, str]:
    """Return {slug: full_url} for all Budget Bytes post URLs."""
    if SITEMAP_CACHE.exists():
        log.info("Loading sitemap from cache %s", SITEMAP_CACHE)
        return json.loads(SITEMAP_CACHE.read_text())

    ns = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
    slug_to_url: dict[str, str] = {}
    for suffix in ["", "2", "3"]:
        url = f"https://www.budgetbytes.com/post-sitemap{suffix}.xml"
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        root = ET.fromstring(r.text)
        for loc_el in root.iter(f"{ns}loc"):
            loc = loc_el.text or ""
            if "wp-content" in loc:
                continue
            slug = loc.rstrip("/").split("/")[-1]
            slug_to_url[slug] = loc
        log.info("post-sitemap%s: %d entries total", suffix, len(slug_to_url))
        time.sleep(0.5)

    SITEMAP_CACHE.write_text(json.dumps(slug_to_url, indent=2))
    return slug_to_url


def _get_with_retry(
    url: str,
    params: dict | None = None,
    timeout: int = 15,
    max_retries: int = 5,
    base_sleep: float = 2.0,
) -> requests.Response | None:
    """GET with exponential backoff on 429/5xx. Returns None after all retries fail."""
    for attempt in range(max_retries):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
        except requests.RequestException as e:
            log.warning("Request error (attempt %d/%d) %s: %s", attempt + 1, max_retries, url, e)
            time.sleep(base_sleep * (2 ** attempt))
            continue

        if r.status_code == 429:
            retry_after = float(r.headers.get("Retry-After", base_sleep * (2 ** attempt)))
            log.warning("Rate limited (attempt %d/%d), sleeping %.0fs", attempt + 1, max_retries, retry_after)
            time.sleep(retry_after)
            continue

        if r.status_code >= 500:
            log.warning("Server error %d (attempt %d/%d) %s", r.status_code, attempt + 1, max_retries, url)
            time.sleep(base_sleep * (2 ** attempt))
            continue

        return r

    log.error("All %d retries exhausted for %s", max_retries, url)
    return None


def fetch_bb_category(slug: str) -> str:
    """Return a simplified category label for a recipe slug via WP REST API."""
    r = _get_with_retry(
        "https://www.budgetbytes.com/wp-json/wp/v2/posts",
        params={"slug": slug, "_fields": "categories"},
        timeout=10,
    )
    if r is None:
        return _FALLBACK_CATEGORY
    try:
        r.raise_for_status()
        data = r.json()
        if not data:
            return _FALLBACK_CATEGORY
        cat_ids: set[int] = set(data[0].get("categories", []))
        for cid, label in _CATEGORY_PRIORITY:
            if cid in cat_ids:
                return label
        return _FALLBACK_CATEGORY
    except Exception as e:
        log.warning("Category parse failed for %s: %s", slug, e)
        return _FALLBACK_CATEGORY


def extract_steps(url: str) -> list[str] | None:
    """Fetch a recipe page and return its steps, or None."""
    r = _get_with_retry(url)
    if r is None:
        return None
    try:
        r.raise_for_status()
    except Exception as e:
        log.warning("HTTP error for %s: %s", url, e)
        return None

    soup = BeautifulSoup(r.content, "html.parser")
    container = soup.find(class_="wprm-recipe-container")
    if container is None:
        return None

    steps = []
    for ins in container.find_all("li", class_="wprm-recipe-instruction"):
        step_el = ins.find(class_="wprm-recipe-instruction-text") or ins
        text = step_el.get_text(" ", strip=True)
        if text:
            steps.append(text)
    return steps if steps else None


def main() -> None:
    df = pd.read_csv(ENRICHED_CSV)
    log.info("Loaded %d recipes from %s", len(df), ENRICHED_CSV)

    sitemap = get_sitemap_urls()

    steps_map: dict[str, list[str] | None] = {}
    category_map: dict[str, str] = {}
    miss_titles: list[str] = []

    for title in tqdm(df["title"], desc="Scraping"):
        slug = title_to_slug(title)
        url = sitemap.get(slug, f"https://www.budgetbytes.com/{slug}/")

        steps = extract_steps(url)
        category = fetch_bb_category(slug)

        if steps:
            steps_map[title] = steps
        else:
            miss_titles.append(title)
            steps_map[title] = None
        category_map[title] = category

        time.sleep(SLEEP_SEC)

    hit_count = len(df) - len(miss_titles)
    log.info("Steps hit: %d  miss: %d", hit_count, len(miss_titles))
    if miss_titles:
        log.info("Missed: %s", miss_titles[:10])

    df["steps"] = df["title"].map(steps_map)
    df["bb_category"] = df["title"].map(category_map)
    df.to_csv(OUT_CSV, index=False)
    log.info("Saved to %s", OUT_CSV)
    log.info("Steps coverage: %.1f%%", df["steps"].notna().mean() * 100)

    log.info("Category distribution:\n%s", df["bb_category"].value_counts().to_string())


if __name__ == "__main__":
    main()
