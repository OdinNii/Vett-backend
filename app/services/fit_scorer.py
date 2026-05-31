"""
Fit scoring engine — 4 dimensions.

Dimension weights (sum = 100):
  Skills       40%
  Experience   25%
  Location     20%
  Salary       15%

Score range: 0–100 per dimension, weighted to overall.
Jobs scoring below the user's min_fit_score threshold are excluded from the feed.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.user import UserProfile
    from app.models.job import Job


WEIGHTS = {
    "skills": 0.40,
    "experience": 0.25,
    "location": 0.20,
    "salary": 0.15,
}

LEVEL_ORDER = ["junior", "mid", "senior", "lead", "head"]


@dataclass
class FitResult:
    overall: int
    skills_score: int
    experience_score: int
    location_score: int
    salary_score: int
    matched_skills: list[str]
    missing_skills: list[str]
    reason: str


def _skills_score(profile: "UserProfile", job: "Job") -> tuple[int, list[str], list[str]]:
    user_skills = {s.lower() for s in (profile.skills or [])}
    job_skills = {s.lower() for s in (job.required_skills or [])}

    # Neutral score when either side has no skill data — don't penalise users
    # who haven't uploaded a CV yet, or jobs with no explicit skill requirements.
    if not job_skills or not user_skills:
        return 70, [], []

    matched = sorted(user_skills & job_skills)
    missing = sorted(job_skills - user_skills)
    score = int(len(matched) / len(job_skills) * 100)
    return min(score, 100), matched, missing


def _experience_score(profile: "UserProfile", job: "Job") -> int:
    user_level = (profile.experience_level or "mid").lower()
    job_level = (job.experience_level or "").lower()
    user_years = profile.experience_years or 0
    job_years_min = job.experience_years_min or 0

    # Years match
    years_score = 100
    if job_years_min > 0:
        if user_years >= job_years_min:
            years_score = 100
        elif user_years >= job_years_min - 1:
            years_score = 75  # one year short — still viable
        elif user_years >= job_years_min - 2:
            years_score = 50
        else:
            years_score = 20

    # Level match
    level_score = 100
    if job_level and job_level in LEVEL_ORDER and user_level in LEVEL_ORDER:
        user_idx = LEVEL_ORDER.index(user_level)
        job_idx = LEVEL_ORDER.index(job_level)
        diff = abs(user_idx - job_idx)
        level_score = max(0, 100 - diff * 30)

    return int((years_score + level_score) / 2)


def _location_score(profile: "UserProfile", job: "Job") -> int:
    user_pref = (profile.remote_preference or "any").lower()
    job_remote = job.is_remote

    if user_pref == "remote":
        return 100 if job_remote else 30
    elif user_pref == "onsite":
        return 100 if not job_remote else 40
    elif user_pref == "hybrid":
        return 80 if job_remote else 70
    else:  # "any"
        return 85

    # Country match (if user has country and job has country)
    # Both remote → ignore country


def _salary_score(profile: "UserProfile", job: "Job") -> int:
    user_min = profile.salary_min
    user_max = profile.salary_max
    job_min = job.salary_min
    job_max = job.salary_max

    # If either side has no salary data — neutral
    if not (user_min or user_max) or not (job_min or job_max):
        return 75

    job_mid = ((job_min or 0) + (job_max or job_min or 0)) / 2
    user_mid = ((user_min or 0) + (user_max or user_min or 0)) / 2

    if user_mid == 0:
        return 75

    ratio = job_mid / user_mid
    if ratio >= 1.0:
        return 100  # job pays at or above expectation
    elif ratio >= 0.85:
        return 80
    elif ratio >= 0.70:
        return 55
    elif ratio >= 0.55:
        return 30
    return 10


def _build_reason(
    profile: "UserProfile",
    job: "Job",
    matched_skills: list[str],
    missing_skills: list[str],
    overall: int,
) -> str:
    if overall >= 85:
        if matched_skills:
            top = ", ".join(matched_skills[:3])
            return f"Strong match — your {top} experience aligns directly with this role."
        return "Strong profile match across all dimensions."
    elif overall >= 70:
        if missing_skills:
            gap = missing_skills[0]
            return f"Good fit. You're missing {gap} — everything else lines up well."
        return "Good match overall with solid experience alignment."
    elif overall >= 60:
        gaps = ", ".join(missing_skills[:2]) if missing_skills else "a few areas"
        return f"Moderate fit — skill gaps in {gaps}, but your experience is relevant."
    return "Stretch role — significant gaps, but transferable skills may help."


def score_job_for_user(profile: "UserProfile", job: "Job") -> FitResult:
    skills_s, matched, missing = _skills_score(profile, job)
    exp_s = _experience_score(profile, job)
    loc_s = _location_score(profile, job)
    sal_s = _salary_score(profile, job)

    overall = int(
        skills_s * WEIGHTS["skills"]
        + exp_s * WEIGHTS["experience"]
        + loc_s * WEIGHTS["location"]
        + sal_s * WEIGHTS["salary"]
    )

    reason = _build_reason(profile, job, matched, missing, overall)

    return FitResult(
        overall=overall,
        skills_score=skills_s,
        experience_score=exp_s,
        location_score=loc_s,
        salary_score=sal_s,
        matched_skills=matched,
        missing_skills=missing,
        reason=reason,
    )
