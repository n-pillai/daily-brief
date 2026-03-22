#!/usr/bin/env python3
"""
Daily Brief Generator
Searches for today's news, synthesises it via Claude, generates audio via Deepgram,
and produces an HTML brief + MP3 file.
"""

import os
import re
import json
import time
import datetime
import requests
from pathlib import Path
import anthropic
from anthropic import Anthropic
from jinja2 import Template

# ── Configuration ──────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
DEEPGRAM_API_KEY = os.environ["DEEPGRAM_API_KEY"]
DEEPGRAM_VOICE = "aura-helios-en"  # British male
RESEND_API_KEY = os.environ["RESEND_API_KEY"]
RECIPIENT_EMAILS = [e.strip() for e in os.environ["RECIPIENT_EMAILS"].split(",")]

TODAY = datetime.date.today()
YESTERDAY = TODAY - datetime.timedelta(days=1)
DATE_STR = TODAY.strftime("%B %d, %Y")         # February 28, 2026
YESTERDAY_STR = YESTERDAY.strftime("%B %d, %Y")
DATE_FILE = TODAY.strftime("%Y-%m-%d")          # 2026-02-28
DAY_NAME = TODAY.strftime("%A")                 # Friday

OUTPUT_DIR = Path("briefs")
OUTPUT_DIR.mkdir(exist_ok=True)

TEMPLATE_PATH = Path("templates/brief_template.html")

# ── Load config ────────────────────────────────────────────────────────────
_config = json.loads(Path("config.json").read_text())
SOURCES = _config["sources"]
CATEGORIES = _config["categories"]
TRUSTED_SOURCES = SOURCES["trusted_sources"]

WEATHER_LOCATIONS = [
    {"label": "Home", "icon": "🏠", "query": os.environ.get("WEATHER_LOCATION_HOME", "")},
    {"label": "Work", "icon": "🏢", "query": os.environ.get("WEATHER_LOCATION_WORK", "")},
]

client = Anthropic(api_key=ANTHROPIC_API_KEY)


# ── Weather ───────────────────────────────────────────────────────────────
def _wmo_icon(code: int) -> str:
    if code == 0: return "☀️"
    if code in (1, 2): return "⛅"
    if code == 3: return "☁️"
    if code in (45, 48): return "🌫️"
    if code in (95, 96, 99): return "⛈️"
    if code in (71, 73, 75, 77, 85, 86): return "❄️"
    return "🌧️"


def _wmo_description(code: int) -> str:
    descriptions = {
        0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
        45: "Foggy", 48: "Icy fog",
        51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle",
        61: "Light rain", 63: "Rain", 65: "Heavy rain",
        71: "Light snow", 73: "Snow", 75: "Heavy snow", 77: "Snow grains",
        80: "Showers", 81: "Rain showers", 82: "Heavy showers",
        85: "Snow showers", 86: "Heavy snow showers",
        95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Thunderstorm with hail",
    }
    return descriptions.get(code, "Unknown")


def _geocode(location_name: str) -> tuple[float, float, str]:
    """Geocode a location name to lat/lon using Open-Meteo's geocoding API."""
    r = requests.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": location_name, "count": 1, "language": "en", "format": "json"},
        timeout=10,
    )
    r.raise_for_status()
    results = r.json().get("results", [])
    if not results:
        raise RuntimeError(f"No geocoding results for '{location_name}'")
    result = results[0]
    return result["latitude"], result["longitude"], result.get("timezone", "auto")


def fetch_weather() -> list[dict]:
    """Fetch today's weather via Open-Meteo (free, no API key required)."""
    print("🌤️  Fetching weather...")
    results = []
    for loc in WEATHER_LOCATIONS:
        if not loc["query"]:
            results.append({"label": loc["label"], "location_icon": loc["icon"], "error": True})
            continue
        try:
            lat, lon, timezone = _geocode(loc["query"])
            r = requests.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m,apparent_temperature,weather_code",
                    "daily": "temperature_2m_max,temperature_2m_min",
                    "temperature_unit": "fahrenheit",
                    "timezone": timezone,
                    "forecast_days": 1,
                },
                timeout=10,
            )
            r.raise_for_status()
            data = r.json()
            current = data["current"]
            daily = data["daily"]
            code = current["weather_code"]
            results.append({
                "label": loc["label"],
                "location_icon": loc["icon"],
                "weather_icon": _wmo_icon(code),
                "condition": _wmo_description(code),
                "temp_f": str(round(current["temperature_2m"])),
                "feels_like_f": str(round(current["apparent_temperature"])),
                "high_f": str(round(daily["temperature_2m_max"][0])),
                "low_f": str(round(daily["temperature_2m_min"][0])),
            })
            print(f"  ✅ {loc['label']}: {round(current['temperature_2m'])}°F, {_wmo_description(code)}")
        except Exception as e:
            print(f"  ❌ Weather fetch failed for {loc['label']}: {e}")
            results.append({"label": loc["label"], "location_icon": loc["icon"], "error": True})
    return results


