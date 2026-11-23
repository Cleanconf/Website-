# OSO dashboard automation

## How this works, in plain English

Every morning at 06:00 UK time, a small program wakes up and:

1. Asks Stripe for yesterday's money numbers (revenue, new paying customers, cancellations and why, failed payments).
2. Asks PostHog (the app's analytics) for yesterday's trial sign-ups and website click-throughs.
3. Asks Google Analytics for yesterday's website visitor numbers.
4. Saves all of that, and works out how it compares to the day before, the same day last week, and the same point last month.
5. Checks whether anything moved more than 15% away from its normal level over the last week.
6. If anything did, and a Claude (Anthropic) key has been set up, asks Claude to turn that into 3 plain-English suggestions. If not, it just says "no suggestions yet" rather than guessing.
7. Posts a short message to Slack with the headline numbers and those suggestions.

It saves everything as plain files in `data/` in this folder, committed back into this repository each day - no database, nothing else to pay for or manage.

It runs on GitHub's own servers (via a GitHub Actions workflow, `.github/workflows/dashboard-daily.yml`), not on anyone's laptop, so it runs every morning whether or not anyone's computer is switched on.

## Setup

### 1. Install locally (only needed to test on your own machine)

```sh
cd dashboard-automation
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

### 2. Secrets

These are set once in this GitHub repository's **Settings -> Secrets and variables -> Actions**, not in any file:

| Secret | What it is | Where to get it |
| --- | --- | --- |
| `STRIPE_DASHBOARD_KEY` | A **restricted, read-only** Stripe key | Stripe Dashboard -> Developers -> API keys -> "Create restricted key", read-only on Customers, Subscriptions, Charges, Invoices, Payment Intents, Disputes |
| `POSTHOG_API_KEY` | A PostHog personal API key, ideally scoped read-only | PostHog -> Settings -> Personal API keys |
| `POSTHOG_PROJECT_ID` | The PostHog project ID holding real app traffic | The number in the PostHog project URL (currently `265973`) |
| `GA4_PROPERTY_ID` | The GA4 property's numeric ID | GA4 Admin -> Property Settings -> Property details (not the `G-...` measurement ID) |
| `GA4_SERVICE_ACCOUNT_JSON` | A Google service account key (the whole JSON file, as one line) | Google Cloud Console -> IAM & Admin -> Service Accounts -> create one -> Keys -> Add key (JSON). Then add that service account's email as a **Viewer** in GA4 Admin -> Property Access Management |
| `SLACK_BOT_TOKEN` | The existing "OSO Content Review" Slack bot token (reused from the content automation) | Already in `automation/.env` locally - copy the same value in as a GitHub secret. Invite the bot to the dashboard Slack channel: `/invite @OSO Content Review` |
| `SLACK_CHANNEL_ID` | The Slack channel ID for `#daily-dashboard-metrics` | Right-click the channel in Slack -> View channel details -> copy the Channel ID at the bottom |
| `ANTHROPIC_API_KEY` | Optional. Without it, the job runs fine and just skips the "3 suggestions" step | console.anthropic.com -> Settings -> API Keys |

**GA4 timezone**: double check in GA4 Admin -> Property Settings that the property's reporting timezone is set to UK/London - otherwise the daily figures will be pulled for the wrong hours.

### 3. Backfill

Use the "Run workflow" button on the `Daily dashboard` workflow in the Actions tab, filling in `from_date` and `to_date`. Note Stripe's event history only reaches back about 30 days - an older backfill will come back with zeros for Stripe, not an error.

### 4. Dry run

Tick "dry_run" when running the workflow manually. It builds everything and logs what the Slack message would say, without actually posting it - good for checking a change looks right first.

### 5. Troubleshooting

- **A source is marked "stale" in Slack**: that source's API call failed (timeout, bad key, etc.) - check that day's run output in the Actions tab for the actual error. The dashboard falls back to the last successful day's figures rather than showing a blank.
- **Numbers look off by a few hours**: almost always the GA4 property's timezone setting (see above).
- **Nothing posted at all**: check the `Check it is 06:00 in London` step in the Actions tab - on each day two scheduled runs fire (05:00 and 06:00 UTC, to cover both BST and GMT), and exactly one of them is supposed to be skipped. If both were skipped, something's wrong with that time check.
- **Re-running a day that already ran**: by default the job skips a day it's already successfully fetched, so re-running is harmless. Pass `force` to make it re-fetch and overwrite.

## Tests

```sh
cd dashboard-automation
./venv/bin/pytest
```

Covers the date/timezone logic (including the March and October clock changes and month-end comparisons), the rollup and flagging rules, and the Slack message formatting.
