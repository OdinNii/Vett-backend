"""
Email delivery via SendGrid REST API v3.

Uses httpx (already a project dependency) so no new packages are required.
All functions are async-safe and swallow errors so the calling scanner is
never interrupted by an email failure.

Usage
-----
    from app.services.email_service import send_application_digest
    await send_application_digest(user_email, user_name, applications, profile)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, date
from typing import Optional

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

_SENDGRID_URL = "https://api.sendgrid.com/v3/mail/send"

# ── Data contract passed in from the scanner ─────────────────────────────────

@dataclass
class ApplicationDigestItem:
    job_title: str
    company: str
    status: str          # "submitted" | "manual_required" | "applied" | "failed"
    job_url: str         # redirect URL to the original job posting
    application_id: str  # UUID — used to build fallback-pack deep-link


# ── Internal helpers ──────────────────────────────────────────────────────────

def _first_name(full_name: Optional[str], email: str) -> str:
    if full_name and full_name.strip():
        return full_name.strip().split()[0]
    return email.split("@")[0].capitalize()


def _time_label(notification_time: Optional[str]) -> str:
    mapping = {
        "morning":   "tomorrow morning at 7 am",
        "afternoon": "tomorrow afternoon at 1 pm",
        "evening":   "tomorrow evening at 6 pm",
    }
    return mapping.get(notification_time or "morning", "tomorrow morning at 7 am")


def _currency_symbol(currency: str) -> str:
    return "£" if currency.upper() == "GBP" else "$"


# ── HTML + plain-text builders ────────────────────────────────────────────────

def _build_email(
    first_name: str,
    submitted: list[ApplicationDigestItem],
    manual: list[ApplicationDigestItem],
    next_briefing: str,
    app_base_url: str = "https://vett.app",
) -> tuple[str, str, str]:
    """Return (subject, html_body, plain_body)."""

    total = len(submitted) + len(manual)
    if total == 0:
        return "", "", ""

    # ── Subject ──────────────────────────────────────────────────────────────
    subject = (
        f"Vett applied to {total} job{'s' if total != 1 else ''} for you today"
        if submitted
        else f"You have {total} application{'s' if total != 1 else ''} that need your attention"
    )

    # ── Plain text ───────────────────────────────────────────────────────────
    lines: list[str] = [
        f"Hi {first_name},",
        "",
    ]

    if submitted:
        count = len(submitted)
        lines.append(
            f"Vett submitted {count} application{'s' if count != 1 else ''} on your behalf today. "
            "Here is where you stand:"
        )
        lines.append("")
        for app in submitted:
            lines.append(f"  {app.job_title} at {app.company}")
            if app.job_url:
                lines.append(f"  View job: {app.job_url}")
            lines.append("")

    if manual:
        lines.append(
            "These ones need a quick finish from you. "
            "The application form couldn't be auto-filled, so Vett has prepared everything you need:"
        )
        lines.append("")
        for app in manual:
            lines.append(f"  {app.job_title} at {app.company}")
            fallback_link = f"{app_base_url}/fallback/{app.application_id}"
            lines.append(f"  Open your pack: {fallback_link}")
            lines.append("")

    lines += [
        f"Your next briefing arrives {next_briefing}.",
        "",
        "Good luck,",
        "The Vett team",
    ]

    plain = "\n".join(lines)

    # ── HTML ─────────────────────────────────────────────────────────────────
    def _submitted_rows() -> str:
        rows = []
        for app in submitted:
            link = (
                f'<a href="{app.job_url}" style="color:#6aa9ff;text-decoration:none;">'
                f"View job"
                f"</a>"
                if app.job_url else ""
            )
            rows.append(f"""
              <tr>
                <td style="padding:12px 0;border-bottom:1px solid #1a2540;">
                  <div style="font-size:15px;font-weight:500;color:#eef2f8;">{app.job_title}</div>
                  <div style="font-size:13px;color:#8b97ad;margin-top:2px;">{app.company}</div>
                  {"<div style='margin-top:6px;'>" + link + "</div>" if link else ""}
                </td>
              </tr>""")
        return "\n".join(rows)

    def _manual_rows() -> str:
        rows = []
        for app in manual:
            fallback_link = f"{app_base_url}/fallback/{app.application_id}"
            rows.append(f"""
              <tr>
                <td style="padding:12px 0;border-bottom:1px solid #1a2540;">
                  <div style="font-size:15px;font-weight:500;color:#eef2f8;">{app.job_title}</div>
                  <div style="font-size:13px;color:#8b97ad;margin-top:2px;">{app.company}</div>
                  <div style="margin-top:6px;">
                    <a href="{fallback_link}"
                       style="color:#ffb878;text-decoration:none;font-size:13px;">
                      Open your pack
                    </a>
                  </div>
                </td>
              </tr>""")
        return "\n".join(rows)

    submitted_section = ""
    if submitted:
        submitted_section = f"""
        <p style="font-size:15px;color:#eef2f8;line-height:1.6;margin:0 0 16px;">
          Vett submitted {len(submitted)} application{"s" if len(submitted) != 1 else ""} on your behalf today.
          Here is where you stand:
        </p>
        <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:28px;">
          {_submitted_rows()}
        </table>"""

    manual_section = ""
    if manual:
        manual_section = f"""
        <div style="background:#0e1c33;border-radius:12px;padding:20px 24px;margin-bottom:28px;">
          <p style="font-size:13px;font-weight:600;letter-spacing:0.08em;color:#ffb878;
                    margin:0 0 4px;text-transform:uppercase;">These need your touch</p>
          <p style="font-size:14px;color:#8b97ad;margin:0 0 16px;line-height:1.5;">
            The application form couldn{"'"}t be auto-filled. Vett has your cover note and
            key points ready. It should take under two minutes.
          </p>
          <table width="100%" cellpadding="0" cellspacing="0">
            {_manual_rows()}
          </table>
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{subject}</title>
</head>
<body style="margin:0;padding:0;background:#060d1a;font-family:-apple-system,BlinkMacSystemFont,
             'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#060d1a;padding:40px 0;">
    <tr>
      <td align="center">
        <table width="560" cellpadding="0" cellspacing="0"
               style="max-width:560px;width:100%;background:#0a1426;border-radius:16px;
                      border:1px solid rgba(255,255,255,0.06);overflow:hidden;">

          <!-- Header -->
          <tr>
            <td style="padding:28px 32px 20px;border-bottom:1px solid rgba(255,255,255,0.06);">
              <span style="font-size:22px;font-weight:700;letter-spacing:-0.5px;color:#eef2f8;">vett</span>
            </td>
          </tr>

          <!-- Body -->
          <tr>
            <td style="padding:28px 32px 8px;">
              <p style="font-size:17px;font-weight:500;color:#eef2f8;margin:0 0 20px;line-height:1.4;">
                Hi {first_name},
              </p>

              {submitted_section}
              {manual_section}

              <p style="font-size:13px;color:#5a6580;margin:24px 0 0;line-height:1.6;">
                Your next briefing arrives {next_briefing}.
              </p>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="padding:20px 32px 28px;border-top:1px solid rgba(255,255,255,0.06);margin-top:24px;">
              <p style="font-size:12px;color:#5a6580;margin:0;line-height:1.6;">
                You're receiving this because Vett is applying to jobs on your behalf.
                To stop email digests, open Vett and turn them off in your profile.
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

    return subject, html, plain