# ── NBA Scores ────────────────────────────────────────────────────────────
def fetch_nba_scores() -> list[dict]:
    """Fetch yesterday's completed NBA scores from ESPN's public API."""
    print("🏀 Fetching NBA scores...")
    yesterday = TODAY - datetime.timedelta(days=1)
    date_param = yesterday.strftime("%Y%m%d")
    try:
        r = requests.get(
            "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard",
            params={"dates": date_param},
            timeout=10,
        )
        r.raise_for_status()
        games = []
        for event in r.json().get("events", []):
            competition = event.get("competitions", [{}])[0]
            if not competition.get("status", {}).get("type", {}).get("completed"):
                continue
            competitors = competition.get("competitors", [])
            home = next((c for c in competitors if c["homeAway"] == "home"), None)
            away = next((c for c in competitors if c["homeAway"] == "away"), None)
            if not home or not away:
                continue
            away_score = int(away.get("score", 0))
            home_score = int(home.get("score", 0))
            games.append({
                "away_abbr": away["team"]["abbreviation"],
                "away_score": away_score,
                "home_abbr": home["team"]["abbreviation"],
                "home_score": home_score,
                "away_win": away_score > home_score,
            })
        if games:
            print(f"  ✅ {len(games)} NBA game(s) on {yesterday.strftime('%b %d')}")
        else:
            print(f"  ℹ️  No NBA games on {yesterday.strftime('%b %d')}")
        return games
    except Exception as e:
        print(f"  ❌ NBA scores fetch failed: {e}")
        return []


# ── Active Sports ──────────────────────────────────────────────────────────
def get_active_sports() -> str:
    """Return a string listing sports currently in season, based on the current month."""
    month = TODAY.month
    active = []
    if month in (10, 11, 12, 1, 2, 3, 4, 5, 6):
        active.append("NBA basketball")
    if month in (9, 10, 11, 12, 1, 2):
        active.append("NFL American football")
    if month in (8, 9, 10, 11, 12, 1, 2, 3, 4, 5):
        active.append("Premier League and European soccer")
    if month in (4, 5, 6, 7, 8, 9, 10):
        active.append("MLB baseball")
    if month in (10, 11, 12, 1, 2, 3, 4, 5, 6):
        active.append("NHL ice hockey")
    # Cricket: year-round; IPL runs April–May, WPL runs February–March
    cricket = "international cricket (pay special attention to Team India Men and Women matches)"
    if month in (2, 3):
        cricket += ", WPL (Women's Premier League)"
    if month in (4, 5):
        cricket += ", IPL (Indian Premier League)"
    active.append(cricket)
    return ", ".join(active)


# ── Deep Dive State ───────────────────────────────────────────────────────
def load_deep_dive_state() -> dict:
    """Load curated deep dive state from data/deep_dive_state.json."""
    state_path = Path("data/deep_dive_state.json")
    if not state_path.exists():
        print("  ⚠️  No deep_dive_state.json found — Deep Dive section will be empty")
        return {}
    return json.loads(state_path.read_text())


def save_deep_dive_state(state: dict) -> None:
    """Write updated deep dive state back to data/deep_dive_state.json."""
    state_path = Path("data/deep_dive_state.json")
    state_path.parent.mkdir(exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2))


def enrich_deep_dive_item(item: dict, item_type: str) -> dict:
    """On first appearance, generate a 1-2 sentence description and estimated time via web search."""
    if not item or item.get("description"):
        return item
    title = item.get("title", "Unknown")
    source = item.get("source", "Unknown")
    url = item.get("url", "")
    type_label = "longform article or essay" if item_type == "read" else "podcast episode"
    print(f"  ✨ Enriching {item_type}: {title}...")
    prompt = f"""Search for information about this {type_label} and return a brief description.

Title: {title}
Source: {source}
{"URL: " + url if url else ""}

Return JSON only:
{{
  "description": "1-2 sentence description of what this is about and why it is worth reading or listening to",
  "estimated_time": "e.g. '25 min read' or '2.5 hr listen'"
}}"""
    for attempt in range(3):
        try:
            response = client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=300,
                tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 2}],
                messages=[{"role": "user", "content": prompt}],
            )
            break
        except anthropic.RateLimitError as e:
            if attempt < 2:
                wait = int(e.response.headers.get("retry-after", 60))
                time.sleep(wait)
            else:
                raise
    text = ""
    for block in response.content:
        if block.type == "text":
            text += block.text
    try:
        json_match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
        if json_match:
            enriched = json.loads(json_match.group())
            item["description"] = enriched.get("description", "")
            item["estimated_time"] = enriched.get("estimated_time", "")
    except Exception as e:
        print(f"  ⚠️  Enrichment parsing failed: {e}")
    return item


