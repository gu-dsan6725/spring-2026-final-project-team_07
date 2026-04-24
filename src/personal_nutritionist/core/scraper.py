"""
Fetch a recipe from a URL. Tries JSON-LD (schema.org/Recipe) first since most
recipe sites embed it. Falls back to stripping the page to readable text and
asking Claude to extract the fields.
"""

import json
import logging
import os
import re

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

_EXTRACT_PROMPT = """
Extract recipe information from the text below and return a JSON object.
Include only fields you can confidently determine. Omit fields you cannot find.

Required if present:
- title (str)
- ingredients (list of strings, each a full ingredient line)
- steps (list of strings, each a complete step)
- servings (float)
- prep_time (int, minutes)
- cook_time (int, minutes)
- calories (float, per serving)
- protein (float, grams per serving)
- fat (float, grams per serving)
- carbs (float, grams per serving)
- cost_per_serving (float, USD — omit if not mentioned)
- category (str: breakfast, main_dish, side_dish, snack, dessert, or drink)

Respond with a JSON object only. No markdown fences, no prose.

PAGE TEXT:
{text}
""".strip()


def _parse_duration(value) -> int | None:
    """Parse ISO 8601 duration string (PT30M, PT1H30M) to minutes."""
    if not value or not isinstance(value, str):
        return None
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?", value)
    if not m:
        return None
    hours = int(m.group(1) or 0)
    minutes = int(m.group(2) or 0)
    return hours * 60 + minutes


def _from_json_ld(soup: BeautifulSoup) -> dict | None:
    """Try to extract a schema.org/Recipe from JSON-LD script tags."""
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except (json.JSONDecodeError, TypeError):
            continue

        if isinstance(data, list):
            data = next((d for d in data if d.get("@type") == "Recipe"), None)
        if isinstance(data, dict) and data.get("@type") == "Recipe":
            recipe: dict = {}

            recipe["title"] = data.get("name", "")

            ingredients = data.get("recipeIngredient") or []
            recipe["ingredients"] = [str(i) for i in ingredients]

            instructions = data.get("recipeInstructions") or []
            steps = []
            for inst in instructions:
                if isinstance(inst, str):
                    steps.append(inst)
                elif isinstance(inst, dict):
                    steps.append(inst.get("text", ""))
            recipe["steps"] = steps

            servings_raw = data.get("recipeYield")
            if isinstance(servings_raw, list):
                servings_raw = servings_raw[0]
            if servings_raw:
                try:
                    recipe["servings"] = float(re.search(r"\d+", str(servings_raw)).group())
                except (AttributeError, ValueError):
                    pass

            recipe["prep_time"] = _parse_duration(data.get("prepTime"))
            recipe["cook_time"] = _parse_duration(data.get("cookTime"))

            nutrition = data.get("nutrition") or {}
            for field, key in [
                ("calories", "calories"),
                ("protein", "proteinContent"),
                ("fat", "fatContent"),
                ("carbs", "carbohydrateContent"),
            ]:
                raw = nutrition.get(key)
                if raw:
                    try:
                        recipe[field] = float(re.search(r"[\d.]+", str(raw)).group())
                    except (AttributeError, ValueError):
                        pass

            return {k: v for k, v in recipe.items() if v is not None and v != "" and v != []}

    return None


def _page_text(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "iframe"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return "\n".join(lines)[:12000]


def _from_llm(text: str) -> dict:
    import anthropic
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    message = client.messages.create(
        model=os.getenv("ORCHESTRATOR_MODEL", "claude-sonnet-4-6"),
        max_tokens=1024,
        messages=[{"role": "user", "content": _EXTRACT_PROMPT.format(text=text)}],
    )
    return json.loads(message.content[0].text)


def scrape_recipe(url: str) -> dict:
    """
    Fetch a recipe URL and return a partial recipe dict.
    Raises httpx.HTTPError on network failure, ValueError if nothing useful found.
    """
    resp = httpx.get(url, headers=_HEADERS, follow_redirects=True, timeout=15)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "lxml")

    data = _from_json_ld(soup)
    if data and data.get("title") and data.get("ingredients"):
        logger.info("scrape_recipe json-ld success url=%s", url)
        return data

    logger.info("scrape_recipe json-ld empty, falling back to LLM url=%s", url)
    text = _page_text(soup)
    if not text:
        raise ValueError("Page produced no readable text")
    return _from_llm(text)
