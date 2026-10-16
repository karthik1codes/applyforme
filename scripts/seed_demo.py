"""Seed a THROWAWAY demo database + resumes so the dashboard can be previewed without touching real data.

    .venv\\Scripts\\python scripts\\seed_demo.py
    cd dashboard; $env:APPLYFORME_DB="..\\data\\demo\\applyforme.db"; $env:APPLYFORME_OUTPUT="..\\data\\demo\\output"; npm run dev
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DEMO = ROOT / "data" / "demo"
(DEMO / "output").mkdir(parents=True, exist_ok=True)

from applyforme import store as store_mod  # noqa: E402
from applyforme.agents import resume as R  # noqa: E402
from applyforme.config import load_profile  # noqa: E402
from applyforme.models import Job, Tailored  # noqa: E402

store_mod.DATA_DIR = DEMO
R.OUTPUT_DIR = DEMO / "output"
R.tailor_resume = lambda job, prof: (R._baseline(prof), [])  # no LLM needed

profile = load_profile(ROOT / "profile.example.yaml")
s = store_mod.Store()
s.db.executescript("DELETE FROM jobs; DELETE FROM questions; DELETE FROM events; DELETE FROM kv;")
now = datetime.now(timezone.utc)
iso = lambda d: (now - timedelta(days=d, hours=d)).isoformat(timespec="seconds")  # noqa: E731

JOBS = [  # company, title, location, score, status, days_ago
    ("stripe", "Backend Engineer, Payments", "Remote", 88, "applied", 1),
    ("notion", "Senior Backend Engineer", "Remote", 84, "applied", 2),
    ("airbnb", "Data Engineer, Analytics", "Bengaluru", 81, "applied", 4),
    ("spotify", "Machine Learning Engineer", "Remote", 79, "applied", 6),
    ("figma", "Full-Stack Engineer", "Remote", 77, "ready", 0),
    ("linear", "Frontend Engineer", "Remote", 75, "ready", 0),
    ("vercel", "Platform / SRE Engineer", "Remote", 82, "needs_feedback", 0),
    ("ramp", "Software Engineer, Backend", "Bengaluru", 80, "needs_feedback", 1),
    ("datadog", "Security Engineer", "Remote", 72, "matched", 1),
    ("uber", "Engineering Manager", "Bengaluru", 41, "skipped", 3),
]
for company, title, loc, score, status, d in JOBS:
    job = Job(id=f"demo:{company}:{abs(hash(title)) % 9999}", ats="demo", company=company, title=title, location=loc,
              url=f"https://boards.example.com/{company}/jobs/1", apply_url=f"https://boards.example.com/{company}/jobs/1",
              description="Demo job description.")
    s.add_job(job)
    fields = dict(
        score=score, status=status,
        reasons=json.dumps({"reasons": ["Strong overlap with Python/SQL/AWS", "4 yrs matches the 3-6 yr requirement"], "red_flags": ["Timezone overlap may be limited"] if score < 80 else []}),
    )
    if status in ("applied", "ready", "needs_feedback"):
        pdf, tex, _ = R.build_pdf(job, profile)
        fields["cover_letter"] = Tailored(
            cover_letter=f"Hi {company} team,\n\nI built an ingestion pipeline processing 2M events/day and cut API latency by 40% at Acme Corp. That is the kind of work your {title} role needs.\n\nJane Doe",
            resume_pdf=pdf, resume_tex=tex,
        ).model_dump_json()
    s.update(job.id, **fields)
    if status == "applied":
        s.update(job.id, applied_at=iso(d))
        s.add_event(job.id, "submitted", f"Application submitted to {company}", job.url)
        s.db.execute("UPDATE events SET created_at=? WHERE job_id=? AND kind='submitted'", (iso(d), job.id))
    if status == "needs_feedback":
        s.save_questions(job.id, [
            {"label": "What are your salary expectations (annual, INR)?", "type": "text", "suggested": None},
            {"label": "Are you legally authorized to work in the United States?", "type": "select", "options": ["Yes", "No"], "suggested": "No"},
            {"label": "Why do you want to work at this company? *", "type": "textarea", "suggested": None},
        ])

def event(company, kind, title, body):
    j = s.db.execute("SELECT id FROM jobs WHERE company=?", (company,)).fetchone()["id"]
    s.add_event(j, kind, title, body, ref=f"{company}-{kind}")

event("stripe", "confirmation", "Thanks for applying to Stripe", "From: no-reply@stripe.com\n\nWe received your application for Backend Engineer, Payments.")
event("notion", "interview", "Notion: let's schedule a 30 min intro call", "From: recruiting@notion.so\n\nHi Jane, we'd love to chat. Please share your availability this week.")
event("spotify", "rejection", "Update on your Spotify application", "From: jobs@spotify.com\n\nUnfortunately we won't be moving forward at this time.")
s.db.commit()
print(f"Seeded {len(JOBS)} demo jobs in {DEMO}")