# ── Step 1: Search for news ───────────────────────────────────────────────
def search_news() -> dict:
    """Use Claude with web search to gather today's news across all categories."""
    print("📡 Searching for today's news...")

    def source_list(category: str) -> str:
        return ", ".join(TRUSTED_SOURCES.get(category, []))

    explore_sources = ", ".join(SOURCES["explore_pool"])
    podcast_sources = ", ".join(SOURCES["podcasts"])
    active_sports = get_active_sports()

    search_queries = {
        "world": (
            f"top world politics news today {DATE_STR} "
            f"from {source_list('world')}"
        ),
        "india": (
            f"top India news politics business today {DATE_STR} "
            f"from {source_list('india')}"
        ),
        "tech": (
            f"top technology AI news today {DATE_STR} "
            f"from {source_list('tech')}"
        ),
        "business": (
            f"top business finance news today {DATE_STR} "
            f"from {source_list('business')}"
        ),
        "science": (
            f"top science health news today {DATE_STR} "
            f"from {source_list('science')}"
        ),
        "sports": (
            f"top sports news today {DATE_STR} — sports currently in season: {active_sports} "
            f"from {source_list('sports')}"
        ),
        "explore": (
            f"interesting long-form feature stories published in the past 2 weeks "
            f"from {explore_sources}"
        ),
    }

    source_instructions = {
        "world": (
            f"Search specifically for today's top world politics and international news "
            f"reported by these trusted outlets: {source_list('world')}. "
            f"Only return stories where the original reporting outlet is one of these sources. "
            f"Only include stories published on {DATE_STR} or {YESTERDAY_STR}. Ignore older stories even if they rank highly. "
            f"Do not use news aggregators, regional blogs, or unfamiliar outlets."
        ),
        "india": (
            f"Search specifically for today's top news from India — politics, economy, society, and foreign affairs — "
            f"reported by these trusted outlets: {source_list('india')}. "
            f"Only return stories where the original reporting outlet is one of these sources. "
            f"Only include stories published on {DATE_STR} or {YESTERDAY_STR}. Ignore older stories even if they rank highly. "
            f"Do not use news aggregators or unfamiliar regional outlets."
        ),
        "tech": (
            f"Search specifically for today's top technology and AI news "
            f"reported by these trusted outlets: {source_list('tech')}. "
            f"Only return stories where the original reporting outlet is one of these sources. "
            f"Only include stories published on {DATE_STR} or {YESTERDAY_STR}. Ignore older stories even if they rank highly. "
            f"Do not use news aggregators or secondary tech blogs."
        ),
        "business": (
            f"Search specifically for today's top business and finance news "
            f"reported by these trusted outlets: {source_list('business')}. "
            f"Only return stories where the original reporting outlet is one of these sources. "
            f"Only include stories published on {DATE_STR} or {YESTERDAY_STR}. Ignore older stories even if they rank highly. "
            f"Do not use news aggregators or investor blogs."
        ),
        "science": (
            f"Search specifically for today's top science and health news "
            f"reported by these trusted outlets: {source_list('science')}. "
            f"Only return stories where the original reporting outlet is one of these sources. "
            f"Only include stories published on {DATE_STR} or {YESTERDAY_STR}. Ignore older stories even if they rank highly. "
            f"Do not use aggregator sites like ScienceDaily — find the primary journal or specialist outlet."
        ),
        "sports": (
            f"Search specifically for today's top sports news — scores, results, transfers, and major stories — "
            f"reported by these trusted outlets: {source_list('sports')}. "
            f"Sports currently in season: {active_sports}. Prioritise coverage of these. "
            f"If any World Cup or major international tournament is currently active, include it. "
            f"Only include stories published on {DATE_STR} or {YESTERDAY_STR}. Ignore older stories even if they rank highly. "
            f"Only return stories where the original reporting outlet is one of these sources."
        ),
        "explore": (
            f"Search for interesting and thought-provoking long-form or feature stories published in the past 2 weeks "
            f"from these outlets: {explore_sources}. "
            f"Prioritise The Economist and New York Times — the reader subscribes to both and rarely has time to read long-form. "
            f"Surface their best essays, analysis, or features from the past 2 weeks first. "
            f"Fill remaining slots from the other outlets. "
            f"Also search for the top longform essays, blog posts, or papers trending on Hacker News in the past week — "
            f"surface the actual articles being linked, not Hacker News discussion pages. "
            f"These are the only acceptable sources for this section."
        ),
    }

    results = {}
    for category, query in search_queries.items():
        print(f"  🔍 Searching: {category}...")

        for attempt in range(3):
            try:
                response = client.messages.create(
                    model="claude-sonnet-4-5-20250929",
                    max_tokens=2000,
                    tools=[{
                        "type": "web_search_20250305",
                        "name": "web_search",
                        "max_uses": 5,
                    }],
                    messages=[{
                        "role": "user",
                        "content": f"""{source_instructions[category]}

Search query: {query}

Return the top 5 most important stories. For each story provide:
- headline (concise, informative)
- source_name (the specific outlet, e.g. "BBC", "Reuters" — not an aggregator)
- source_url (direct link to the article if available, otherwise the outlet's homepage)
- summary (2-3 sentences of substance, not just headline expansion)
- why_it_matters (1 sentence, only for the top 1-2 stories)
- approved (true if source is in the approved list, false if not)

Prefer approved outlets. If you find fewer than 3 stories from approved outlets, fill remaining slots with stories from other major reputable outlets (major newspapers, wire services, broadcasters) and mark approved as false. Do not use aggregators or blogs.

Format as JSON array. Only return the JSON, no other text."""
                    }],
                )
                break
            except anthropic.RateLimitError as e:
                if attempt < 2:
                    wait = int(e.response.headers.get("retry-after", 60))
                    print(f"  ⚠️  Rate limit hit for {category} (attempt {attempt + 1}/3) — waiting {wait}s...")
                    time.sleep(wait)
                else:
                    raise

        # Extract text from response
        text = ""
        for block in response.content:
            if block.type == "text":
                text += block.text

        results[category] = text
        print(f"  ✅ {category} done")
        time.sleep(10)  # Brief pause between categories to avoid rapid-fire token bursts

    return results


