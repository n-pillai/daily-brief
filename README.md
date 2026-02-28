# The Daily Brief

Automated daily news briefing with AI synthesis and audio narration, delivered to your inbox every morning.

## What it does

1. **Searches** today's news across trusted sources (Economist, NYT, BBC, TechCrunch, Stratechery, TLDR)
2. **Synthesises** stories via Claude — cross-referencing across outlets, categorising into World & Politics, Tech & AI, Business & Finance, Science & Health
3. **Curates** an Explore section (rotating discovery sources) and Deep Dive section (podcasts, long reads)
4. **Narrates** the brief in British English via Deepgram Aura, producing an MP3
5. **Emails** the HTML brief to your inbox via Resend

## Setup

### 1. Fork or clone this repo

Keep the repo private if you don't want your daily brief content public.

### 2. Add secrets

Go to **Settings → Secrets and variables → Actions** and add:

| Secret | Value |
|--------|-------|
| `ANTHROPIC_API_KEY` | Your Anthropic API key |
| `DEEPGRAM_API_KEY` | Your Deepgram API key |
| `RESEND_API_KEY` | Your Resend API key |
| `RECIPIENT_EMAIL` | Email address to deliver the brief to |

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

The brief will arrive in your inbox within a few minutes.

## Output

Each run produces and emails:

- A structured HTML brief with stories across 4 categories, an Explore section, and a Deep Dive section
- An MP3 audio narration (~10–15 minutes)

Generated files are not committed to the repo — the brief is delivered via email only.

## Costs

- **Anthropic API**: ~$0.10–0.30/day (Claude Sonnet with web search)
- **Deepgram**: ~$0.01–0.05/day (Aura TTS, pay-per-character)
- **Resend**: free tier (3,000 emails/month)
- **GitHub Actions**: free tier (well under 2,000 min/month)

Total: roughly **$3–10/month**.
