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
from anthropic import Anthropic
from jinja2 import Template

# ── Configuration ──────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
DEEPGRAM_API_KEY = os.environ["DEEPGRAM_API_KEY"]
DEEPGRAM_VOICE = "aura-helios-en"  # British male

TODAY = datetime.date.today()
DATE_STR = TODAY.strftime("%B %d, %Y")         # February 28, 2026
DATE_FILE = TODAY.strftime("%Y-%m-%d")          # 2026-02-28
DAY_NAME = TODAY.strftime("%A")                 # Friday

OUTPUT_DIR = Path("briefs")
OUTPUT_DIR.mkdir(exist_ok=True)

TEMPLATE_PATH = Path("templates/brief_template.html")

# ── Trusted sources and preferences ────────────────────────────────────────
SOURCES = {
    "core": ["The Economist", "NYT", "BBC", "TechCrunch", "Stratechery", "AI Daily Brief", "TLDR"],
    "subscriptions": ["The Economist", "NYT", "Lenny's Newsletter"],
    "explore_pool": ["WIRED", "MIT Technology Review", "Ars Technica", "The Verge", "Aeon", "Quanta Magazine"],
    "podcasts": ["Lenny's Podcast", "AI Daily Brief", "Acquired", "The Journal (WSJ)"],
}

CATEGORIES = [
    {"id": "world", "name": "World & Politics", "badge_class": "world", "number": "01"},
    {"id": "tech", "name": "Tech & AI", "badge_class": "tech", "number": "02"},
    {"id": "business", "name": "Business & Finance", "badge_class": "business", "number": "03"},
    {"id": "science", "name": "Science & Health", "badge_class": "science", "number": "04"},
]

client = Anthropic(api_key=ANTHROPIC_API_KEY)


# ── Step 1: Search for news ───────────────────────────────────────────────
def search_news() -> dict:
    """Use Claude with web search to gather today's news across all categories."""
    print("📡 Searching for today's news...")

    search_queries = {
        "world": f"top world politics news today {DATE_STR}",
        "tech": f"top technology AI news today {DATE_STR}",
        "business": f"top business finance news today {DATE_STR}",
        "science": f"top science health news today {DATE_STR}",
        "explore": f"interesting stories WIRED MIT Technology Review today {DATE_STR}",
        "deepdive": f"new podcast episodes Lenny's Podcast AI Daily Brief Acquired The Journal WSJ {DATE_STR}",
    }

    results = {}
    for category, query in search_queries.items():
        print(f"  🔍 Searching: {category}...")
        response = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=2000,
            tools=[{
                "type": "web_search_20250305",
                "name": "web_search",
                "max_uses": 2,
            }],
            messages=[{
                "role": "user",
                "content": f"""Search for: {query}

Return the top 5 most important stories. For each story provide:
- headline (concise, informative)
- source_name (which outlet reported it)
- source_url (direct link if available, otherwise outlet homepage)
- summary (2-3 sentences of substance, not just headline expansion)
- why_it_matters (1 sentence, only for the top 1-2 stories)

Format as JSON array. Only return the JSON, no other text."""
            }],
        )

        # Extract text from response
        text = ""
        for block in response.content:
            if block.type == "text":
                text += block.text

        results[category] = text
        print(f"  ✅ {category} done")
        time.sleep(15)  # Stay within 30k TPM rate limit

    return results


# ── Step 2: Synthesise into structured brief ──────────────────────────────
def synthesise_brief(raw_results: dict) -> dict:
    """Have Claude synthesise raw search results into a polished brief."""
    print("✍️  Synthesising brief...")

    subscriptions = ", ".join(SOURCES["subscriptions"])
    explore_sources = ", ".join(SOURCES["explore_pool"])

    prompt = f"""You are writing The Daily Brief for {DAY_NAME}, {DATE_STR}.

Here are raw news search results by category:

WORLD & POLITICS:
{raw_results.get('world', 'No results')}

TECH & AI:
{raw_results.get('tech', 'No results')}

BUSINESS & FINANCE:
{raw_results.get('business', 'No results')}

SCIENCE & HEALTH:
{raw_results.get('science', 'No results')}

EXPLORE (discovery sources):
{raw_results.get('explore', 'No results')}

DEEP DIVE (podcasts/long reads):
{raw_results.get('deepdive', 'No results')}

Write a synthesised daily brief. Cross-reference stories across sources for accuracy.
The reader subscribes to: {subscriptions} — mark these with "subscriber": true.

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
      "id": "tech",
      "name": "Tech & AI",
      "badge_class": "tech",
      "number": "02",
      "stories": [...]
    }},
    {{
      "id": "business",
      "name": "Business & Finance",
      "badge_class": "business",
      "number": "03",
      "stories": [...]
    }},
    {{
      "id": "science",
      "name": "Science & Health",
      "badge_class": "science",
      "number": "04",
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
  }},
  "deep_dive": [
    {{
      "type": "podcast|audiobook|longread",
      "icon": "🎙️ or 📖 or 📰",
      "title": "...",
      "url": "...",
      "meta": "62 min · Released Feb 27",
      "description": "...",
      "subscriber": false,
      "tag_label": "New Episode"
    }}
  ]
}}

Include 4-5 stories per news section, 2-3 explore stories, and 5-7 deep dive items.
Ensure all URLs are real and accurate. Do not invent URLs."""

    response = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=8000,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text

    # Extract JSON from response (handle markdown code blocks)
    json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if json_match:
        text = json_match.group(1)

    brief_data = json.loads(text)
    print("  ✅ Brief synthesised")
    return brief_data