# ── Step 2: Synthesise into structured brief ──────────────────────────────
def synthesise_brief(raw_results: dict) -> dict:
    """Have Claude synthesise raw search results into a polished brief."""
    print("✍️  Synthesising brief...")

    subscriptions = ", ".join(SOURCES["subscriptions"])
    explore_sources = ", ".join(SOURCES["explore_pool"])

    trusted_by_category = "\n".join(
        f"- {cat.title()}: {', '.join(outlets)}"
        for cat, outlets in TRUSTED_SOURCES.items()
    )

    prompt = f"""You are writing The Daily Brief for {DAY_NAME}, {DATE_STR}.

Here are raw news search results by category:

WORLD & POLITICS:
{raw_results.get('world', 'No results')}

INDIA:
{raw_results.get('india', 'No results')}

TECH & AI:
{raw_results.get('tech', 'No results')}

BUSINESS & FINANCE:
{raw_results.get('business', 'No results')}

SCIENCE & HEALTH:
{raw_results.get('science', 'No results')}

SPORTS:
{raw_results.get('sports', 'No results')}

EXPLORE (discovery sources):
{raw_results.get('explore', 'No results')}

Write a synthesised daily brief. Cross-reference stories across sources for accuracy.
The reader subscribes to: {subscriptions} — mark these with "subscriber": true.

SOURCE QUALITY RULES — strictly enforced:
Only include stories from these approved outlets per section:
{trusted_by_category}
- Explore: {explore_sources}

If a story in the raw results comes from a news aggregator (e.g. ScienceDaily, Crescendo AI, News9live, MarketScreener, or any site that republishes others' reporting), you must either:
  a) Identify and cite the actual primary source (the journal, university, or original outlet), or
  b) Omit the story entirely.
Do not include stories where you cannot identify a reputable primary source. Fewer high-quality stories is better than padding with aggregator content.
If a section has fewer than 2 stories from approved outlets, include the most important stories from any major reputable outlet (major newspapers, wire services, broadcasters) to bring each section to at least 3 stories. Mark these with a note in the source name like "Additional: [Outlet Name]".

FRESHNESS RULE — strictly enforced:
Only include stories published on {DATE_STR} or {YESTERDAY_STR} (within the last 48 hours).
Exclude any story older than 48 hours, even if it is the only result for a category.
Events that concluded more than 2 days ago (tournament finals, concluded summits, closed negotiations) must not appear.
If a category genuinely has no fresh stories, return fewer stories rather than padding with stale ones.

Return ONLY valid JSON with this exact structure:
{{
  "summary": "One-sentence overview of the day's top 3 stories",
  "sections": [
    {{
      "id": "world",
      "name": "World & Politics",
      "badge_class": "world",
      "number": "01",
      "stories": [
        {{
          "headline": "...",
          "sources": [
            {{"name": "BBC", "url": "https://...", "subscriber": false}},
            {{"name": "The Economist", "url": "https://...", "subscriber": true}}
          ],
          "summary": "2-3 sentences of real substance",
          "why_it_matters": "1 sentence or null"
        }}
      ]
    }},
    {{
      "id": "india",
      "name": "India",
      "badge_class": "india",
      "number": "02",
      "stories": [...]
    }},
    {{
      "id": "tech",
      "name": "Tech & AI",
      "badge_class": "tech",
      "number": "03",
      "stories": [...]
    }},
    {{
      "id": "business",
      "name": "Business & Finance",
      "badge_class": "business",
      "number": "04",
      "stories": [...]
    }},
    {{
      "id": "science",
      "name": "Science & Health",
      "badge_class": "science",
      "number": "05",
      "stories": [...]
    }},
    {{
      "id": "sports",
      "name": "Sports",
      "badge_class": "sports",
      "number": "06",
      "stories": [...]
    }}
  ],
  "explore": {{
    "source_name": "WIRED or MIT Technology Review etc.",
    "source_description": "One sentence about this source",
    "stories": [
      {{
        "headline": "...",
        "source_name": "...",
        "source_url": "...",
        "summary": "..."
      }}
    ]
  }}
}}

Include 4-5 stories per news section and 2-3 explore stories.
Ensure all URLs are real and accurate. Do not invent URLs."""

    brief_data = None
    for attempt in range(3):
        try:
            response = client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=8000,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text if response.content else ""
            json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
            if json_match:
                text = json_match.group(1)
            if not text.strip():
                raise ValueError("empty response")
            brief_data = json.loads(text)
            break
        except (anthropic.RateLimitError, ValueError, json.JSONDecodeError) as e:
            if attempt < 2:
                if isinstance(e, anthropic.RateLimitError):
                    wait = int(e.response.headers.get("retry-after", 60))
                    print(f"  ⚠️  Rate limit hit during synthesis (attempt {attempt + 1}/3) — waiting {wait}s...")
                else:
                    print(f"  ⚠️  Bad response during synthesis (attempt {attempt + 1}/3): {e} — retrying in 30s...")
                    wait = 30
                time.sleep(wait)
            else:
                raise RuntimeError(f"synthesise_brief failed after 3 attempts: {e}") from e

    print("  ✅ Brief synthesised")
    return brief_data


