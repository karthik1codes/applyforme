# applyforme

Agentic job-application pipeline with a Next.js dashboard. State lives in one SQLite file (`data/applyforme.db`) shared by the Python agents and the dashboard.

| # | Stage | Command | What happens |
|---|-------|---------|--------------|
| 1 | Discover | `discover` | Greenhouse / Lever / Ashby public APIs; optional Indeed/LinkedIn/Glassdoor/ZipRecruiter/Google via JobSpy (`searches:` in profile) |
| 2 | Enrich | `enrich` | Full description: JSON-LD -> page text -> LLM extraction |
| 3 | Score | `match` | LLM scores 0-100 vs your profile; below `min_match_score` is skipped |
| 4 | Tailor resume | `tailor` | Per-job **PDF** (uploaded to the form) and **LaTeX** (Overleaf). Reorders/rewords only; code-validated so employers, titles, dates, skills and numbers can't be invented |
| 5 | Cover letter | `tailor` | Grounded in your profile |
| 6 | Apply | `apply` | Playwright fills the form. Unknown *required* questions are saved to the dashboard instead of guessed; you approve every submit |

`run` = stages 1-5. `inbox` = pull employer replies (IMAP, read-only). `dashboard` = start the web UI.

## Setup
```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m playwright install chromium
.venv\Scripts\python -m applyforme init      # creates profile.yaml + .env
```
Put `OPENAI_API_KEY` in `.env`, drop your resume (`resume.pdf`) next to it, then build your profile from it:
```powershell
.venv\Scripts\python -m applyforme setup --resume resume.pdf
```
The wizard reads your resume (the LLM only transcribes, it never adds anything), then asks you to confirm contact details, salary range, notice period, target titles, accepted locations and locations to reject. It writes `profile.yaml` and backs up the previous one. (Prefer hand-editing? `init` copies the annotated example.) The first `dashboard` run installs the web dependencies.

## Safety nets (what keeps output honest)
- **Resume**: employers, titles, dates, skills and every number are checked against your profile; a second LLM "judge" pass looks for invented work (`APPLYFORME_JUDGE=0` turns it off). Any violation falls back to your original content.
- **Cover letter**: length, leaked assistant phrasing, `[Placeholders]` and typographic tells are checked; failures are regenerated from a fresh prompt up to 3 times, and the job stays un-tailored if it never passes.
- **Submit verification**: `applied` is only recorded when a confirmation page/message is detected. Otherwise the job becomes `failed` with the reason (validation errors, or "no confirmation seen - check your email") so it can't be double-submitted.
- **Apply manually**: SSO sign-in walls and account-wall portals (Workday, iCIMS, Taleo, SuccessFactors, ...) are routed to **Apply manually** with your tailored resume ready, instead of failing. Closed postings are skipped.
- **Location filter**: `reject_locations` drops "Remote (US only)" style roles unless the posting also names a place you accept.
- **Seniority filter**: `preferences.seniority_level: junior` drops Senior/Staff/Principal/Lead/Manager titles before scoring; the matcher also hard-fails mismatches.
- **Workday**: add employers under `sources.workday` in `profile.yaml` (see the example) to discover from their public JSON search.

## Onboarding (dashboard)
Open http://localhost:3000 → sign in (or local mode) → **Onboarding** asks for:
1. Resume upload  
2. Background (current title, **seniority level**, years, target titles, skills)  
3. Social links (LinkedIn, GitHub, portfolio, website, X)  
4. Locations / salary / work auth  

That writes `profile.yaml` (`onboarding_complete: true`). Agents read it on every run. **Junior** seniority automatically blocks Senior / Staff / Principal / Lead / Director / Manager titles in discovery and scoring. Change anytime under **Preferences** or `/onboarding?force=1`.

## Keeping agents live on EC2 (webhooks + scheduler)
You do **not** SSH in to run `discover` / `run` by hand. On the server, one worker process owns both:

1. **On-box cron** (`SCHEDULE_RUN`, `SCHEDULE_INBOX` in `.env`) — default: full pipeline every 4 hours, inbox every 6 hours  
2. **Authenticated webhooks** — EventBridge, curl, or the Settings page buttons  

```bash
# On the EC2 box (systemd — see deploy/ec2/)
python -m applyforme serve          # :8787 cron + /hooks/*
# Public URL (nginx → Next → worker):
curl -X POST https://YOUR_DOMAIN/api/pipeline/webhook \
  -H "Authorization: Bearer $PIPELINE_WEBHOOK_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"stage":"run","limit":40}'
```

| Trigger | What runs |
|---------|-----------|
| `SCHEDULE_RUN` cron inside `serve` | `discover → enrich → match → tailor` |
| `SCHEDULE_INBOX` cron | IMAP inbox poll |
| `POST /hooks/run` or `/api/pipeline/webhook` | same as `run` (async 202) |
| AWS EventBridge → API Destination | see `deploy/ec2/eventbridge-rule.json` |
| Settings → Trigger pipeline | browser → same webhook |
| WhatsApp / Stripe webhooks | separate; billing & STATUS only |