# ── Public send function ──────────────────────────────────────────────────────

async def send_application_digest(
    user_email: str,
    user_name: Optional[str],
    applications: list[ApplicationDigestItem],
    notification_time: Optional[str] = None,
) -> bool:
    """
    Send the daily application digest email via SendGrid.

    Returns True if accepted by SendGrid, False on any error.
    Never raises — failures are logged and swallowed so the scanner continues.

    applications should contain ALL applications submitted in the current
    scan cycle (status = submitted | manual_required | applied).
    Failed applications are silently excluded from the email.
    """
    settings = get_settings()
    if not settings.sendgrid_api_key or not settings.sendgrid_api_key.startswith("SG."):
        logger.warning(
            "SENDGRID_API_KEY not configured — skipping digest email for %s", user_email
        )
        return False

    # Split by outcome
    submitted = [a for a in applications if a.status in ("submitted", "applied")]
    manual    = [a for a in applications if a.status == "manual_required"]
    # Silently drop pure failures — don't mention them in the email

    if not submitted and not manual:
        logger.debug("No applications to report for %s — skipping digest", user_email)
        return False

    first_name = _first_name(user_name, user_email)
    next_briefing = _time_label(notification_time)
    subject, html, plain = _build_email(first_name, submitted, manual, next_briefing)

    if not subject:
        return False

    payload = {
        "personalizations": [{"to": [{"email": user_email}]}],
        "from": {
            "email": settings.sendgrid_from_email,
            "name": settings.sendgrid_from_name,
        },
        "subject": subject,
        "content": [
            {"type": "text/plain", "value": plain},
            {"type": "text/html",  "value": html},
        ],
    }

    headers = {
        "Authorization": f"Bearer {settings.sendgrid_api_key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(_SENDGRID_URL, json=payload, headers=headers)
            if resp.status_code == 202:
                logger.info(
                    "Digest email sent to %s (%d submitted, %d manual)",
                    user_email, len(submitted), len(manual),
                )
                return True
            logger.warning(
                "SendGrid returned %d for %s: %s",
                resp.status_code, user_email, resp.text[:200],
            )
            return False
    except Exception as exc:
        logger.warning("Digest email failed for %s (%s): %s", user_email, type(exc).__name__, exc)
        return False