# ── Step 3: Generate narration text ───────────────────────────────────────
def generate_narration(brief_data: dict) -> list[dict]:
    """Generate TTS-friendly narration text from brief data."""
    print("🎤 Generating narration text...")

    weather = brief_data.get("weather", [])
    weather_lines = []
    for w in weather:
        if not w.get("error"):
            weather_lines.append(
                f"{w['label']}: {w['temp_f']}°F, {w['condition']}, high {w['high_f']}°F, low {w['low_f']}°F"
            )
    weather_str = " / ".join(weather_lines) if weather_lines else ""

    prompt = f"""Convert this daily brief into a spoken narration script for a British English newsreader.

Brief data:
{json.dumps(brief_data, indent=2)}

Rules:
- Write numbers as words ("sixty-eight billion" not "68B")
- No abbreviations ("United States" not "US", except well-known ones like "AI")
- No contractions ("do not" not "don't", "here is" not "here's")
- Natural speech phrasing with good rhythm
- Include brief transitions between sections
- Open with "The Daily Brief. {DAY_NAME}, {DATE_STR}. Good morning." then add one natural sentence covering today's weather for both locations: {weather_str}
- Close with "That is your Daily Brief for {DAY_NAME}. Have a great day."
- Do NOT narrate the Deep Dive section — just the 4 news categories and Explore

Return a JSON array with exactly 8 objects:
[
  {{"label": "Introduction", "text": "..."}},
  {{"label": "World & Politics", "text": "..."}},
  {{"label": "India", "text": "..."}},
  {{"label": "Tech & AI", "text": "..."}},
  {{"label": "Business & Finance", "text": "..."}},
  {{"label": "Science & Health", "text": "..."}},
  {{"label": "Sports", "text": "..."}},
  {{"label": "Explore & Sign-off", "text": "..."}}
]

Return ONLY the JSON array."""

    sections = None
    for attempt in range(3):
        try:
            response = client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=6000,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text if response.content else ""
            json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
            if json_match:
                text = json_match.group(1)
            if not text.strip():
                raise ValueError("empty response")
            sections = json.loads(text)
            break
        except (anthropic.RateLimitError, ValueError, json.JSONDecodeError) as e:
            if attempt < 2:
                if isinstance(e, anthropic.RateLimitError):
                    wait = int(e.response.headers.get("retry-after", 60))
                    print(f"  ⚠️  Rate limit hit during narration (attempt {attempt + 1}/3) — waiting {wait}s...")
                else:
                    print(f"  ⚠️  Bad response during narration (attempt {attempt + 1}/3): {e} — retrying in 30s...")
                    wait = 30
                time.sleep(wait)
            else:
                raise RuntimeError(f"generate_narration failed after 3 attempts: {e}") from e
    print(f"  ✅ {len(sections)} narration sections generated")
    return sections


# ── Step 4: Generate audio via Deepgram ───────────────────────────────────
def _split_text(text: str, max_chars: int = 1900) -> list[str]:
    """Split text into chunks under max_chars, breaking at sentence boundaries."""
    if len(text) <= max_chars:
        return [text]
    chunks = []
    while text:
        if len(text) <= max_chars:
            chunks.append(text)
            break
        split_at = text.rfind(". ", 0, max_chars)
        if split_at == -1:
            split_at = text.rfind(" ", 0, max_chars)
        if split_at == -1:
            split_at = max_chars
        else:
            split_at += 1  # include the period
        chunks.append(text[:split_at].strip())
        text = text[split_at:].strip()
    return chunks


def _tts_request(text: str) -> bytes:
    """Send a single TTS request to Deepgram and return audio bytes."""
    response = requests.post(
        f"https://api.deepgram.com/v1/speak?model={DEEPGRAM_VOICE}",
        headers={
            "Authorization": f"Token {DEEPGRAM_API_KEY}",
            "Content-Type": "application/json",
        },
        json={"text": text},
    )
    if response.status_code != 200:
        raise RuntimeError(f"Deepgram API error ({response.status_code}): {response.text[:200]}")
    return response.content


def generate_audio(narration_sections: list[dict]) -> Path:
    """Call Deepgram TTS API for each narration section, stitch into one MP3."""
    print("🔊 Generating audio via Deepgram...")

    audio_chunks = []
    for i, section in enumerate(narration_sections):
        print(f"  🎵 Section {i+1}/{len(narration_sections)}: {section['label']}...")

        chunks = _split_text(section["text"])
        section_bytes = b""
        for chunk in chunks:
            section_bytes += _tts_request(chunk)

        audio_chunks.append(section_bytes)
        print(f"  ✅ {section['label']} done ({len(section_bytes)} bytes)")

    # Stitch MP3 chunks together
    mp3_path = OUTPUT_DIR / f"daily_brief_{DATE_FILE}.mp3"
    with open(mp3_path, "wb") as f:
        for chunk in audio_chunks:
            f.write(chunk)

    total_size = mp3_path.stat().st_size
    print(f"  ✅ Audio saved: {mp3_path} ({total_size / 1024 / 1024:.1f} MB)")
    return mp3_path


# ── Step 5: Render HTML ───────────────────────────────────────────────────
def render_html(brief_data: dict, narration_sections: list[dict], mp3_filename: str) -> Path:
    """Render the HTML brief from the Jinja2 template."""
    print("📄 Rendering HTML...")

    template_str = TEMPLATE_PATH.read_text()
    template = Template(template_str)

    html = template.render(
        date_str=DATE_STR,
        day_name=DAY_NAME,
        date_file=DATE_FILE,
        brief=brief_data,
        narration=narration_sections,
        mp3_filename=mp3_filename,
        sources=SOURCES,
        elevenlabs_api_key=None,  # No browser-side key needed — MP3 is pre-generated
    )

    html_path = OUTPUT_DIR / f"daily_brief_{DATE_FILE}.html"
    html_path.write_text(html)
    print(f"  ✅ HTML saved: {html_path}")
    return html_path


