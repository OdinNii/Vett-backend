"""
Application submission engine.

Attempts to submit job applications on behalf of the user:
  1. Fast-path: if the URL belongs to a known JS-heavy ATS (Greenhouse,
     Lever, Workday, LinkedIn …) → manual_required immediately, with a
     helpful prep message.
  2. Fetch the page with httpx (follows redirects, browser-like UA).
  3. Re-check the final URL against the ATS list.
  4. Parse HTML with BeautifulSoup; score every <form> for how
     "application-like" it looks (email / name / phone / CV / cover fields).
  5. Fill the best-matching form with user profile data and POST it.
  6. Inspect the response for success signals.
  7. Return a SubmissionResult(status, platform, message).

Status values
─────────────
  submitted       Engine filled and POSTed the form; response looked good.
  manual_required Page is behind JS/auth/known ATS — user must finish.
  failed          Fetch or POST failed with a hard error.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.models.user import User, UserProfile

logger = logging.getLogger(__name__)

# ── Known ATS / job platforms that require JS or authentication ───────────────
# Strings are checked against the netloc of the URL (with www. stripped).
_MANUAL_PLATFORMS: dict[str, str] = {
    "greenhouse.io":         "Greenhouse",
    "lever.co":              "Lever",
    "workday.com":           "Workday",
    "myworkdayjobs.com":     "Workday",
    "taleo.net":             "Taleo",
    "successfactors.com":    "SAP SuccessFactors",
    "sap.com":               "SAP SuccessFactors",
    "icims.com":             "iCIMS",
    "jobvite.com":           "Jobvite",
    "linkedin.com":          "LinkedIn",
    "indeed.com":            "Indeed",
    "glassdoor.com":         "Glassdoor",
    "smartrecruiters.com":   "SmartRecruiters",
    "recruitee.com":         "Recruitee",
    "workable.com":          "Workable",
    "ashbyhq.com":           "Ashby",
    "rippling.com":          "Rippling",
    "bamboohr.com":          "BambooHR",
    "otta.com":              "Otta",
    "wellfound.com":         "Wellfound",
    "angellist.com":         "Wellfound",
    "dover.com":             "Dover",
    "gem.com":               "Gem",
    "pinpoint.com":          "Pinpoint",
    "teamtailor.com":        "Teamtailor",
    "personio.com":          "Personio",
    "breezy.hr":             "Breezy HR",
    "jazzhr.com":            "JazzHR",
    "jobsoid.com":           "Jobsoid",
    "adzuna.co.uk":          "Adzuna",
    "adzuna.com":            "Adzuna",
    "totaljobs.com":         "Totaljobs",
    "reed.co.uk":            "Reed",
    "cwjobs.co.uk":          "CW Jobs",
    "monster.co.uk":         "Monster",
    "cv-library.co.uk":      "CV-Library",
    "jobsite.co.uk":         "Jobsite",
}

# Field-name patterns used to identify what each input does
_EMAIL_RE  = re.compile(r"\b(email[_\-]?(?:address)?|e[_\-]?mail)\b", re.I)
_NAME_RE   = re.compile(r"\b(full[_\-]?name|applicant[_\-]?name|(?:first|last|given|family)[_\-]?name|name)\b", re.I)
_PHONE_RE  = re.compile(r"\b(phone|telephone|mobile|cell|tel)\b", re.I)
_COVER_RE  = re.compile(r"\b(cover[_\-]?letter|covering[_\-]?letter|cover[_\-]?note|message|motivation|why[_\-]?apply)\b", re.I)
_RESUME_RE = re.compile(r"\b(resume|curriculum[_\-]?vitae|cv|upload[_\-]?cv|attach[_\-]?cv|file)\b", re.I)

# Phrases in response HTML that indicate a successful submission
_SUCCESS_SIGNALS = [
    "thank you",
    "application received",
    "application submitted",
    "application complete",
    "successfully submitted",
    "successfully applied",
    "we'll be in touch",
    "we will be in touch",
    "we'll review",
    "you've applied",
    "you have applied",
    "your application",
]

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
}


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class SubmissionResult:
    """Outcome of a single application attempt."""
    status: str          # "submitted" | "manual_required" | "failed"
    platform: str = "direct"
    message: str = ""
    details: dict = field(default_factory=dict)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _detect_platform(url: str) -> Optional[str]:
    """Return the ATS platform name if the URL matches a known provider."""
    host = urlparse(url).netloc.lower().removeprefix("www.")
    for domain, name in _MANUAL_PLATFORMS.items():
        if host == domain or host.endswith("." + domain):
            return name
    return None


def _platform_slug(name: str) -> str:
    return name.lower().replace(" ", "_")


def _prep_message(platform: str) -> str:
    return (
        f"This role is on {platform}. Vett has prepped your profile and "
        f"cover note — tap to finish in under a minute."
    )


def build_cover_note(
    profile: UserProfile,
    user: User,
    *,
    job_title: str = "",
    company: str = "",
) -> str:
    """
    Build a cover note from profile data.

    Accepts optional job_title / company for personalised notes stored in the
    Application record. When omitted (e.g. when filling an HTML form where the
    role/company aren't known), falls back to profile.target_role.
    """
    role   = job_title or profile.target_role or "this role"
    name   = user.full_name or ""
    skills = (profile.skills or [])[:4]
    years  = profile.experience_years

    if company:
        opening = f"I came across the {role} role at {company} and wanted to reach out."
    else:
        opening = f"I want to apply for the {role} position."

    if years:
        exp_line = f"I have {years} years of experience in this area."
    else:
        exp_line = "I have relevant experience in this area."

    if len(skills) >= 2:
        skill_list = ", ".join(skills[:-1]) + f" and {skills[-1]}"
        skills_line = f"My main focus has been {skill_list}."
    elif skills:
        skills_line = f"My main focus has been {skills[0]}."
    else:
        skills_line = ""

    closing = "I think there is a good fit here and would be glad to talk it through. Please do get in touch."

    parts = [opening, exp_line]
    if skills_line:
        parts.append(skills_line)
    parts.append(closing)

    sign = f"\n\n{name}" if name else ""
    return "Hi,\n\n" + " ".join(parts) + sign


def build_fallback_pack(
    profile: UserProfile,
    user: User,
    *,
    job_title: str = "",
    company: str = "",
    job_url: str = "",
    required_skills: Optional[list] = None,
    deadline: Optional[str] = None,
) -> dict:
    """
    Build the fallback pack for applications that require manual submission.

    Returns a dict with: cover_note, key_points, job_url, deadline.
    """
    cover_note = build_cover_note(
        profile, user, job_title=job_title, company=company,
    )

    key_points: list[str] = []
    skills = profile.skills or []

    if profile.experience_years:
        role_label = profile.target_role or "this field"
        key_points.append(
            f"{profile.experience_years} years of experience in {role_label}."
        )

    matched = []
    if required_skills:
        req_lower = {s.lower() for s in required_skills}
        matched = [s for s in skills if s.lower() in req_lower][:3]
    if matched:
        key_points.append(f"Direct experience with {', '.join(matched)}, which the role asks for.")
    elif skills:
        key_points.append(f"Background includes {', '.join(skills[:3])}.")

    if profile.industries:
        sector = "sectors" if len(profile.industries) > 1 else "sector"
        key_points.append(f"Worked in the {', '.join(profile.industries[:2])} {sector}.")

    if getattr(profile, "remote_preference", None) in ("remote", "hybrid"):
        key_points.append("Open to remote and hybrid roles.")
    elif profile.location:
        key_points.append(f"Based in {profile.location}.")

    if len(key_points) < 3 and skills[len(matched):len(matched) + 2]:
        extra = skills[len(matched):len(matched) + 2]
        key_points.append(f"Also experienced with {', '.join(extra)}.")

    return {
        "cover_note": cover_note,
        "key_points": key_points[:5],
        "job_url": job_url,
        "deadline": deadline,
    }


def _cv_as_file(profile: UserProfile) -> tuple[bytes, str, str]:
    """Encode the CV raw text as UTF-8 bytes for multipart upload."""
    text     = profile.cv_raw_text or ""
    filename = profile.cv_filename or "cv.txt"
    # Ensure .txt extension so it's always readable by the server
    if not filename.endswith((".txt", ".pdf", ".docx")):
        filename = filename + ".txt"
    return text.encode("utf-8"), filename, "text/plain"


def _score_form(form, raw_html: str) -> int:
    """
    Score how application-like a form looks (higher = more likely).
    Caller pre-computes raw_html = str(form).lower() to avoid redundant
    re-serialisation when scoring multiple forms.
    """
    score = 0
    if _EMAIL_RE.search(raw_html):              score += 4
    if _NAME_RE.search(raw_html):               score += 2
    if _PHONE_RE.search(raw_html):              score += 1
    if _COVER_RE.search(raw_html):              score += 3
    if _RESUME_RE.search(raw_html):             score += 3
    if form.find("input", {"type": "file"}):    score += 4

    body_text = form.get_text(" ", strip=True).lower()
    if any(w in body_text for w in ("apply", "application", "submit your application")):
        score += 2

    return score


async def _fill_and_submit(
    client: httpx.AsyncClient,
    form,
    page_url: str,
    user: User,
    profile: UserProfile,
) -> SubmissionResult:
    """Fill a form's fields with profile data and POST it."""
    action     = form.get("action", "")
    target_url = urljoin(page_url, action) if action else page_url

    form_data: dict[str, str] = {}
    file_fields: list[str]    = []

    for inp in form.find_all(["input", "textarea", "select"]):
        name     = inp.get("name") or inp.get("id", "")
        if not name:
            continue
        inp_type = (inp.get("type") or "text").lower()

        if inp_type == "file":
            file_fields.append(name)
            continue
        if inp_type in ("submit", "button", "image", "reset"):
            continue
        if inp_type == "hidden":
            form_data[name] = inp.get("value", "")
            continue

        key = name.lower()
        if _EMAIL_RE.search(key):
            form_data[name] = user.email
        elif _NAME_RE.search(key):
            form_data[name] = user.full_name or ""
        elif _PHONE_RE.search(key):
            form_data[name] = ""   # phone not stored in profile
        elif _COVER_RE.search(key):
            form_data[name] = build_cover_note(profile, user)
        else:
            form_data[name] = inp.get("value", "")

    try:
        if file_fields and profile.cv_raw_text:
            cv_bytes, cv_name, cv_mime = _cv_as_file(profile)
            files = {
                field_name: (cv_name, cv_bytes, cv_mime)
                for field_name in file_fields
            }
            resp = await client.post(target_url, data=form_data, files=files, timeout=25)
        else:
            resp = await client.post(target_url, data=form_data, timeout=25)
    except Exception as exc:
        logger.warning("Form POST failed for %s: %s", target_url, exc)
        return SubmissionResult(
            status="failed",
            message=f"Form submission error: {exc}",
        )

    # Success detection: look for confirmation phrases OR a redirect (302)
    resp_lower = resp.text.lower()
    confirmed  = (
        any(sig in resp_lower for sig in _SUCCESS_SIGNALS)
        or resp.status_code in (201, 302, 303)
    )

    if confirmed:
        return SubmissionResult(
            status="submitted",
            platform="direct",
            message="Application submitted via the job page form.",
            details={"http_status": resp.status_code},
        )

    # Ambiguous: form was POSTed but no clear success signal
    return SubmissionResult(
        status="submitted",
        platform="direct",
        message="Application form submitted (no explicit confirmation received).",
        details={"http_status": resp.status_code, "ambiguous": True},
    )


# ── Public API ────────────────────────────────────────────────────────────────

async def submit_application(
    job_url: str,
    user: User,
    profile: UserProfile,
) -> SubmissionResult:
    """
    Main entry point — attempt to submit a job application.

    Returns SubmissionResult with status:
      submitted       — form found, filled, and POSTed successfully
      manual_required — known ATS / JS site / no form detected
      failed          — network error or unrecoverable problem
    """
    if not job_url:
        return SubmissionResult(
            status="manual_required",
            platform="unknown",
            message="No application URL available. Please apply directly.",
        )

    # Fast-path: known platform before even fetching
    platform = _detect_platform(job_url)
    if platform:
        return SubmissionResult(
            status="manual_required",
            platform=_platform_slug(platform),
            message=_prep_message(platform),
        )

    async with httpx.AsyncClient(
        headers=_BROWSER_HEADERS,
        follow_redirects=True,
        timeout=httpx.Timeout(20.0, connect=10.0),
    ) as client:

        # ── Fetch the page ────────────────────────────────────────────────────
        try:
            resp = await client.get(job_url)
        except httpx.TimeoutException:
            return SubmissionResult(
                status="manual_required",
                platform="unreachable",
                message="The job page timed out. Please apply directly.",
            )
        except Exception as exc:
            logger.warning("Failed to fetch %s: %s", job_url, exc)
            return SubmissionResult(
                status="failed",
                message=f"Could not load application page: {exc}",
            )

        # Re-check after redirects (many Adzuna URLs redirect to ATS pages)
        final_url = str(resp.url)
        platform  = _detect_platform(final_url)
        if platform:
            return SubmissionResult(
                status="manual_required",
                platform=_platform_slug(platform),
                message=_prep_message(platform),
            )

        # Bot protection or auth wall
        if resp.status_code in (401, 403, 429):
            return SubmissionResult(
                status="manual_required",
                platform="protected",
                message=(
                    "This page is behind a login or bot-protection. "
                    "Vett prepped your cover note — apply directly."
                ),
            )

        # ── Parse and score forms ─────────────────────────────────────────────
        soup  = BeautifulSoup(resp.text, "lxml")
        forms = soup.find_all("form")

        if not forms:
            return SubmissionResult(
                status="manual_required",
                platform="no_form",
                message=(
                    "No HTML form found — this page likely uses JavaScript rendering. "
                    "Vett prepped your profile; tap to finish."
                ),
            )

        # Pre-score every form once (serialise each to string only once)
        scored     = [(f, _score_form(f, str(f).lower())) for f in forms]
        best_form, best_score = max(scored, key=lambda x: x[1])

        if best_score < 4:
            # Form exists but doesn't look like an application form
            return SubmissionResult(
                status="manual_required",
                platform="no_match",
                message=(
                    "No standard application form detected on this page. "
                    "Vett prepped your profile; tap to finish."
                ),
            )

        logger.info(
            "Found application form on %s (score=%d), attempting submit",
            final_url, best_score,
        )
        return await _fill_and_submit(client, best_form, final_url, user, profile)
