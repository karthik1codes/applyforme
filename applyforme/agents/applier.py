"""Applier agent: opens the application form in a real browser, maps fields -> profile answers
with an LLM, fills them, then WAITS for human approval before submitting."""
from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import Page, sync_playwright
from pydantic import BaseModel

from ..config import DATA_DIR, ROOT
from ..llm import ask_json
from ..models import FieldAnswer, FormField, Job, Profile, Tailored
from .routing import classify_submission, closed_reason, manual_reason

# Tags every visible form control with data-afm and returns a description.
# Radios/checkboxes sharing a name are collapsed into one logical field with options.
EXTRACT_JS = r"""
() => {
  const vis = el => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return (r.width > 0 && r.height > 0 && s.visibility !== 'hidden') || el.type === 'file'; };
  const txt = el => (el && el.innerText ? el.innerText : '').replace(/\s+/g, ' ').trim();
  const labelOf = el => {
    if (el.getAttribute('aria-label')) return el.getAttribute('aria-label');
    if (el.id) { const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`); if (l) return txt(l); }
    const ll = el.getAttribute('aria-labelledby');
    if (ll) { const t = ll.split(' ').map(i => txt(document.getElementById(i))).join(' ').trim(); if (t) return t; }
    const wrap = el.closest('label'); if (wrap) return txt(wrap);
    const fs = el.closest('fieldset'); if (fs && fs.querySelector('legend')) return txt(fs.querySelector('legend'));
    let p = el.parentElement;
    for (let i = 0; i < 4 && p; i++, p = p.parentElement) {
      const l = p.querySelector('label, legend, [class*="label"]'); if (l && txt(l)) return txt(l);
    }
    return el.placeholder || el.name || '';
  };
  const out = []; const groups = {}; let n = 0;
  document.querySelectorAll('input, textarea, select').forEach(el => {
    const type = el.tagName === 'SELECT' ? 'select' : el.tagName === 'TEXTAREA' ? 'textarea' : (el.type || 'text');
    if (['hidden', 'submit', 'button', 'image', 'reset'].includes(type)) return;
    if (!vis(el)) return;
    if (type === 'radio' || type === 'checkbox') {
      const g = type + ':' + (el.name || labelOf(el));
      const optLabel = txt(el.closest('label')) || (el.id && txt(document.querySelector(`label[for="${CSS.escape(el.id)}"]`))) || el.value;
      if (!groups[g]) {
        const key = 'f' + (n++);
        groups[g] = { key, label: (el.closest('fieldset') && el.closest('fieldset').querySelector('legend')) ? txt(el.closest('fieldset').querySelector('legend')) : labelOf(el), type, required: el.required, options: [] };
        out.push(groups[g]);
      }
      el.setAttribute('data-afm', groups[g].key + '|' + optLabel);
      groups[g].options.push(optLabel);
      return;
    }
    const key = 'f' + (n++);
    el.setAttribute('data-afm', key);
    const f = { key, label: labelOf(el), type, required: el.required || el.getAttribute('aria-required') === 'true', options: [] };
    if (type === 'select') f.options = [...el.options].map(o => o.text.trim()).filter(t => t && !/^select/i.test(t));
    out.push(f);
  });
  return out;
}
"""

SYSTEM = """You fill out a job application form on behalf of a candidate.
For every form field return the value to enter, using ONLY the candidate profile, the tailored
cover letter, and the job info provided.
RULES:
- NEVER invent facts. If the answer is not derivable from the profile, set value to null (a human will answer).
- For select/radio fields, value MUST be exactly one of the listed options. For checkbox groups, a single option label.
- For consent/privacy/terms checkboxes required to apply, choose the affirmative option.
- For EEO/demographic questions use the profile's screening answers; if absent choose a 'decline'-style option.
- For file fields: resume => value 'RESUME'; cover letter file => value 'COVER_LETTER'; anything else => null.
- For a 'cover letter' textarea, use the tailored cover letter text.
- Free-text 'why us' style questions: write 2-4 grounded sentences from the profile, specific to THIS job's
  description, in a natural voice (no 'I am passionate about'); if impossible, null.
- Name fields: use the candidate's preferred name unless the field says 'legal name'.
- Yes/no basics (18+, background check, previously employed here, how did you hear about us) come from
  profile.screening if present; never invent criminal-history, citizenship or licence answers - null instead.
- SALARY: if the job description shows a pay range, answer with its midpoint (convert currency only if the profile
  gives a conversion note); otherwise use profile.compensation.salary_expectation. Never go below
  salary_range_min. Hourly rate = annual / 2080. Asked for a range: expectation +/- 10%.
- Skills questions ("experience with X?"): answer yes only for skills or clearly adjacent work in the profile.
- confidence: 0-1 how sure you are."""


