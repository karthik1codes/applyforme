"""Decide, without a browser, when a job can't be auto-applied and how to tell if a submit really worked."""
from __future__ import annotations

import re
from urllib.parse import urlparse

# ATS portals that force account creation / multi-page wizards / hard captchas: tailor the resume, then apply by hand.
MANUAL_ATS_DOMAINS = [
    "myworkdayjobs.com", "myworkdaysite.com", "icims.com", "taleo.net", "successfactors.com",
    "oraclecloud.com", "ibegin.com",
]

# Sign-in walls we deliberately never automate (no credential entry into Google/Microsoft/SSO pages).
SSO_DOMAINS = [
    "accounts.google.com", "login.microsoftonline.com", "login.live.com", "appleid.apple.com",
    "okta.com", "auth0.com", "onelogin.com", "linkedin.com/login", "linkedin.com/uas",
]

_CLOSED = re.compile(
    r"no longer (accepting|available|open)|(position|role|job|posting)( has| is)?( been)? (filled|closed|expired|removed)"
    r"|this job (has )?(expired|closed)|job (is )?not (found|available)|page (you were looking for )?(not found|doesn.t exist)",
    re.I,
)

_STRONG_SUCCESS = re.compile(
    r"application (has been |was |is )?(successfully )?(submitted|received|sent|complete)"
    r"|(we|they)('ve| have) received your application"
    r"|successfully (applied|submitted)|thank(s| you) for (applying|your application|submitting)"
    r"|your application (is|has been) (in|submitted|received|complete)"
    r"|you('ve| have) (successfully )?(applied|submitted)"
    r"|application (submission )?confirmed",
    re.I,
)
_SOFT_SUCCESS = re.compile(r"\bthank(s| you)\b|\bconfirmation\b|\ball set\b", re.I)
_SUCCESS_URL = re.compile(r"(confirm|thank|submitted|success|complete|applied)", re.I)
# Pages that look like a success URL but are not an application confirmation.
_NOT_SUCCESS = re.compile(
    r"thank(s| you) for (visiting|your interest|your time|considering)"
    r"|(page|job|position|role) (not found|no longer|expired|closed)"
    r"|please (fix|correct|complete|review) (the )?(errors?|fields?|form)"
    r"|something went wrong|unable to submit|submission failed"
    r"|sign in|log in|create an account",
    re.I,
)
_SUBMIT_CONTROL = re.compile(
    r"submit (your )?application|send (your )?application|submit$|finish$|done applying", re.I
)


def is_confirmation_text(text: str) -> bool:
    """True only when the page text contains an explicit confirmation."""
    t = text or ""
    return bool(_STRONG_SUCCESS.search(t)) and not bool(_NOT_SUCCESS.search(t))


def has_submit_control(page_text: str) -> bool:
    """Rough signal that the form is still waiting to be submitted."""
    return bool(_SUBMIT_CONTROL.search((page_text or "")[:6000]))


def manual_reason(url: str) -> str | None:
    """Return why this URL must be applied to manually, or None if automation may proceed."""
    if not url:
        return None
    u = urlparse(url)
    host, full = (u.netloc or "").lower(), f"{u.netloc}{u.path}".lower()
    for d in SSO_DOMAINS:
        if d in full:
            return f"requires single sign-on ({d.split('/')[0]})"
    for d in MANUAL_ATS_DOMAINS:
        if host == d or host.endswith("." + d):
            return f"{d} needs an account and a multi-step wizard - apply manually with your tailored resume"
    return None


def closed_reason(page_text: str) -> str | None:
    m = _CLOSED.search(page_text or "")
    return f"job appears closed ({m.group(0).strip()})" if m else None


def classify_submission(text: str, url_before: str, url_after: str, error_count: int) -> str:
    """'applied' (confirmed), 'errors' (validation), 'login', or 'unverified'.

    A URL change alone is never enough.  Careers sites commonly redirect to a
    ``/thank-you`` page for a newsletter, a job alert, or a generic "thanks for
    visiting" page; treating that as an application confirmation is how jobs
    were marked applied without being submitted.
    """
    text = text or ""
    if _NOT_SUCCESS.search(text[:4000]):
        if re.search(r"sign in|log in|create an account", text[:4000], re.I):
            return "login"
        if error_count > 0:
            return "errors"
        return "unverified"
    if _STRONG_SUCCESS.search(text):
        return "applied"
    moved = url_after != url_before
    if moved and _SUCCESS_URL.search(url_after) and _SOFT_SUCCESS.search(text[:1500]) and not error_count:
        # A success URL plus a soft thank-you is still not enough on its own;
        # require the text to look like an application acknowledgement.
        if re.search(r"appl(y|ication)|submission|candidate", text[:2500], re.I):
            return "applied"
    if error_count > 0:
        return "errors"
    return "unverified"