**Deploy once:** clone to `/opt/applyforme`, put secrets in `.env`, then `sudo bash deploy/ec2/setup.sh`. That installs systemd units `applyforme-worker` + `applyforme-web` and nginx. Keep port **8787 firewalled** (localhost only); expose 80/443. Step-by-step push/update commands: [`deploy/ec2/PUSH.md`](deploy/ec2/PUSH.md).

The **Settings** page is the user-facing control for this: status, “Find new jobs now”, and schedule in plain language (deploy details under Advanced).

Local Windows without EC2: still fine to run `python -m applyforme run` manually, or `python -m applyforme serve` and hit `http://127.0.0.1:8787/hooks/run`.

## Daily flow
```powershell
.venv\Scripts\python -m applyforme dashboard         # http://localhost:3000 (leave running)
# complete Onboarding in the browser once
.venv\Scripts\python -m applyforme run               # discover -> score -> tailor (respects seniority)
.venv\Scripts\python -m applyforme apply --dry-run <job_id>
.venv\Scripts\python -m applyforme apply --limit 3   # fills forms, asks before each submit
.venv\Scripts\python -m applyforme inbox             # optional: employer replies
```
If `apply` hits a required question it can't answer, the job moves to **Feedback**. Answer it on the dashboard, then re-run `apply <job_id>`; saved answers are reused automatically. (`apply --ask` asks in the terminal instead.)

## Dashboard (`dashboard/`, Next.js 16 + shadcn `dashboard-01`)
| Page | What it shows |
|------|---------------|
| `/` Landing | Hero (DitherScan + AsciiFluid), Google sign-in, resume upload, cookie notice |
| `/onboarding` | Background, socials, seniority, target roles (required once) |
| `/home` Dashboard | **For you** jobs for your target level + KPIs |
| `/jobs` | All roles agents fetched for your preferences |
| `/applications` | Pipeline statuses (ready / applied / manual / …) |
| `/ats` | Match scores + reasons |
| `/resumes` · `/cover-letters` | Tailored docs per job |
| `/saved` · `/preferences` · `/interview` | Bookmarks, filters, practice prompts |
| `/profile` · `/settings` · `/billing` · `/feedback` | Account |
| `/applications` | Recent applications with status filters; `/applications/<id>` for score reasons, timeline, cover letter, resume |
| `/feedback` | Jobs blocked on your answers, with forms |
| `/inbox` | Applied inbox: submissions + employer confirmations / interviews / rejections |
| `/resumes` | Tailored resumes grouped by job category: preview PDF, download `.tex`, **Open in Overleaf** |
| `/whatsapp` | Link your phone (official WhatsApp Cloud API), then message `STATUS` to get your applied-jobs count |
| `/billing` | Plans + Stripe Checkout (edit plans in `dashboard/src/lib/billing.ts`) |

Preview with fake data (never touches your real DB): `.venv\Scripts\python scripts\seed_demo.py`, then start the dashboard with `APPLYFORME_DB` / `APPLYFORME_OUTPUT` pointing at `data\demo`.

## Optional integrations (all configured in `.env`, see `.env.example`)
- **WhatsApp**: needs a Meta developer app + a public URL for the webhook (e.g. ngrok). The webhook rejects unsigned requests, and only the number that completed the one-time code handshake can query counts.
- **Stripe**: test mode works with just `STRIPE_SECRET_KEY`; add `STRIPE_WEBHOOK_SECRET` for automatic renewals/cancellations.
- **IMAP inbox**: read-only (`BODY.PEEK`), never modifies or deletes mail.

## Deliberate limits
- Submit needs your `y` (`--yes` overrides). Unknown required answers are never guessed.
- No captcha-solving services: solve captchas yourself in the visible browser.
- Google sign-in protects `/home` and the rest of the app when `GOOGLE_CLIENT_*` is set. Without keys (or with `AUTH_DISABLED=1`) the dashboard stays open for local use. Don't expose it publicly without OAuth + a real `AUTH_SECRET`.
- Plans on `/billing` are not enforced by the agents; they're a payment page for your product.
- Aggregator-only listings (LinkedIn Easy Apply, etc.) are scored and tailored but not auto-applied.
- Multi-page portals (Workday, etc.) are discovered, scored and tailored but applied to manually; the applier targets single-page ATS forms.
- Job-board scraping may violate those sites' terms; it's opt-in and your call.

## Tests
```powershell
.venv\Scripts\python -m pytest tests -q                                   # Python (no API key needed)
cd dashboard; npx.cmd next build                                          # type-check + build
node scripts/test-webhooks.mjs http://localhost:3000 ..\data\applyforme.db # WhatsApp webhook smoke test (needs fake WHATSAPP_* env)
```

## Credits
The feature set was inspired by [ApplyPilot](https://github.com/Pickle-Pixel/ApplyPilot) (AGPL-3.0). No ApplyPilot code or data files are copied here; the ideas (validation, judge pass, Workday search, manual-ATS routing, setup wizard) are independently implemented. Workday's search endpoint is Workday's own public API.
