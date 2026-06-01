#!/usr/bin/env python3
"""
Contact form handler for touficmajdalani.com
Listens on 127.0.0.1:LISTEN_PORT, handles POST /contact-submit
Sends confirmation email to user + copy to site owner via ProtonMail SMTP
"""

import html as _html
import json
import logging
import os
import re
import smtplib
import time
from collections import defaultdict
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

# ── Config from environment ───────────────────────────────────────────────────
SMTP_HOST   = os.environ.get("SMTP_HOST",    "smtp.protonmail.ch")
SMTP_PORT   = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER   = os.environ["SMTP_USER"]   # fail fast if missing
SMTP_PASS   = os.environ["SMTP_PASS"]
CONTACT_TO  = os.environ.get("CONTACT_TO",  SMTP_USER)
LISTEN_HOST = os.environ.get("LISTEN_HOST", "127.0.0.1")
LISTEN_PORT = int(os.environ.get("LISTEN_PORT", "5001"))
SITE_ORIGIN = os.environ.get("SITE_ORIGIN", "https://touficmajdalani.com")

# ── Request size cap ──────────────────────────────────────────────────────────
MAX_BODY = 10_240  # 10 KB

# ── Rate limiting ─────────────────────────────────────────────────────────────
_rate: dict         = defaultdict(list)  # per-IP submission timestamps
_global_hits: list  = []                 # all-IP submission timestamps
_violations: dict   = defaultdict(int)   # per-IP violation count (rate + bad attempts)
_blocked: dict      = {}                 # ip -> unblock timestamp
_bad_attempts: dict = defaultdict(list)  # per-IP invalid-request timestamps

RATE_LIMIT          = 5      # max successful submissions per IP per hour
GLOBAL_LIMIT        = 20     # max submissions across all IPs per hour
RATE_WINDOW         = 3600   # seconds (1 hour sliding window)
INVALID_LIMIT       = 3      # bad attempts before soft block
BLOCK_AFTER         = 3      # escalate to hard block after this many violations
BLOCK_DURATION_SOFT = 3600   # 1 hour soft block (first offence)
BLOCK_DURATION      = 86400  # 24 hours hard block (repeat offender)

