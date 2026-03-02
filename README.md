# The Daily Brief

Automated daily news briefing with AI synthesis, weather, and audio narration, delivered to your inbox every morning.

## What it does

1. **Weather** — fetches current conditions and forecast for up to two locations
2. **Searches** today's news via Claude with web search across World & Politics, Tech & AI, Business & Finance, Science & Health, Explore, and Deep Dive (podcasts & long reads)
3. **Synthesises** stories — cross-referencing across outlets, flagging subscriber sources
4. **Narrates** the brief in British English via Deepgram Aura, producing an MP3
5. **Emails** the HTML brief to one or more recipients via Resend
6. **Saves** the HTML and MP3 to the repo for 7 days, then auto-cleans up

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

### 4. Adjust the schedule

Edit `.github/workflows/daily-brief.yml` and change the cron to match your timezone:

```yaml
# 6 AM London (GMT):   "0 6 * * *"
# 6 AM New York (EST): "0 11 * * *"
# 6 AM Mumbai (IST):   "30 0 * * *"
```

### 5. Customise your sources

Edit `config.json` to set your subscriptions, explore pool, and podcast sources. Subscriber sources are flagged in the brief.

### 6. Run it

Either wait for the cron, or trigger manually:
**Actions → Daily Brief → Run workflow**

The brief will arrive in your inbox within about 7 minutes.

## Output

Each run produces and emails:

- A structured HTML brief with weather, stories across 4 news categories, an Explore section, and a Deep Dive section
- An MP3 audio narration of the news sections

The HTML and MP3 are committed to `briefs/` in the repo and automatically deleted after 7 days.

## Costs

- **Anthropic API**: ~$0.10–0.30/day (Claude Sonnet with web search)
- **Deepgram**: ~$0.01–0.05/day (Aura TTS, pay-per-character)
- **Resend**: free tier (3,000 emails/month)
- **GitHub Actions**: free tier (well under 2,000 min/month)

Total: roughly **$3–10/month**.