# ── Step 6: Generate email-safe HTML ──────────────────────────────────────
def generate_email_html(brief_data: dict, mp3_url: str) -> str:
    """Generate inline-styled email HTML programmatically from brief data."""
    print("📧 Generating email HTML...")

    ACCENT = "#1B4D3E"
    BADGE_COLORS = {
        "world": "#DC2626", "india": "#F97316", "tech": "#2563EB",
        "business": "#059669", "science": "#7C3AED",
        "sports": "#0EA5E9", "explore": "#D97706",
    }

    def badge(text, color):
        return (f'<span style="background:{color};color:#fff;padding:3px 10px;'
                f'border-radius:4px;font-size:11px;font-family:Arial,sans-serif;'
                f'font-weight:bold;text-transform:uppercase;letter-spacing:0.5px">{text}</span>')

    def render_story(story):
        sources_parts = []
        for s in story.get("sources", []):
            link = f'<a href="{s.get("url","")}" style="color:{ACCENT};text-decoration:none">{s["name"]}</a>'
            if s.get("subscriber"):
                link += (' <span style="background:#059669;color:#fff;padding:1px 5px;'
                         'border-radius:3px;font-size:9px;font-family:Arial">Sub</span>')
            sources_parts.append(link)
        sources_html = " · ".join(sources_parts)

        why = ""
        if story.get("why_it_matters"):
            why = (f'<div style="background:#f0fdf4;border-left:3px solid {ACCENT};'
                   f'padding:8px 12px;margin:8px 0;font-size:13px;font-family:Georgia,serif;'
                   f'color:#374151"><strong>Why it matters:</strong> {story["why_it_matters"]}</div>')

        return (f'<div style="margin-bottom:20px">'
                f'<h3 style="margin:0 0 4px;font-family:Georgia,serif;font-size:16px;color:#111">{story["headline"]}</h3>'
                f'<div style="font-size:12px;color:#6b7280;margin-bottom:8px;font-family:Arial">{sources_html}</div>'
                f'<p style="margin:0;font-family:Georgia,serif;font-size:14px;color:#374151;line-height:1.6">{story["summary"]}</p>'
                f'{why}</div>')

    # NBA scoreboard (injected at top of Sports section)
    def nba_scoreboard_html(scores):
        if not scores:
            return ""
        games_html = ""
        for g in scores:
            away = f"<strong>{g['away_abbr']} {g['away_score']}</strong>" if g["away_win"] else f"{g['away_abbr']} {g['away_score']}"
            home = f"<strong>{g['home_abbr']} {g['home_score']}</strong>" if not g["away_win"] else f"{g['home_abbr']} {g['home_score']}"
            games_html += (f'<span style="background:#fff;border-radius:4px;padding:4px 8px;'
                           f'font-family:Arial;font-size:12px;color:#1e293b;white-space:nowrap">'
                           f'{away} <span style="color:#94a3b8">@</span> {home}</span> ')
        return (f'<div style="margin-bottom:16px;padding:10px 12px;background:#EFF6FF;'
                f'border-radius:6px;border:1px solid #BFDBFE">'
                f'<div style="font-family:Arial;font-size:10px;font-weight:bold;color:#1E40AF;'
                f'text-transform:uppercase;letter-spacing:1px;margin-bottom:8px">🏀 NBA — Last Night</div>'
                f'<div style="display:flex;flex-wrap:wrap;gap:6px">{games_html}</div></div>')

    # News sections
    sections_html = ""
    for section in brief_data.get("sections", []):
        color = BADGE_COLORS.get(section["id"], "#6b7280")
        stories_html = "".join(render_story(s) for s in section.get("stories", []))
        scores_html = nba_scoreboard_html(brief_data.get("nba_scores", [])) if section["id"] == "sports" else ""
        sections_html += (f'<div style="margin-bottom:32px">'
                          f'<div style="margin-bottom:16px">{badge(section["name"], color)}</div>'
                          f'{scores_html}{stories_html}</div>')

    # Explore section
    explore = brief_data.get("explore", {})
    explore_html = ""
    if explore:
        explore_stories = ""
        for s in explore.get("stories", []):
            explore_stories += (f'<div style="margin-bottom:16px">'
                                f'<h3 style="margin:0 0 4px;font-family:Georgia,serif;font-size:15px;color:#111">'
                                f'<a href="{s.get("source_url","")}" style="color:#111;text-decoration:none">{s["headline"]}</a></h3>'
                                f'<p style="margin:0;font-family:Georgia,serif;font-size:13px;color:#374151;line-height:1.6">{s["summary"]}</p>'
                                f'</div>')
        explore_html = (f'<div style="margin-bottom:32px">'
                        f'<div style="margin-bottom:8px">{badge("Explore · " + explore.get("source_name",""), BADGE_COLORS["explore"])}</div>'
                        f'<p style="font-size:12px;color:#6b7280;font-family:Arial;margin:0 0 16px">{explore.get("source_description","")}</p>'
                        f'{explore_stories}</div>')

    # Deep Dive section
    deep_dive_html = ""
    dds = brief_data.get("deep_dive_state", {})
    if dds:
        def dd_email_item(icon, label, item, nudge=False):
            if not item:
                return ""
            days = item.get("days_shown", 1)
            day_str = f"Day {days}"
            if nudge and days >= 7:
                day_str += " — tell Leo when you finish to get your next item"
            title_html = (f'<a href="{item["url"]}" style="color:{ACCENT};text-decoration:none">{item["title"]}</a>'
                          if item.get("url") else item.get("title", ""))
            desc = f'<p style="margin:4px 0 0;font-size:13px;font-family:Georgia,serif;color:#374151">{item["description"]}</p>' if item.get("description") else ""
            time_str = f' · {item["estimated_time"]}' if item.get("estimated_time") else ""
            return (f'<div style="margin-bottom:12px;padding:12px;background:#f8fafc;border-radius:6px">'
                    f'<div style="font-size:11px;color:#6b7280;font-family:Arial;margin-bottom:4px">'
                    f'{icon} {label} · {day_str}{time_str}</div>'
                    f'<div style="font-size:14px;font-family:Georgia,serif;font-weight:bold">{title_html}</div>'
                    f'<div style="font-size:11px;color:#9ca3af;font-family:Arial">{item.get("source","")}</div>'
                    f'{desc}</div>')

        book_r = dds.get("current_book_read")
        book_l = dds.get("current_book_listen")
        book_html = ""
        if book_r:
            if book_l and book_r.get("title") == book_l.get("title"):
                book_html = (f'<div style="margin-bottom:12px;padding:12px;background:#f8fafc;border-radius:6px">'
                             f'<div style="font-size:11px;color:#6b7280;font-family:Arial;margin-bottom:4px">📚 Book — reading + listening</div>'
                             f'<div style="font-size:14px;font-family:Georgia,serif;font-weight:bold">{book_r["title"]}</div>'
                             f'<div style="font-size:12px;color:#9ca3af;font-family:Arial">{book_r.get("author","")}</div></div>')
            else:
                book_html = (f'<div style="margin-bottom:12px;padding:12px;background:#f8fafc;border-radius:6px">'
                             f'<div style="font-size:11px;color:#6b7280;font-family:Arial;margin-bottom:4px">📚 Book</div>'
                             f'<div style="font-size:13px;font-family:Georgia,serif"><strong>Reading:</strong> {book_r["title"]} · {book_r.get("author","")}</div>'
                             + (f'<div style="font-size:13px;font-family:Georgia,serif"><strong>Listening:</strong> {book_l["title"]} · {book_l.get("author","")}</div>' if book_l else "")
                             + f'</div>')

        items_html = (dd_email_item("📖", "Read", dds.get("current_read"), nudge=True)
                      + dd_email_item("🎙️", "Listen", dds.get("current_listen"), nudge=True)
                      + book_html)
        if items_html:
            deep_dive_html = (f'<div style="margin-bottom:32px">'
                              f'<div style="margin-bottom:16px">{badge("Deep Dive", "#0891B2")}</div>'
                              f'{items_html}</div>')

    # Weather card
    weather_html = ""
    weather_data = brief_data.get("weather", [])
    if weather_data:
        cells = ""
        for w in weather_data:
            if w.get("error"):
                cells += (f'<td style="width:50%;text-align:center;padding:8px 4px;'
                          f'font-family:Arial;font-size:12px;color:#9ca3af">'
                          f'{w["location_icon"]} {w["label"]}<br>Unavailable</td>')
            else:
                cells += (f'<td style="width:50%;text-align:center;padding:8px 4px">'
                          f'<div style="font-family:Arial;font-size:11px;color:#6b7280;margin-bottom:4px">'
                          f'{w["location_icon"]} {w["label"]}</div>'
                          f'<div style="font-size:22px;margin-bottom:2px">{w["weather_icon"]}</div>'
                          f'<div style="font-family:Arial;font-size:15px;font-weight:bold;color:#111">{w["temp_f"]}°F</div>'
                          f'<div style="font-family:Arial;font-size:11px;color:#6b7280;margin-bottom:2px">{w["condition"]}</div>'
                          f'<div style="font-family:Arial;font-size:11px;color:#9ca3af">H:{w["high_f"]}° / L:{w["low_f"]}°</div>'
                          f'</td>')
        weather_html = (f'<table width="100%" style="margin-bottom:24px;background:#f8fafc;'
                        f'border-radius:8px;border-collapse:collapse">'
                        f'<tr>{cells}</tr></table>')

    # Audio link
    audio_html = ""
    if mp3_url:
        audio_html = (f'<div style="margin-bottom:32px;padding:16px;background:#f0fdf4;'
                      f'border-radius:8px;text-align:center">'
                      f'<p style="margin:0 0 10px;font-family:Arial;font-size:13px;color:#374151">🎧 Listen to today\'s brief</p>'
                      f'<a href="{mp3_url}" style="background:{ACCENT};color:#fff;padding:10px 24px;'
                      f'border-radius:6px;text-decoration:none;font-family:Arial;font-size:14px;font-weight:bold">'
                      f'Download MP3</a>'
                      f'<p style="margin:8px 0 0;font-size:11px;color:#9ca3af;font-family:Arial">'
                      f'Audio may take a moment to become available after delivery.</p></div>')

    html = (f'<!DOCTYPE html><html><body style="margin:0;padding:0;background:#f9fafb">'
            f'<div style="max-width:600px;margin:0 auto;background:#fff;padding:32px 24px">'
            f'<div style="text-align:center;margin-bottom:24px;padding-bottom:24px;border-bottom:2px solid {ACCENT}">'
            f'<h1 style="margin:0 0 4px;font-family:Georgia,serif;font-size:28px;color:{ACCENT};letter-spacing:2px">THE DAILY BRIEF</h1>'
            f'<div style="font-family:Arial;font-size:13px;color:#6b7280">{DAY_NAME}, {DATE_STR}</div>'
            f'<p style="margin:12px 0 0;font-family:Georgia,serif;font-size:15px;color:#374151;font-style:italic">{brief_data.get("summary","")}</p>'
            f'</div>'
            f'{weather_html}{audio_html}{sections_html}{explore_html}{deep_dive_html}'
            f'<div style="text-align:center;padding-top:24px;border-top:1px solid #e5e7eb;'
            f'font-family:Arial;font-size:11px;color:#9ca3af">Curated for Nisha · {DAY_NAME}, {DATE_STR}</div>'
            f'</div></body></html>')

    print("  ✅ Email HTML generated")
    return html


