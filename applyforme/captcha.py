"""Detect CAPTCHA widgets so Apply can stop and ask the human to solve them.

Automatic/third-party solving is deliberately disabled.  Playwright cannot
prove a human solved a challenge, and bypassing CAPTCHA is an access-control
violation.  When a challenge is present the headed browser stays open and the
applier waits for the user; the workflow resumes only after the widget clears.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

from playwright.sync_api import Page

LiveWriter = Callable[[str, str], None]


@dataclass(frozen=True)
class CaptchaChallenge:
    kind: str  # recaptcha_v2 | hcaptcha | turnstile
    sitekey: str
    extra: dict[str, str]


def detect_captcha(page: Page) -> CaptchaChallenge | None:
    """Return an active captcha widget on the page, if any."""
    if not page or page.is_closed():
        return None
    try:
        raw = page.evaluate(
            """() => {
  const pick = (el) => (el && el.getAttribute('data-sitekey')) || '';
  const turn = document.querySelector('.cf-turnstile[data-sitekey], [data-turnstile-sitekey]');
  if (turn) {
    return { kind: 'turnstile', sitekey: pick(turn) || turn.getAttribute('data-turnstile-sitekey') || '' };
  }
  const hc = document.querySelector('.h-captcha[data-sitekey], iframe[src*="hcaptcha.com"]');
  if (hc) {
    const box = document.querySelector('.h-captcha[data-sitekey]');
    if (box) return { kind: 'hcaptcha', sitekey: pick(box) };
    return { kind: 'hcaptcha', sitekey: '' };
  }
  const rc = document.querySelector('.g-recaptcha[data-sitekey], div[data-sitekey][data-widget-id]');
  if (rc) return { kind: 'recaptcha_v2', sitekey: pick(rc) };
  const any = document.querySelector('[data-sitekey]');
  if (any && !any.closest('.cf-turnstile')) {
    const sk = pick(any);
    if (sk) return { kind: 'recaptcha_v2', sitekey: sk };
  }
  const iframe = document.querySelector('iframe[src*="recaptcha"], iframe[src*="hcaptcha"], iframe[src*="challenges.cloudflare"]');
  if (iframe) {
    const src = iframe.getAttribute('src') || '';
    if (src.includes('hcaptcha')) return { kind: 'hcaptcha', sitekey: '' };
    if (src.includes('turnstile') || src.includes('cloudflare')) return { kind: 'turnstile', sitekey: '' };
    return { kind: 'recaptcha_v2', sitekey: '' };
  }
  return null;
}"""
        )
    except Exception:
        return None
    if not raw or not isinstance(raw, dict):
        return None
    kind = str(raw.get("kind") or "").strip()
    sitekey = str(raw.get("sitekey") or "").strip()
    if kind not in ("recaptcha_v2", "hcaptcha", "turnstile"):
        return None
    if not sitekey and kind != "recaptcha_v2":
        try:
            sitekey = page.evaluate(
                """() => {
  const t = document.querySelector('.cf-turnstile[data-sitekey]');
  if (t) return t.getAttribute('data-sitekey') || '';
  const h = document.querySelector('.h-captcha[data-sitekey]');
  if (h) return h.getAttribute('data-sitekey') || '';
  return '';
}"""
            ) or ""
        except Exception:
            sitekey = ""
    if not sitekey:
        return None
    return CaptchaChallenge(kind=kind, sitekey=sitekey, extra={})


def captcha_solved_on_page(page: Page) -> bool:
    """Heuristic: no visible challenge iframe and response field has content."""
    try:
        return bool(
            page.evaluate(
                """() => {
  const ta = document.querySelector('textarea[name="g-recaptcha-response"], textarea[name="h-captcha-response"], input[name="cf-turnstile-response"]');
  if (ta && (ta.value || '').length > 20) return true;
  const challenge = document.querySelector('iframe[src*="recaptcha/api2/bframe"], iframe[src*="hcaptcha.com/captcha"], .cf-turnstile[data-state="expired"]');
  if (challenge && challenge.offsetParent !== null) return false;
  return !document.querySelector('iframe[src*="recaptcha"], iframe[src*="hcaptcha"], .cf-turnstile:not([data-state="success"])');
}"""
            )
        )
    except Exception:
        return False


def resolve_page_captchas(
    page: Page,
    *,
    live: LiveWriter | None = None,
    max_attempts: int = 2,
) -> tuple[bool, str]:
    """Never solve automatically. Return whether the page is clear for the human."""
    del max_attempts  # kept for API compatibility; there is no auto-retry loop
    challenge = detect_captcha(page)
    if not challenge:
        return True, "no captcha"
    if captcha_solved_on_page(page):
        return True, "captcha already satisfied"
    if live:
        live("captcha", f"{challenge.kind} detected — solve it in the Chromium window; auto-solving is disabled")
    return (
        False,
        f"{challenge.kind} present — solve it in the browser. Automatic/third-party CAPTCHA solving is disabled.",
    )


def wait_for_manual_captcha(
    page: Page,
    seconds: int,
    *,
    live: LiveWriter | None = None,
    poll_ms: int = 1500,
) -> bool:
    """Wait until the human clears the captcha or the bounded timeout expires."""
    if seconds <= 0:
        return captcha_solved_on_page(page) or not detect_captcha(page)
    end = time.time() + seconds
    while time.time() < end:
        if page.is_closed():
            return False
        if not detect_captcha(page) or captcha_solved_on_page(page):
            return True
        if live:
            left = int(end - time.time())
            live("captcha", f"Solve captcha in the browser ({left}s left)")
        try:
            page.wait_for_timeout(min(poll_ms, max(200, int((end - time.time()) * 1000))))
        except Exception:
            return False
    return captcha_solved_on_page(page)
