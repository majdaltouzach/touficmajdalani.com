#!/usr/bin/env python3
"""
Contact form handler for touficmajdalani.com
Listens on 127.0.0.1:LISTEN_PORT, handles POST /contact-submit
Sends confirmation email to user + copy to site owner via ProtonMail SMTP
"""

import json
import logging
import os
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

# ── Rate limiting: max 5 submissions per IP per hour ──────────────────────────
_rate: dict = defaultdict(list)
RATE_LIMIT  = 5
RATE_WINDOW = 3600  # seconds


def rate_ok(ip: str) -> bool:
    now = time.time()
    _rate[ip] = [t for t in _rate[ip] if now - t < RATE_WINDOW]
    if len(_rate[ip]) >= RATE_LIMIT:
        return False
    _rate[ip].append(now)
    return True


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
    subject = "Your message has been received — Toufic Majdalani"
    html = f"""
    <html><body style="font-family:'Rubik',Arial,sans-serif;color:#4d4d4d;max-width:600px;margin:auto;padding:24px">
      <h2 style="color:#6f6f6f">Message Received ✓</h2>
      <p>Hi {first},</p>
      <p>Thanks for reaching out! I've received your message and will get back to you shortly.</p>
      <hr style="border:none;border-top:1px solid #ddd;margin:24px 0"/>
      <h3 style="color:#6f6f6f">Your submission:</h3>
      <table style="width:100%;border-collapse:collapse">
        <tr><td style="padding:6px 0;color:#999;width:110px">Name</td>
            <td style="padding:6px 0">{first} {last}</td></tr>
        <tr><td style="padding:6px 0;color:#999">Email</td>
            <td style="padding:6px 0">{email}</td></tr>
        <tr><td style="padding:6px 0;color:#999;vertical-align:top">Message</td>
            <td style="padding:6px 0;white-space:pre-wrap">{message}</td></tr>
      </table>
      <hr style="border:none;border-top:1px solid #ddd;margin:24px 0"/>
      <p style="color:#999;font-size:13px">— Toufic Majdalani · <a href="{SITE_ORIGIN}" style="color:#6f6f6f">{SITE_ORIGIN}</a></p>
    </body></html>
    """
    text = (
        f"Hi {first},\n\n"
        "Thanks for reaching out! I've received your message and will get back to you shortly.\n\n"
        "--- Your submission ---\n"
        f"Name:    {first} {last}\n"
        f"Email:   {email}\n"
        f"Message: {message}\n"
        "----------------------\n\n"
        f"— Toufic Majdalani · {SITE_ORIGIN}"
    )
    send_email(email, subject, html, text)


def send_owner_copy(first: str, last: str, email: str, message: str) -> None:
    subject = f"[Contact Form] New message from {first} {last}"
    html = f"""
    <html><body style="font-family:'Rubik',Arial,sans-serif;color:#4d4d4d;max-width:600px;margin:auto;padding:24px">
      <h2 style="color:#6f6f6f">New Contact Form Submission</h2>
      <table style="width:100%;border-collapse:collapse">
        <tr><td style="padding:6px 0;color:#999;width:110px">Name</td>
            <td style="padding:6px 0"><strong>{first} {last}</strong></td></tr>
        <tr><td style="padding:6px 0;color:#999">Email</td>
            <td style="padding:6px 0"><a href="mailto:{email}">{email}</a></td></tr>
        <tr><td style="padding:6px 0;color:#999;vertical-align:top">Message</td>
            <td style="padding:6px 0;white-space:pre-wrap">{message}</td></tr>
      </table>
    </body></html>
    """
    text = (
        f"Name:    {first} {last}\n"
        f"Email:   {email}\n"
        f"Message: {message}\n"
    )
    send_email(CONTACT_TO, subject, html, text)


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
        raw    = self.rfile.read(length).decode("utf-8", errors="replace")
        ct     = self.headers.get("Content-Type", "")

        if "application/json" in ct:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                self._json(400, {"error": "Invalid JSON"}); return
            first   = data.get("first_name", "").strip()
            last    = data.get("last_name",  "").strip()
            email   = data.get("email",      "").strip()
            message = data.get("message",    "").strip()
        else:  # form-urlencoded
            parsed  = parse_qs(raw)
            first   = parsed.get("first_name", [""])[0].strip()
            last    = parsed.get("last_name",  [""])[0].strip()
            email   = parsed.get("email",      [""])[0].strip()
            message = parsed.get("message",    [""])[0].strip()

        # Validation
        if not all([first, last, email, message]):
            self._json(400, {"error": "All fields are required."}); return
        if "@" not in email or "." not in email.split("@")[-1]:
            self._json(400, {"error": "Invalid email address."}); return
        if len(message) > 5000:
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
