# applyforme

Agentic job-application pipeline with a Next.js dashboard. State lives in one SQLite file (`data/applyforme.db`) shared by the Python agents and the dashboard.

| # | Stage | Command | What happens |
|---|-------|---------|--------------|
| 1 | Discover | `discover` | Indeed/LinkedIn/Glassdoor/ZipRecruiter/Google (JobSpy) + Greenhouse/Lever/Ashby/Workday; optional Crustdata (capped credits) |
| 2 | Enrich | `enrich` | Full description: JSON-LD -> page text -> LLM; optional Crustdata company links (budgeted) |
| 3 | Score | `match` | LLM scores 0-100 vs your profile; below `min_match_score` is skipped |
| 4 | Tailor resume | `tailor` | Per-job **PDF** (uploaded to the form) and **LaTeX** (Overleaf). Reorders/rewords only; code-validated so employers, titles, dates, skills and numbers can't be invented |
| 5 | Cover letter | `tailor` | Grounded in your profile |
| 6 | Apply | `apply` | Headed Chromium fills the form, including **LinkedIn Easy Apply** (sign in once in the window; cookies persist). Live view in dashboard; review before submit |

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
- **Resume**: employers, titles, dates, skills and every number are checked against your profile. Optional second LLM "judge" (`APPLYFORME_JUDGE=1`) catches invented work but roughly doubles tailor time. Any violation falls back to your original content.
- **Cover letter**: length, leaked assistant phrasing, `[Placeholders]` and typographic tells are checked; failures are regenerated from a fresh prompt up to 3 times, and the job stays un-tailored if it never passes.
- **Submit verification**: `applied` is only recorded when a confirmation page/message is detected. Otherwise the job becomes `failed` with the reason (validation errors, or "no confirmation seen - check your email") so it can't be double-submitted.
- **Apply manually**: SSO sign-in walls and account-wall portals (Workday, iCIMS, Taleo, SuccessFactors, ...) are routed to **Apply manually** with your tailored resume ready, instead of failing. Closed postings are skipped.
- **Location filter**: `reject_locations` drops "Remote (US only)" style roles unless the posting also names a place you accept.
- **Seniority filter**: `preferences.seniority_level: junior` drops Senior/Staff/Principal/Lead/Manager titles before scoring; the matcher also hard-fails mismatches.
- **Workday**: add employers under `sources.workday` in `profile.yaml` (see the example) to discover from their public JSON search.
- **Crustdata** (optional): set `CRUSTDATA_API_KEY`. Company enrich is capped (`CRUSTDATA_MAX_ENRICH_PER_RUN`, default 5 ≈ 10 credits) and cached. Job index search is **off** by default (`CRUSTDATA_JOB_SEARCH=1` to enable). JobSpy boards stay free.
- **Watch Apply**: `APPLYFORME_BROWSER_HEADED=1` opens a real Chromium window; the application page shows a live screenshot feed while the agent works.

## Onboarding (dashboard)
Open http://localhost:3000 → sign in (or local mode) → **Onboarding** asks for:
1. Resume upload
2. Background (current title, **seniority level**, years, target titles, skills)
3. Social links (LinkedIn, GitHub, portfolio, website, X)
4. Locations / salary / work auth

That writes `profile.yaml` (`onboarding_complete: true`). Agents read it on every run. **Junior** seniority automatically blocks Senior / Staff / Principal / Lead / Director / Manager titles in discovery and scoring. Change anytime under **Preferences** or `/onboarding?force=1`.

## Production: AWS EC2 (backend runs on the instance)
Deploy the **worker + Next.js dashboard** on an EC2 box — that is the supported production path. systemd keeps both pipelines alive (jobs ∥ internships) with on-box cron and webhooks. You do **not** SSH in to run `discover` / `run` by hand.

```bash
# Amazon Linux instance — SSH as ec2-user (not ubuntu)
ssh -i ~/.ssh/your-key.pem ec2-user@YOUR_EC2_IP
# Or launch a new AL2023 box:
#   export AWS_REGION=ap-south-1 KEY_NAME=your-keypair
#   export APPLYFORME_REPO_URL=https://github.com/YOUR_USER/applyforme.git
#   export ALLOCATE_EIP=1        # optional: stable public IP
#   bash deploy/ec2/launch-ec2.sh
```
Full `ec2-user` commands: [`deploy/ec2/PUSH.md`](deploy/ec2/PUSH.md).

