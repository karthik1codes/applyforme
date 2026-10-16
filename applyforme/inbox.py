"""Applied inbox: optional, read-only IMAP poller that matches employer emails to applied jobs
and records them as timeline events. Env: IMAP_HOST, IMAP_USER, IMAP_PASSWORD (app password), IMAP_FOLDER."""
from __future__ import annotations

import email
import imaplib
import os
import re
from datetime import datetime, timedelta
from email.header import decode_header, make_header
from email.utils import parseaddr

from .store import Store

KINDS = [  # first match wins
    ("rejection", r"unfortunately|not (be )?moving forward|regret to inform|other candidates|will not be proceeding|decided not to"),
    ("interview", r"interview|schedule a (call|chat)|availability|next steps|phone screen|assessment|coding challenge"),
    ("confirmation", r"thank you for applying|received your application|application (has been )?received|we got your application"),
]


def classify(text: str) -> str:
    t = text.lower()
    return next((k for k, pat in KINDS if re.search(pat, t)), "reply")


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _text(msg: email.message.Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                return (part.get_payload(decode=True) or b"").decode(part.get_content_charset() or "utf-8", "replace")
        return ""
    return (msg.get_payload(decode=True) or b"").decode(msg.get_content_charset() or "utf-8", "replace")


def poll(days: int = 14) -> int:
    host, user, pw = os.getenv("IMAP_HOST"), os.getenv("IMAP_USER"), os.getenv("IMAP_PASSWORD")
    if not (host and user and pw):
        print("Set IMAP_HOST, IMAP_USER and IMAP_PASSWORD in .env to enable the applied inbox (Gmail: use an app password).")
        return 0
    store = Store()
    applied = store.db.execute("SELECT id, company, title FROM jobs WHERE status='applied'").fetchall()
    if not applied:
        print("No applied jobs yet.")
        return 0
    added = 0
    m = imaplib.IMAP4_SSL(host)
    m.login(user, pw)
    m.select(os.getenv("IMAP_FOLDER", "INBOX"), readonly=True)  # readonly: never changes your mailbox
    since = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")
    _, data = m.search(None, f'(SINCE "{since}")')
    for num in data[0].split():
        _, raw = m.fetch(num, "(BODY.PEEK[])")
        msg = email.message_from_bytes(raw[0][1])
        sender = parseaddr(msg.get("From", ""))[1].lower()
        subject = str(make_header(decode_header(msg.get("Subject", ""))))
        body = _text(msg)[:4000]
        hay = _slug(f"{sender} {subject} {body}")
        for j in applied:
            co = _slug(j["company"])
            if len(co) >= 3 and co in hay:
                kind = classify(f"{subject} {body}")
                ref = msg.get("Message-ID") or f"{sender}:{subject}"
                before = store.db.total_changes
                store.add_event(j["id"], kind, subject[:140] or "(no subject)", f"From: {sender}\n\n{body[:1200]}", ref=ref)
                added += store.db.total_changes - before > 0
                break
    m.logout()
    print(f"Inbox: {added} new event(s).")
    return added