# ── Input validation ──────────────────────────────────────────────────────────
_EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s]{2,}$")
# Strips control characters that enable SMTP header injection
_CTRL_RE  = re.compile(r"[\r\n\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _sanitize(s: str) -> str:
    return _CTRL_RE.sub("", s)


def _check_block(ip: str, now: float) -> bool:
    """Return True if IP is currently blocked. Expire stale blocks."""
    if ip in _blocked:
        if now < _blocked[ip]:
            return True
        del _blocked[ip]
        _violations[ip] = 0
    return False


def rate_ok(ip: str) -> bool:
    now = time.time()
    if _check_block(ip, now):
        return False

    # Global throttle — limits distributed attacks across many IPs
    _global_hits[:] = [t for t in _global_hits if now - t < RATE_WINDOW]
    if len(_global_hits) >= GLOBAL_LIMIT:
        return False

    # Per-IP throttle — repeated violations escalate to hard block
    _rate[ip] = [t for t in _rate[ip] if now - t < RATE_WINDOW]
    if len(_rate[ip]) >= RATE_LIMIT:
        _violations[ip] += 1
        if _violations[ip] >= BLOCK_AFTER:
            _blocked[ip] = now + BLOCK_DURATION
            logging.warning("Hard-blocked IP %s for 24 h after %d violations", ip, _violations[ip])
        else:
            _blocked[ip] = now + BLOCK_DURATION_SOFT
            logging.warning("Soft-blocked IP %s for 1 h (rate limit)", ip)
        return False

    _rate[ip].append(now)
    _global_hits.append(now)
    return True


def record_bad_attempt(ip: str) -> None:
    """Count a validation failure; block IP after INVALID_LIMIT bad attempts."""
    now = time.time()
    if _check_block(ip, now):
        return  # already blocked, no need to re-evaluate
    _bad_attempts[ip] = [t for t in _bad_attempts[ip] if now - t < RATE_WINDOW]
    _bad_attempts[ip].append(now)
    if len(_bad_attempts[ip]) >= INVALID_LIMIT:
        _bad_attempts[ip] = []  # reset window after triggering block
        _violations[ip] += 1
        if _violations[ip] >= BLOCK_AFTER:
            _blocked[ip] = now + BLOCK_DURATION
            logging.warning("Hard-blocked IP %s for 24 h (bad attempts)", ip)
        else:
            _blocked[ip] = now + BLOCK_DURATION_SOFT
            logging.warning("Soft-blocked IP %s for 1 h (bad attempts)", ip)


# ── Email helpers ─────────────────────────────────────────────────────────────

def send_email(to: str, subject: str, body_html: str, body_text: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = SMTP_USER
    msg["To"]      = to
    msg.attach(MIMEText(body_text, "plain"))
    msg.attach(MIMEText(body_html, "html"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
        s.ehlo()
        s.starttls()
        s.login(SMTP_USER, SMTP_PASS)
        s.sendmail(SMTP_USER, [to], msg.as_string())


def send_confirmation(first: str, last: str, email: str, message: str) -> None:
    ef, el, ee, em = (_html.escape(x) for x in (first, last, email, message))
    subject   = "Your message has been received — Toufic Majdalani"
    body_html = f"""
    <html><body style="font-family:'Rubik',Arial,sans-serif;color:#4d4d4d;max-width:600px;margin:auto;padding:24px">
      <h2 style="color:#6f6f6f">Message Received ✓</h2>
      <p>Hi {ef},</p>
      <p>Thanks for reaching out! I've received your message and will get back to you shortly.</p>
      <hr style="border:none;border-top:1px solid #ddd;margin:24px 0"/>
      <h3 style="color:#6f6f6f">Your submission:</h3>
      <table style="width:100%;border-collapse:collapse">
        <tr><td style="padding:6px 0;color:#999;width:110px">Name</td>
            <td style="padding:6px 0">{ef} {el}</td></tr>
        <tr><td style="padding:6px 0;color:#999">Email</td>
            <td style="padding:6px 0">{ee}</td></tr>
        <tr><td style="padding:6px 0;color:#999;vertical-align:top">Message</td>
            <td style="padding:6px 0;white-space:pre-wrap">{em}</td></tr>
      </table>
      <hr style="border:none;border-top:1px solid #ddd;margin:24px 0"/>
      <p style="color:#999;font-size:13px">— Toufic Majdalani · <a href="{SITE_ORIGIN}" style="color:#6f6f6f">{SITE_ORIGIN}</a></p>
    </body></html>
    """
    body_text = (
        f"Hi {first},\n\n"
        "Thanks for reaching out! I've received your message and will get back to you shortly.\n\n"
        "--- Your submission ---\n"
        f"Name:    {first} {last}\n"
        f"Email:   {email}\n"
        f"Message: {message}\n"
        "----------------------\n\n"
        f"— Toufic Majdalani · {SITE_ORIGIN}"
    )
    send_email(email, subject, body_html, body_text)


def send_owner_copy(first: str, last: str, email: str, message: str) -> None:
    ef, el, ee, em = (_html.escape(x) for x in (first, last, email, message))
    subject   = f"[Contact Form] New message from {first} {last}"
    body_html = f"""
    <html><body style="font-family:'Rubik',Arial,sans-serif;color:#4d4d4d;max-width:600px;margin:auto;padding:24px">
      <h2 style="color:#6f6f6f">New Contact Form Submission</h2>
      <table style="width:100%;border-collapse:collapse">
        <tr><td style="padding:6px 0;color:#999;width:110px">Name</td>
            <td style="padding:6px 0"><strong>{ef} {el}</strong></td></tr>
        <tr><td style="padding:6px 0;color:#999">Email</td>
            <td style="padding:6px 0"><a href="mailto:{ee}">{ee}</a></td></tr>
        <tr><td style="padding:6px 0;color:#999;vertical-align:top">Message</td>
            <td style="padding:6px 0;white-space:pre-wrap">{em}</td></tr>
      </table>
    </body></html>
    """
    body_text = (
        f"Name:    {first} {last}\n"
        f"Email:   {email}\n"
        f"Message: {message}\n"
    )
    send_email(CONTACT_TO, subject, body_html, body_text)


# ── HTTP handler ──────────────────────────────────────────────────────────────

class ContactHandler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):  # route to stdlib logging
        logging.info("%s - %s", self.address_string(), fmt % args)

    def _json(self, code: int, data: dict) -> None:
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type",  "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", SITE_ORIGIN)
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):  # preflight
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin",  SITE_ORIGIN)
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        if urlparse(self.path).path != "/contact-submit":
            self._json(404, {"error": "not found"})
            return

        ip = self.client_address[0]
        if not rate_ok(ip):
            self._json(429, {"error": "Too many requests. Please wait before submitting again."})
            return

        length = int(self.headers.get("Content-Length", 0))
        if length > MAX_BODY:
            record_bad_attempt(ip)
            self._json(413, {"error": "Request too large."}); return
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        ct  = self.headers.get("Content-Type", "")

        if "application/json" in ct:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                record_bad_attempt(ip)
                self._json(400, {"error": "Invalid JSON"}); return
            first    = _sanitize(data.get("first_name", "").strip())
            last     = _sanitize(data.get("last_name",  "").strip())
            email    = _sanitize(data.get("email",      "").strip())
            message  = _sanitize(data.get("message",    "").strip())
            honeypot = data.get("phone", "").strip()
        else:  # form-urlencoded
            parsed   = parse_qs(raw)
            first    = _sanitize(parsed.get("first_name", [""])[0].strip())
            last     = _sanitize(parsed.get("last_name",  [""])[0].strip())
            email    = _sanitize(parsed.get("email",      [""])[0].strip())
            message  = _sanitize(parsed.get("message",    [""])[0].strip())
            honeypot = parsed.get("phone", [""])[0].strip()

        # Honeypot — bots fill hidden fields, humans don't
        if honeypot:
            logging.warning("Honeypot triggered from %s", ip)
            self._json(200, {"ok": True, "message": "Message sent! Check your inbox for a confirmation."})
            return

        # Validation — each failure counts as a bad attempt
        if not all([first, last, email, message]):
            record_bad_attempt(ip)
            self._json(400, {"error": "All fields are required."}); return
        if len(first) > 40 or len(last) > 40:
            record_bad_attempt(ip)
            self._json(400, {"error": "Name too long."}); return
        if not _EMAIL_RE.match(email):
            record_bad_attempt(ip)
            self._json(400, {"error": "Invalid email address."}); return
        if len(message) < 5 or " " not in message:
            record_bad_attempt(ip)
            self._json(400, {"error": "Please enter a real message."}); return
        if len(message) > 5000:
            record_bad_attempt(ip)
            self._json(400, {"error": "Message too long (max 5000 chars)."}); return

        try:
            send_confirmation(first, last, email, message)
            send_owner_copy(first, last, email, message)
        except Exception as exc:
            logging.error("SMTP error: %s", exc)
            self._json(500, {"error": "Failed to send email. Please try again later."}); return

        self._json(200, {"ok": True, "message": "Message sent! Check your inbox for a confirmation."})


# ── Entrypoint ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    server = HTTPServer((LISTEN_HOST, LISTEN_PORT), ContactHandler)
    logging.info("Contact handler listening on %s:%d", LISTEN_HOST, LISTEN_PORT)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logging.info("Shutting down")