| Trigger | What runs |
|---------|-----------|
| `SCHEDULE_RUN` | jobs lane: `discover → enrich → match → tailor` |
| `SCHEDULE_INTERNSHIPS` | internships lane (Glassdoor / Wellfound / …) |
| `SCHEDULE_INBOX` | IMAP inbox poll |
| `JOB_RETENTION_DAYS` | drop untouched listings older than N days (default 10; applied/ready/manual kept) |
| `POST /api/pipeline/webhook` `{"stage":"run"\|"internships"\|"cleanup"}` | same lanes (async 202) |
| AWS EventBridge | optional — `deploy/ec2/eventbridge-rule.json` |
| Settings / Internships UI | browser → same webhook |

Security group: **22 / 80 / 443** only. Port **8787** stays on localhost. Full guide: [`deploy/ec2/PUSH.md`](deploy/ec2/PUSH.md).

Local Windows: `python -m applyforme dashboard` still starts UI + worker for development.

## Daily flow (UI-first — no manual agent commands)
```powershell
.venv\Scripts\python -m applyforme dashboard   # starts web UI + background worker
```
Then in the browser at http://localhost:3000:
1. Finish **Onboarding** → a job search starts automatically
2. Use **Find jobs for me** on Dashboard / Jobs / Settings anytime
3. Open a role → **Job posting** / **Careers** links · tailor & apply from the UI

Agents are triggered by those buttons (and by on-box cron / EventBridge). You should not need to run `discover` / `run` by hand.

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
- **LinkedIn connector**: per-user OAuth 2.0 with the official OpenID Connect scopes `openid profile email` and `/v2/userinfo`. Tokens are AES-256-GCM encrypted with `LINKEDIN_TOKEN_KEY`; the connector never asks for a password. LinkedIn does not offer public job-search, saved-job, Easy Apply, or application-submit APIs, so this connector deliberately does not claim those capabilities. See `.env.example` for the three required settings and the exact redirect URI.

## Deliberate limits
- Apply prepares and validates the form, then stops for your review. Submission is a separate **Submit application** action (or `--submit` on the CLI); the dashboard never adds `--yes`. One authorization covers one application.
- Unknown required answers are never guessed. The agent pauses for you or marks the job `needs_feedback`.
- No captcha-solving services: a detected challenge stops the workflow and you solve it in the visible browser.
- LinkedIn connector uses official OpenID Connect (`openid profile email`) and `/v2/userinfo` per signed-in user. LinkedIn has no public job-search/Easy-Apply/application API, so applying still happens in the browser where you sign in yourself.
- Google sign-in protects `/home` and the rest of the app when `GOOGLE_CLIENT_*` is set. Without keys (or with `AUTH_DISABLED=1`) the dashboard stays open for local use. Don't expose it publicly without OAuth + a real `AUTH_SECRET`.
- Plans on `/billing` are not enforced by the agents; they're a payment page for your product.
- Aggregator-only listings (LinkedIn Easy Apply, etc.) are scored and tailored; the applier fills them in the browser and stops for review. Nothing is submitted without the separate Submit action.
- Multi-page portals (Workday, etc.) are discovered, scored and tailored but applied to manually; the applier targets single-page ATS forms.
- Job-board discovery (Indeed/LinkedIn/Glassdoor/ZipRecruiter/Google) runs on every `discover`/`run`. Those sites' terms may restrict scraping — you accept that risk by running the pipeline.

## Tests
```powershell
.venv\Scripts\python -m pytest tests -q                                   # Python (no API key needed)
cd dashboard; npx.cmd next build                                          # type-check + build
node scripts/test-webhooks.mjs http://localhost:3000 ..\data\applyforme.db # WhatsApp webhook smoke test (needs fake WHATSAPP_* env)
```

## Credits
The feature set was inspired by [ApplyPilot](https://github.com/Pickle-Pixel/ApplyPilot) (AGPL-3.0). No ApplyPilot code or data files are copied here; the ideas (validation, judge pass, Workday search, manual-ATS routing, setup wizard) are independently implemented. Workday's search endpoint is Workday's own public API.