# ── Step 3: Generate narration text ───────────────────────────────────────
def generate_narration(brief_data: dict) -> list[dict]:
    """Generate TTS-friendly narration text from brief data."""
    print("🎤 Generating narration text...")

    prompt = f"""Convert this daily brief into a spoken narration script for a British English newsreader.

Brief data:
{json.dumps(brief_data, indent=2)}

Rules:
- Write numbers as words ("sixty-eight billion" not "68B")
- No abbreviations ("United States" not "US", except well-known ones like "AI")
- No contractions ("do not" not "don't", "here is" not "here's")
- Natural speech phrasing with good rhythm
- Include brief transitions between sections
- Open with "The Daily Brief. {DAY_NAME}, {DATE_STR}. Good morning."
- Close with "That is your Daily Brief for {DAY_NAME}. Have a great day."
- Do NOT narrate the Deep Dive section — just the 4 news categories and Explore

Return a JSON array with exactly 6 objects:
[
  {{"label": "Introduction", "text": "..."}},
  {{"label": "World & Politics", "text": "..."}},
  {{"label": "Tech & AI", "text": "..."}},
  {{"label": "Business & Finance", "text": "..."}},
  {{"label": "Science & Health", "text": "..."}},
  {{"label": "Explore & Sign-off", "text": "..."}}
]

Return ONLY the JSON array."""

    response = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=6000,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text
    json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if json_match:
        text = json_match.group(1)

    sections = json.loads(text)
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
def generate_email_html(brief_data: dict) -> str:
    """Generate a simplified inline-styled HTML version for email."""
    print("📧 Generating email HTML...")

    prompt = f"""Convert this daily brief data into a clean, email-safe HTML document.

Brief data:
{json.dumps(brief_data, indent=2)}

Requirements:
- ALL styles must be inline (no <style> tags — email clients strip them)
- Max width 600px, centered
- Use web-safe fonts: Georgia for body, Arial/Helvetica for UI elements
- Color scheme: accent=#1B4D3E, world=#DC2626, tech=#2563EB, business=#059669, science=#7C3AED, explore=#D97706, deepdive=#0891B2
- Include the header: "THE DAILY BRIEF" brand, date, summary
- Include all sections with colored badges, story headlines (as links), sources, summaries, "why it matters" boxes
- Mark subscriber sources with a small green "Subscriber" badge
- Include Explore and Deep Dive sections
- Footer: "Curated for Nisha · Generated at 6:00 AM · {DAY_NAME}, {DATE_STR}"
- Keep it clean and readable — this is a premium newsletter aesthetic

Return ONLY the complete HTML document, no markdown code fences."""

    response = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=8000,
        messages=[{"role": "user", "content": prompt}],
    )

    html = response.content[0].text
    # Strip markdown fences if present
    if html.startswith("```"):
        html = re.sub(r'^```(?:html)?\s*\n?', '', html)
        html = re.sub(r'\n?```\s*$', '', html)

    print("  ✅ Email HTML generated")
    return html


# ── Main pipeline ─────────────────────────────────────────────────────────
def main():
    print(f"\n{'='*60}")
    print(f"  THE DAILY BRIEF — {DAY_NAME}, {DATE_STR}")
    print(f"{'='*60}\n")

    # Step 1: Search
    raw_results = search_news()

    # Step 2: Synthesise
    brief_data = synthesise_brief(raw_results)

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

    # Step 6: Generate email HTML
    email_html = generate_email_html(brief_data)
    email_path = OUTPUT_DIR / f"daily_brief_{DATE_FILE}_email.html"
    email_path.write_text(email_html)
    print(f"  📧 Email HTML saved: {email_path}")

    print(f"\n{'='*60}")
    print(f"  ✅ BRIEF COMPLETE")
    print(f"  📄 HTML:  {html_path}")
    print(f"  🔊 Audio: {mp3_path}")
    print(f"  📧 Email: {email_path}")
    print(f"  💾 Data:  {data_path}")
    print(f"{'='*60}\n")

    return {
        "html_path": str(html_path),
        "mp3_path": str(mp3_path),
        "email_html": email_html,
        "date": DATE_FILE,
    }


if __name__ == "__main__":
    main()
