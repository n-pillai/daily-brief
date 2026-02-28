# The Daily Brief

Automated daily news briefing with AI synthesis and audio narration.

Generates a curated HTML brief + MP3 audio file every morning at 6 AM via GitHub Actions.

## What it does

1. **Searches** today's news across trusted sources (Economist, NYT, BBC, TechCrunch, Stratechery, TLDR)
2. **Synthesises** stories via Claude — cross-referencing across outlets, categorising into World & Politics, Tech & AI, Business & Finance, Science & Health
3. **Curates** an Explore section (rotating discovery sources) and Deep Dive section (podcasts, long reads)
4. **Narrates** the brief in British English via ElevenLabs, producing an MP3
5. **Commits** the HTML + MP3 to `briefs/` daily

## Setup

### 1. Create a private GitHub repo

Push this folder to a new private repo on GitHub.

### 2. Add secrets

Go to **Settings → Secrets and variables → Actions** and add:

| Secret | Value |
|--------|-------|
| `ANTHROPIC_API_KEY` | Your Anthropic API key |
| `ELEVENLABS_API_KEY` | Your ElevenLabs API key |

### 3. Adjust the schedule

Edit `.github/workflows/daily-brief.yml` and change the cron to match your timezone:

```yaml
# 6 AM London (GMT): "0 6 * * *"
# 6 AM New York (EST): "0 11 * * *"
# 6 AM Mumbai (IST): "30 0 * * *"
```

### 4. Run it

Either wait for the cron, or trigger manually:
**Actions → Daily Brief → Run workflow**

## Reading your brief

Browse to `briefs/` in your repo. Each day produces:

- `daily_brief_YYYY-MM-DD.html` — the full brief (open in browser)
- `daily_brief_YYYY-MM-DD.mp3` — audio narration
- `daily_brief_YYYY-MM-DD.json` — raw data (for debugging)
- `daily_brief_YYYY-MM-DD_email.html` — email-safe version

Tip: use GitHub Pages on the `briefs/` folder for a nice browsable archive.

## Costs

- **Anthropic API**: ~$0.10–0.30/day (Claude Sonnet, web search)
- **ElevenLabs**: ~$0.15–0.30/day (~5,000 characters of narration)
- **GitHub Actions**: free tier (well under 2,000 min/month)

Total: roughly **$5–15/month**.