# ── Step 7: Send email ────────────────────────────────────────────────────
def send_email(email_html: str) -> None:
    """Send the daily brief via Resend."""
    print("📬 Sending email...")

    response = requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "from": "The Daily Brief <today@brief.nisha-pillai.com>",
            "to": RECIPIENT_EMAILS,
            "subject": f"The Daily Brief — {DAY_NAME}, {DATE_STR}",
            "html": email_html,
        },
    )

    if response.status_code != 200:
        raise RuntimeError(f"Resend API error ({response.status_code}): {response.text[:200]}")

    print(f"  ✅ Email sent to {', '.join(RECIPIENT_EMAILS)}")


# ── Cleanup: delete briefs older than 7 days ──────────────────────────────
def cleanup_old_briefs(days: int = 7) -> None:
    """Delete HTML and MP3 brief files older than `days` days."""
    print(f"🧹 Cleaning up briefs older than {days} days...")
    cutoff = datetime.datetime.now() - datetime.timedelta(days=days)
    removed = 0
    for ext in ("*.html", "*.mp3"):
        for f in OUTPUT_DIR.glob(ext):
            if datetime.datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
                f.unlink()
                print(f"  🗑️  Removed {f.name}")
                removed += 1
    if removed == 0:
        print("  ✅ Nothing to clean up")


