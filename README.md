# The Daily Brief

Automated daily news briefing with AI synthesis, weather, and audio narration, delivered to your inbox every morning.

## What it does

1. **Weather** — fetches current conditions and forecast for up to two locations
2. **Searches** today's news via Claude with web search across World & Politics, India, Tech & AI, Business & Finance, Science & Health, and Sports — pulling only from a curated list of trusted outlets per section. Sports coverage is seasonally aware (tracks what's currently in season, with a focus on Team India, IPL, and WPL)
3. **Synthesises** stories — cross-referencing across outlets, flagging subscriber sources
4. **Surfaces an Explore section** — longform articles and features from a broader pool (WIRED, Quanta, Hacker News, Aeon, MIT Technology Review, and others), prioritising paid subscriptions
5. **Tracks a Deep Dive queue** — a persistent curated backlog of one longform read and one podcast episode, each shown with a day counter so you know how long it's been queued. Also tracks your current book. Items are managed externally and synced in; a nudge appears after Day 7
6. **Shows yesterday's NBA scores** via the ESPN public API
7. **Narrates** the brief via Deepgram Aura in your chosen voice, producing an MP3
8. **Emails** the HTML brief to one or more recipients via Resend
9. **Saves** the HTML and MP3 to the repo for 7 days, then auto-cleans up

## Setup

### 1. Fork or clone this repo

### 2. Add secrets

Go to **Settings → Secrets and variables → Actions** and add:

| Secret | Value |
|--------|-------|
| `ANTHROPIC_API_KEY` | Your Anthropic API key |
| `DEEPGRAM_API_KEY` | Your Deepgram API key |
| `RESEND_API_KEY` | Your Resend API key |
| `RECIPIENT_EMAILS` | Comma-separated list of recipient email addresses |
| `WEATHER_LOCATION_HOME` | Home location for weather (e.g. `London`) |
| `WEATHER_LOCATION_WORK` | Work location for weather (e.g. `New+York`) |

### 3. Verify a sender domain in Resend

Go to [resend.com/domains](https://resend.com/domains) and verify a domain you own. Then update the `from` address in `generate_brief.py`:

```python
"from": "The Daily Brief <today@your-domain.com>",
```

Without a verified domain, Resend will only deliver to the email address on your Resend account.

### 4. Set your timezone and schedule

The workflow runs **every hour**. The Python script checks the current UTC time and only generates the brief at 6 AM in your local timezone — no manual cron editing required.

**Default timezone:** Pacific (`America/Los_Angeles`). To change it, edit `DEFAULT_TIMEZONE` and `TARGET_LOCAL_HOUR` at the top of `generate_brief.py`.

**Travel detection (optional):** Add a `CALENDAR_ICS_URL` secret pointing to a private Google Calendar ICS feed. When a multi-day event is found on your calendar today, the script reads the event's location or timezone and automatically shifts delivery to 6 AM at that destination. No changes needed when you travel — just keep your calendar up to date.

| Secret | Value |
|--------|-------|
| `CALENDAR_ICS_URL` | Google Calendar → Settings → your calendar → "Secret address in iCal format" |

### 5. Customise your sources

Edit `config.json` to set your trusted sources per news section, subscriptions, explore pool, and podcast sources. Subscriber sources are flagged in the brief. The trusted source lists control which outlets Claude is directed to search and synthesise from.

### 6. Initialise the Deep Dive queue

The brief tracks a persistent read/listen/book queue in `data/deep_dive_state.json`. This file is committed to the repo and updated on every run. Edit it to set your starting items:

```json
{
  "current_read":  { "title": "...", "url": "...", "source": "...", "first_shown": "YYYY-MM-DD", "description": null, "estimated_time": null },
  "current_listen": { "title": "...", "url": null,  "source": "...", "first_shown": "YYYY-MM-DD", "description": null, "estimated_time": null },
  "current_book_read":   { "title": "...", "author": "..." },
  "current_book_listen": { "title": "...", "author": "..." },
  "last_synced": "YYYY-MM-DD"
}
```

Leave `description` and `estimated_time` as `null` — Claude will enrich them on first run.

### 7. Run it

Either wait for the cron, or trigger manually:
**Actions → Daily Brief → Run workflow**

The brief will arrive in your inbox within about 7 minutes.

## Output

Each run produces and emails:

- A structured HTML brief with weather, stories across 6 news sections (World & Politics, India, Tech & AI, Business & Finance, Science & Health, Sports), an Explore section, and a Deep Dive section (curated read, listen, and current book)
- An MP3 audio narration of the six news sections and the Explore segment (Deep Dive is email-only)

The HTML and MP3 are committed to `briefs/` in the repo and automatically deleted after 7 days.

## Costs

There are small API costs across Claude, Deepgram, and Resend. GitHub Actions is free for public repositories.