class Answers(BaseModel):
    answers: list[FieldAnswer]


def extract_fields(page: Page) -> list[FormField]:
    return [FormField(**f) for f in page.evaluate(EXTRACT_JS)]


def plan_answers(fields: list[FormField], job: Job, profile: Profile, tailored: Tailored) -> list[FieldAnswer]:
    user = json.dumps(
        {
            "job": {"title": job.title, "company": job.company, "location": job.location, "description": job.description[:3000]},
            "candidate": profile.model_dump(exclude={"sources"}),
            "cover_letter": tailored.cover_letter,
            "fields": [f.model_dump() for f in fields],
        }
    )
    return ask_json(SYSTEM, user, Answers).answers


def _fill(page: Page, f: FormField, value: str, resume: Path, cover_pdf: Path | None) -> None:
    loc_all = page.locator(f'[data-afm^="{f.key}"]')
    if f.type == "file":
        if value == "RESUME":
            loc_all.first.set_input_files(str(resume))
        elif value == "COVER_LETTER" and cover_pdf:
            loc_all.first.set_input_files(str(cover_pdf))
    elif f.type == "select":
        el = page.locator(f'[data-afm="{f.key}"]')
        try:
            el.select_option(label=value)
        except Exception:
            opts = el.evaluate("e => [...e.options].map(o => o.text.trim())")
            m = next((o for o in opts if value.lower() in o.lower() or o.lower() in value.lower()), None)
            if m:
                el.select_option(label=m)
    elif f.type in ("radio", "checkbox"):
        el = page.locator(f'[data-afm="{f.key}|{value}"]')
        if el.count():
            el.first.check(force=True)
    else:
        el = page.locator(f'[data-afm="{f.key}"]')
        el.fill(value)


def _is_required(f: FormField) -> bool:
    return f.required or "*" in f.label or "required" in f.label.lower()


VISIBLE_ERRORS_JS = r"""
() => [...document.querySelectorAll('[aria-invalid="true"], [role="alert"], .error, .errors, .field-error, [class*="error-message"], [class*="invalid"]')]
  .filter(e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && ((e.innerText || '').trim() || e.getAttribute('aria-invalid') === 'true'); })
  .map(e => (e.innerText || e.getAttribute('aria-label') || '').trim().slice(0, 120))
"""


def verify_submission(page: Page, url_before: str, timeout_s: int = 15) -> tuple[str, str]:
    """Poll after clicking Submit. Returns ('applied'|'errors'|'unverified', note). Never assumes success."""
    status, errors = "unverified", []
    for _ in range(timeout_s):
        page.wait_for_timeout(1000)
        try:
            text = page.evaluate("() => document.body ? document.body.innerText.slice(0, 8000) : ''")
            errors = page.evaluate(VISIBLE_ERRORS_JS)
        except Exception:
            continue  # navigation in progress
        status = classify_submission(text, url_before, page.url, len(errors))
        if status == "applied":
            return "applied", "confirmation detected"
    if status == "errors":
        return "errors", "form validation errors after submit: " + "; ".join(e for e in errors if e)[:180]
    return "unverified", "Submit was clicked but no confirmation page/message was detected - check the browser and your email before retrying"