# ── Main pipeline ─────────────────────────────────────────────────────────
def main():
    print(f"\n{'='*60}")
    print(f"  THE DAILY BRIEF — {DAY_NAME}, {DATE_STR}")
    print(f"{'='*60}\n")

    # Step 0: Clean up old briefs, fetch weather and NBA scores
    cleanup_old_briefs()
    weather = fetch_weather()
    nba_scores = fetch_nba_scores()

    # Step 1: Search
    raw_results = search_news()

    # Step 2: Synthesise
    brief_data = synthesise_brief(raw_results)
    brief_data["weather"] = weather
    brief_data["nba_scores"] = nba_scores

    # Step 2b: Load and enrich deep dive state
    print("📚 Loading deep dive state...")
    deep_dive_state = load_deep_dive_state()
    if deep_dive_state:
        if deep_dive_state.get("current_read") and not deep_dive_state["current_read"].get("description"):
            deep_dive_state["current_read"] = enrich_deep_dive_item(deep_dive_state["current_read"], "read")
        if deep_dive_state.get("current_listen") and not deep_dive_state["current_listen"].get("description"):
            deep_dive_state["current_listen"] = enrich_deep_dive_item(deep_dive_state["current_listen"], "listen")
        for key in ("current_read", "current_listen"):
            item = deep_dive_state.get(key)
            if item and item.get("first_shown"):
                first = datetime.date.fromisoformat(item["first_shown"])
                item["days_shown"] = (TODAY - first).days + 1
        save_deep_dive_state(deep_dive_state)
        print("  ✅ Deep dive state ready")
    brief_data["deep_dive_state"] = deep_dive_state

    # Save raw data for debugging
    data_path = OUTPUT_DIR / f"daily_brief_{DATE_FILE}.json"
    data_path.write_text(json.dumps(brief_data, indent=2))
    print(f"  💾 Data saved: {data_path}")

    # Step 3: Generate narration
    narration_sections = generate_narration(brief_data)

    # Step 4: Generate audio
    mp3_path = generate_audio(narration_sections)

    # Step 5: Render HTML
    html_path = render_html(brief_data, narration_sections, mp3_path.name)

    # Step 6: Generate email HTML (programmatic, no API call)
    mp3_url = f"https://raw.githubusercontent.com/n-pillai/daily-brief/main/briefs/{mp3_path.name}"
    email_html = generate_email_html(brief_data, mp3_url)

    # Step 7: Send email
    send_email(email_html)

    print(f"\n{'='*60}")
    print(f"  ✅ BRIEF COMPLETE")
    print(f"  📄 HTML:  {html_path}")
    print(f"  🔊 Audio: {mp3_path}")
    print(f"  💾 Data:  {data_path}")
    print(f"{'='*60}\n")

    return {
        "html_path": str(html_path),
        "mp3_path": str(mp3_path),
        "date": DATE_FILE,
    }


if __name__ == "__main__":
    main()