def apply(
    job: Job,
    profile: Profile,
    tailored: Tailored,
    *,
    store=None,
    dry_run: bool = False,
    auto_submit: bool = False,
    ask_terminal: bool = False,
) -> tuple[str, str]:
    """Returns (status, note). status: 'applied' (confirmation seen), 'filled' (dry-run / declined),
    'needs_feedback' (questions saved), 'manual' (SSO / account-wall portal), 'closed', 'errors' or 'unverified'."""
    resume = (ROOT / profile.resume_path).resolve() if not Path(profile.resume_path).is_absolute() else Path(profile.resume_path)
    if tailored.resume_pdf and Path(tailored.resume_pdf).exists():
        resume = Path(tailored.resume_pdf)  # per-job tailored resume
    if not resume.exists():
        raise SystemExit(f"Resume not found at {resume}")

    with sync_playwright() as pw:
        # Persistent profile so cookies / captcha trust survive between runs.
        ctx = pw.chromium.launch_persistent_context(str(DATA_DIR / "browser"), headless=False, viewport={"width": 1280, "height": 900})
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            page.goto(job.apply_url or job.url, wait_until="domcontentloaded")
            page.wait_for_timeout(2500)
            if why := manual_reason(page.url):  # redirected to SSO / an account-wall portal
                return "manual", why
            if why := closed_reason(page.evaluate("() => document.body ? document.body.innerText.slice(0, 3000) : ''")):
                return "closed", why

            # Some job pages need an "Apply" click to reveal the form.
            if not page.locator("input[type=file], input[type=email]").count():
                for name in ("Apply for this job", "Apply now", "Apply"):
                    btn = page.get_by_role("link", name=name).or_(page.get_by_role("button", name=name))
                    if btn.count():
                        btn.first.click()
                        page.wait_for_timeout(2500)
                        break

            fields = extract_fields(page)
            print(f"[applier] found {len(fields)} fields")
            if not fields:
                input("No form detected. Navigate to the form manually in the browser, then press Enter to retry... ")
                fields = extract_fields(page)

            answers = {a.key: a for a in plan_answers(fields, job, profile, tailored)}

            # Decide a value for every field. Uncertain *required* fields become questions for the human:
            # answered earlier on the dashboard -> reuse; else queue them (or ask in the terminal with --ask).
            saved = store.get_answers(job.id) if store else {}
            resolved: list[tuple[FormField, str]] = []
            pending: list[tuple[FormField, str | None]] = []
            for f in fields:
                a = answers.get(f.key)
                value = a.value if a else None
                uncertain = value is None or (a is not None and a.confidence < 0.5 and f.type != "file")
                if uncertain:
                    if f.label in saved:
                        value = saved[f.label]
                    elif not _is_required(f):
                        continue  # optional + unsure: leave blank rather than guess
                    elif ask_terminal:
                        hint = f" options={f.options}" if f.options else ""
                        value = input(f"\n[needs you] {f.label!r} ({f.type}){hint}\n  suggested={value!r}\n  your answer (Enter=skip): ").strip() or value
                    else:
                        pending.append((f, value))
                        continue
                if value not in (None, ""):
                    resolved.append((f, str(value)))

            if pending and store:
                store.save_questions(job.id, [{"label": f.label, "type": f.type, "options": f.options, "suggested": v} for f, v in pending])
                store.add_event(job.id, "needs_feedback", f"{len(pending)} question(s) need your answer", "; ".join(f.label for f, _ in pending)[:500])
                print(f"[applier] {len(pending)} required question(s) saved to the dashboard; answer them there, then re-run apply.")
                return "needs_feedback", "waiting for your answers on the dashboard"

            for f, value in resolved:
                try:
                    _fill(page, f, value, resume, None)
                except Exception as e:
                    print(f"[applier] could not fill {f.label!r}: {e}")

            page.screenshot(path=str(DATA_DIR / f"{job.id.replace(':', '_')}.png"), full_page=True)
            if dry_run:
                input("\nDRY RUN: review the filled form in the browser. Press Enter to close without submitting.")
                return "filled", "dry run - nothing submitted"

            print("\nForm filled. Solve any captcha / fix anything in the browser window now.")
            ok = auto_submit or input("Submit this application? [y/N] ").strip().lower() == "y"
            if not ok:
                return "filled", "filled but not submitted"

            submit = page.locator("button[type=submit], input[type=submit]").or_(page.get_by_role("button", name="Submit"))
            url_before = page.url
            submit.first.click()
            return verify_submission(page, url_before)
        finally:
            ctx.close()
