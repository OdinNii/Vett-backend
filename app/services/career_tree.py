"""
Career tree role suggestion engine.

Builds four rings of personalised role suggestions from a user's profile:
  direct     — roles reachable right now
  adjacent   — one small step up or sideways
  stretch    — achievable in 1–2 years with effort
  peripheral — transferable-skill matches outside core craft

Returns a CareerTreeResponse (Pydantic model) ready to serialise.
"""
from __future__ import annotations

import math
from typing import Optional

from app.models.user import UserProfile
from app.schemas.user import CareerTreeNode, CareerTreeResponse

# ── Role catalogue ────────────────────────────────────────────────────────────
# Each entry: title, salary_range, required_skills (used to compute fit/have/gap)

_ROLES: dict[str, dict[str, list[dict]]] = {
    "engineering": {
        "junior": {
            "direct": [
                {"title": "Software Engineer",       "salary": "£45k – £65k", "skills": ["Python", "JavaScript", "Git", "SQL", "Testing"]},
                {"title": "Frontend Developer",      "salary": "£42k – £62k", "skills": ["React", "JavaScript", "TypeScript", "CSS"]},
                {"title": "Backend Developer",       "salary": "£45k – £68k", "skills": ["Python", "Node.js", "SQL", "REST APIs"]},
            ],
            "adjacent": [
                {"title": "QA Engineer",             "salary": "£40k – £58k", "skills": ["Testing", "Selenium", "Python", "Automation"]},
                {"title": "DevOps Engineer",         "salary": "£50k – £72k", "skills": ["Docker", "AWS", "Linux", "CI/CD"]},
                {"title": "Mobile Developer",        "salary": "£45k – £68k", "skills": ["React Native", "Swift", "Kotlin"]},
            ],
            "stretch": [
                {"title": "Senior Software Engineer","salary": "£65k – £90k", "skills": ["Architecture", "Mentoring", "Code Review", "Systems Design"]},
                {"title": "Tech Lead",               "salary": "£75k – £100k","skills": ["Leadership", "Architecture", "Mentoring", "Planning"]},
            ],
            "peripheral": [
                {"title": "Product Manager",         "salary": "£55k – £85k", "skills": ["Product Strategy", "Data Analysis", "Communication", "User Research"]},
                {"title": "UX Designer",             "salary": "£40k – £60k", "skills": ["Figma", "User Research", "Prototyping"]},
            ],
        },
        "mid": {
            "direct": [
                {"title": "Senior Software Engineer","salary": "£65k – £90k", "skills": ["Architecture", "Mentoring", "Code Review", "Systems Design", "Leadership"]},
                {"title": "Senior Backend Engineer", "salary": "£68k – £95k", "skills": ["Python", "SQL", "Microservices", "Architecture"]},
                {"title": "Senior Frontend Engineer","salary": "£65k – £90k", "skills": ["React", "TypeScript", "Performance", "Architecture"]},
                {"title": "Full Stack Engineer",     "salary": "£60k – £88k", "skills": ["React", "Node.js", "SQL", "Docker"]},
            ],
            "adjacent": [
                {"title": "Engineering Manager",     "salary": "£80k – £120k","skills": ["Leadership", "Mentoring", "Communication", "Project Management"]},
                {"title": "Platform Engineer",       "salary": "£70k – £100k","skills": ["Docker", "Kubernetes", "AWS", "CI/CD", "Terraform"]},
                {"title": "Data Engineer",           "salary": "£65k – £95k", "skills": ["Python", "SQL", "Spark", "Data Pipelines", "AWS"]},
                {"title": "Solutions Architect",     "salary": "£75k – £110k","skills": ["Architecture", "AWS", "Systems Design", "Communication"]},
            ],
            "stretch": [
                {"title": "Staff Engineer",          "salary": "£95k – £140k","skills": ["Systems Design", "Org Influence", "Architecture", "Leadership", "Mentoring"]},
                {"title": "Principal Engineer",      "salary": "£110k – £160k","skills": ["Technical Strategy", "Architecture", "Leadership", "Mentoring", "Communication"]},
            ],
            "peripheral": [
                {"title": "Product Manager",         "salary": "£65k – £100k","skills": ["Product Strategy", "Data Analysis", "Communication", "User Research"]},
                {"title": "Developer Advocate",      "salary": "£60k – £90k", "skills": ["Communication", "Python", "JavaScript", "Writing"]},
            ],
        },
        "senior": {
            "direct": [
                {"title": "Staff Engineer",          "salary": "£95k – £140k","skills": ["Systems Design", "Org Influence", "Architecture", "Leadership", "Mentoring"]},
                {"title": "Principal Engineer",      "salary": "£110k – £160k","skills": ["Technical Strategy", "Architecture", "Leadership", "Mentoring"]},
                {"title": "Senior Staff Engineer",   "salary": "£120k – £170k","skills": ["Technical Strategy", "Org Influence", "Architecture", "Leadership"]},
            ],
            "adjacent": [
                {"title": "Engineering Manager",     "salary": "£90k – £130k","skills": ["Leadership", "Mentoring", "Hiring", "Communication", "Project Management"]},
                {"title": "Director of Engineering", "salary": "£120k – £170k","skills": ["Leadership", "Strategy", "Hiring", "Org Design", "Communication"]},
                {"title": "Chief Architect",         "salary": "£120k – £180k","skills": ["Architecture", "Systems Design", "Leadership", "Strategy"]},
            ],
            "stretch": [
                {"title": "VP of Engineering",       "salary": "£160k – £250k","skills": ["Executive Leadership", "Strategy", "Org Design", "Hiring", "Communication"]},
                {"title": "CTO",                     "salary": "£180k – £350k","skills": ["Technical Vision", "Leadership", "Strategy", "Communication"]},
            ],
            "peripheral": [
                {"title": "Technical Programme Manager","salary": "£90k – £140k","skills": ["Project Management", "Communication", "Leadership", "Planning"]},
                {"title": "Head of Product",         "salary": "£110k – £160k","skills": ["Product Strategy", "Leadership", "Data Analysis", "Communication"]},
            ],
        },
    },
    "design": {
        "junior": {
            "direct": [
                {"title": "Product Designer",        "salary": "£38k – £55k", "skills": ["Figma", "User Research", "Prototyping", "UX Design"]},
                {"title": "UI Designer",             "salary": "£36k – £52k", "skills": ["Figma", "UI Design", "Typography", "Design Systems"]},
                {"title": "UX Designer",             "salary": "£38k – £56k", "skills": ["User Research", "Wireframing", "Figma", "Prototyping"]},
            ],
            "adjacent": [
                {"title": "Motion Designer",         "salary": "£38k – £55k", "skills": ["After Effects", "Animation", "Figma"]},
                {"title": "Content Designer",        "salary": "£35k – £52k", "skills": ["UX Writing", "Communication", "Figma"]},
                {"title": "Design Researcher",       "salary": "£38k – £58k", "skills": ["User Research", "Interviewing", "Synthesis", "Analysis"]},
            ],
            "stretch": [
                {"title": "Senior Product Designer", "salary": "£60k – £85k", "skills": ["Figma", "Design Systems", "User Research", "Leadership", "Mentoring"]},
                {"title": "Lead UX Designer",        "salary": "£65k – £90k", "skills": ["UX Design", "Design Systems", "Leadership", "Strategy"]},
            ],
            "peripheral": [
                {"title": "Product Manager",         "salary": "£50k – £80k", "skills": ["Product Strategy", "Data Analysis", "Communication"]},
                {"title": "Frontend Developer",      "salary": "£42k – £65k", "skills": ["React", "CSS", "JavaScript", "TypeScript"]},
            ],
        },
        "mid": {
            "direct": [
                {"title": "Senior Product Designer", "salary": "£60k – £85k", "skills": ["Figma", "Design Systems", "User Research", "Leadership", "Mentoring"]},
                {"title": "Senior UX Designer",      "salary": "£60k – £88k", "skills": ["UX Design", "User Research", "Systems Thinking", "Mentoring"]},
                {"title": "Lead Designer",           "salary": "£70k – £95k", "skills": ["Design Leadership", "Figma", "Mentoring", "Strategy"]},
            ],
            "adjacent": [
                {"title": "UX Research Lead",        "salary": "£65k – £95k", "skills": ["User Research", "Research Methods", "Leadership", "Synthesis"]},
                {"title": "Design Engineer",         "salary": "£65k – £95k", "skills": ["React", "TypeScript", "Figma", "Design Systems"]},
                {"title": "Product Manager",         "salary": "£70k – £100k","skills": ["Product Strategy", "Data Analysis", "Communication", "User Research"]},
            ],
            "stretch": [
                {"title": "Staff Designer",          "salary": "£95k – £140k","skills": ["Systems Thinking", "Org Influence", "Design Leadership", "Mentoring"]},
                {"title": "Head of Design",          "salary": "£100k – £150k","skills": ["Design Leadership", "Hiring", "Strategy", "Vision", "Mentoring"]},
            ],
            "peripheral": [
                {"title": "Creative Director",       "salary": "£80k – £130k","skills": ["Creative Direction", "Visual Craft", "Leadership", "Brand Strategy"]},
                {"title": "Founding Designer",       "salary": "£75k – £130k + equity","skills": ["Product Design", "Speed", "Range", "Communication"]},
            ],
        },
        "senior": {
            "direct": [
                {"title": "Staff Designer",          "salary": "£95k – £140k","skills": ["Systems Thinking", "Org Influence", "Design Leadership", "Mentoring"]},
                {"title": "Head of Design",          "salary": "£100k – £150k","skills": ["Design Leadership", "Hiring", "Strategy", "Vision"]},
                {"title": "Principal Designer",      "salary": "£100k – £145k","skills": ["Design Strategy", "Systems Thinking", "Org Influence", "Mentoring"]},
            ],
            "adjacent": [
                {"title": "Design Director",         "salary": "£110k – £160k","skills": ["Design Leadership", "Strategy", "Hiring", "Vision", "Communication"]},
                {"title": "VP of Design",            "salary": "£140k – £220k","skills": ["Executive Leadership", "Strategy", "Hiring", "Vision"]},
                {"title": "Chief Design Officer",    "salary": "£180k – £300k","skills": ["Executive Leadership", "Vision", "Strategy", "Communication"]},
            ],
            "stretch": [
                {"title": "VP of Product",           "salary": "£150k – £240k","skills": ["Product Strategy", "Leadership", "Data Analysis", "Communication"]},
                {"title": "Chief Product Officer",   "salary": "£180k – £350k","skills": ["Product Vision", "Executive Leadership", "Strategy"]},
            ],
            "peripheral": [
                {"title": "Creative Director (Agency)","salary": "£90k – £150k","skills": ["Creative Direction", "Visual Craft", "Leadership", "Pitching"]},
                {"title": "Founder",                 "salary": "Equity-heavy", "skills": ["Vision", "Leadership", "Communication", "Fundraising"]},
            ],
        },
    },
    "product": {
        "junior": {
            "direct": [
                {"title": "Product Manager",         "salary": "£50k – £75k", "skills": ["Product Strategy", "User Research", "Data Analysis", "Communication", "Agile"]},
                {"title": "Associate PM",            "salary": "£45k – £65k", "skills": ["Product Strategy", "Communication", "Agile", "Analysis"]},
            ],
            "adjacent": [
                {"title": "Product Analyst",         "salary": "£42k – £62k", "skills": ["Data Analysis", "SQL", "Python", "Communication"]},
                {"title": "Business Analyst",        "salary": "£42k – £62k", "skills": ["Analysis", "SQL", "Communication", "Requirements"]},
                {"title": "Project Manager",         "salary": "£45k – £68k", "skills": ["Project Management", "Communication", "Planning", "Agile"]},
            ],
            "stretch": [
                {"title": "Senior Product Manager",  "salary": "£75k – £110k","skills": ["Product Strategy", "Leadership", "Data Analysis", "Mentoring", "Roadmap"]},
            ],
            "peripheral": [
                {"title": "Product Designer",        "salary": "£42k – £65k", "skills": ["Figma", "User Research", "Prototyping"]},
                {"title": "Scrum Master",            "salary": "£50k – £70k", "skills": ["Agile", "Communication", "Coaching", "Facilitation"]},
            ],
        },
        "mid": {
            "direct": [
                {"title": "Senior Product Manager",  "salary": "£75k – £110k","skills": ["Product Strategy", "Leadership", "Data Analysis", "Mentoring", "Roadmap"]},
                {"title": "Group Product Manager",   "salary": "£90k – £130k","skills": ["Product Strategy", "Leadership", "Mentoring", "Roadmap", "Communication"]},
            ],
            "adjacent": [
                {"title": "Head of Product",         "salary": "£100k – £140k","skills": ["Product Leadership", "Strategy", "Hiring", "Roadmap", "Communication"]},
                {"title": "Growth PM",               "salary": "£80k – £120k","skills": ["Data Analysis", "Experimentation", "Product Strategy", "SQL"]},
                {"title": "Platform PM",             "salary": "£80k – £115k","skills": ["Technical Understanding", "Product Strategy", "APIs", "Communication"]},
            ],
            "stretch": [
                {"title": "Director of Product",     "salary": "£120k – £170k","skills": ["Product Leadership", "Strategy", "Hiring", "Executive Communication", "Vision"]},
                {"title": "VP of Product",           "salary": "£150k – £220k","skills": ["Executive Leadership", "Product Vision", "Strategy", "Org Design"]},
            ],
            "peripheral": [
                {"title": "Startup Founder",         "salary": "Equity-heavy", "skills": ["Vision", "Leadership", "Communication", "Fundraising"]},
                {"title": "Venture Associate",       "salary": "£70k – £100k","skills": ["Analysis", "Communication", "Strategy", "Networking"]},
            ],
        },
        "senior": {
            "direct": [
                {"title": "Director of Product",     "salary": "£120k – £170k","skills": ["Product Leadership", "Strategy", "Hiring", "Vision"]},
                {"title": "Head of Product",         "salary": "£110k – £160k","skills": ["Product Leadership", "Strategy", "Hiring", "Communication"]},
                {"title": "Group PM",                "salary": "£100k – £145k","skills": ["Product Strategy", "Leadership", "Mentoring", "Roadmap"]},
            ],
            "adjacent": [
                {"title": "VP of Product",           "salary": "£150k – £220k","skills": ["Executive Leadership", "Product Vision", "Strategy", "Org Design"]},
                {"title": "Chief Product Officer",   "salary": "£180k – £300k","skills": ["Product Vision", "Executive Leadership", "Strategy"]},
                {"title": "General Manager",         "salary": "£130k – £200k","skills": ["Leadership", "P&L Management", "Strategy", "Communication", "Operations"]},
            ],
            "stretch": [
                {"title": "CEO / Co-Founder",        "salary": "Equity-heavy", "skills": ["Vision", "Leadership", "Fundraising", "Communication"]},
                {"title": "Operating Partner",       "salary": "£150k – £250k","skills": ["Strategy", "Leadership", "Analysis", "Communication"]},
            ],
            "peripheral": [
                {"title": "Consultant (Product)",    "salary": "£900 – £1.5k/day","skills": ["Communication", "Strategy", "Analysis", "Domain Expertise"]},
                {"title": "Chief of Staff",          "salary": "£100k – £160k","skills": ["Communication", "Strategy", "Analysis", "Project Management"]},
            ],
        },
    },
    "data": {
        "junior": {
            "direct": [
                {"title": "Data Analyst",            "salary": "£35k – £52k", "skills": ["SQL", "Python", "Excel", "Data Visualisation", "Statistics"]},
                {"title": "BI Analyst",              "salary": "£38k – £55k", "skills": ["SQL", "Tableau", "Power BI", "Excel", "Reporting"]},
            ],
            "adjacent": [
                {"title": "Data Engineer",           "salary": "£45k – £65k", "skills": ["Python", "SQL", "Spark", "Data Pipelines", "AWS"]},
                {"title": "Analytics Engineer",      "salary": "£45k – £65k", "skills": ["dbt", "SQL", "Python", "Data Modelling"]},
            ],
            "stretch": [
                {"title": "Senior Data Analyst",     "salary": "£55k – £80k", "skills": ["SQL", "Python", "Statistics", "Mentoring", "Leadership"]},
                {"title": "Data Scientist",          "salary": "£55k – £80k", "skills": ["Python", "Machine Learning", "Statistics", "SQL"]},
            ],
            "peripheral": [
                {"title": "Product Analyst",         "salary": "£40k – £60k", "skills": ["SQL", "Python", "Product Metrics", "A/B Testing"]},
                {"title": "Quantitative Researcher", "salary": "£60k – £100k","skills": ["Statistics", "Python", "R", "Research"]},
            ],
        },
        "mid": {
            "direct": [
                {"title": "Senior Data Scientist",   "salary": "£70k – £100k","skills": ["Machine Learning", "Python", "Statistics", "SQL", "Communication"]},
                {"title": "Senior Data Analyst",     "salary": "£60k – £85k", "skills": ["SQL", "Python", "Statistics", "Mentoring", "Leadership"]},
                {"title": "ML Engineer",             "salary": "£75k – £110k","skills": ["Python", "Machine Learning", "MLOps", "Docker", "AWS"]},
            ],
            "adjacent": [
                {"title": "Data Engineering Manager","salary": "£90k – £130k","skills": ["Leadership", "Python", "SQL", "Data Pipelines", "Mentoring"]},
                {"title": "Analytics Manager",       "salary": "£80k – £120k","skills": ["Leadership", "SQL", "Python", "Communication", "Mentoring"]},
                {"title": "Research Scientist",      "salary": "£80k – £120k","skills": ["Machine Learning", "Research", "Python", "Mathematics"]},
            ],
            "stretch": [
                {"title": "Head of Data",            "salary": "£110k – £160k","skills": ["Leadership", "Strategy", "Hiring", "Data Architecture", "Communication"]},
                {"title": "Principal Data Scientist","salary": "£100k – £150k","skills": ["Machine Learning", "Research", "Leadership", "Org Influence"]},
            ],
            "peripheral": [
                {"title": "Quant Researcher",        "salary": "£100k – £200k","skills": ["Statistics", "Python", "Mathematics", "Finance"]},
                {"title": "AI Product Manager",      "salary": "£80k – £120k","skills": ["Product Strategy", "Machine Learning", "Communication", "Data Analysis"]},
            ],
        },
        "senior": {
            "direct": [
                {"title": "Principal Data Scientist","salary": "£100k – £150k","skills": ["Machine Learning", "Research", "Leadership", "Org Influence"]},
                {"title": "Head of Data Science",    "salary": "£120k – £170k","skills": ["Leadership", "Strategy", "Hiring", "Machine Learning"]},
                {"title": "Staff ML Engineer",       "salary": "£110k – £160k","skills": ["Machine Learning", "MLOps", "Systems Design", "Leadership"]},
            ],
            "adjacent": [
                {"title": "Director of Data",        "salary": "£130k – £185k","skills": ["Leadership", "Strategy", "Hiring", "Data Architecture", "Communication"]},
                {"title": "VP of Data",              "salary": "£160k – £240k","skills": ["Executive Leadership", "Strategy", "Org Design", "Communication"]},
                {"title": "Chief AI Officer",        "salary": "£180k – £300k","skills": ["AI Strategy", "Leadership", "Communication", "Technical Vision"]},
            ],
            "stretch": [
                {"title": "CTO (AI focus)",          "salary": "£200k – £400k","skills": ["Technical Vision", "Leadership", "AI Strategy", "Communication"]},
                {"title": "AI Research Director",    "salary": "£160k – £280k","skills": ["Research", "Machine Learning", "Leadership", "Communication"]},
            ],
            "peripheral": [
                {"title": "Startup Founder (AI)",    "salary": "Equity-heavy", "skills": ["Vision", "Machine Learning", "Communication", "Fundraising"]},
                {"title": "VC Principal (Deep Tech)","salary": "£120k – £200k","skills": ["Analysis", "Communication", "Strategy", "Technical Depth"]},
            ],
        },
    },
}

# Generic fallback for unknown crafts
_FALLBACK_ROLES = _ROLES["engineering"]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _detect_craft(target_role: Optional[str], skills: list[str]) -> str:
    role_lower = (target_role or "").lower()
    if any(w in role_lower for w in ("engineer", "developer", "dev ", "software", "frontend", "backend", "fullstack")):
        return "engineering"
    if any(w in role_lower for w in ("design", "ux", "ui ", "creative")):
        return "design"
    if any(w in role_lower for w in ("product manager", " pm ", "product lead")):
        return "product"
    if any(w in role_lower for w in ("data", "analyst", "scientist", "machine learning", "ml ", "ai ")):
        return "data"
    # Skill-based fallback
    skill_lower = {s.lower() for s in skills}
    if {"figma", "ux design", "prototyping"} & skill_lower:
        return "design"
    if {"python", "javascript", "react", "typescript"} & skill_lower:
        return "engineering"
    if {"sql", "tableau", "power bi"} & skill_lower:
        return "data"
    return "engineering"


def _normalise_level(experience_level: Optional[str]) -> str:
    lvl = (experience_level or "mid").lower()
    if lvl in ("junior", "graduate", "entry"):
        return "junior"
    if lvl in ("senior", "lead", "staff", "principal", "head", "director", "vp", "c-suite"):
        return "senior"
    return "mid"


def _compute_fit(user_skills: set[str], required: list[str]) -> tuple[int, list[str], list[str]]:
    """Return (fit_pct, have_skills, gap_skills)."""
    if not required:
        return 50, [], []
    req_lower = {s.lower(): s for s in required}
    have = [req_lower[s.lower()] for s in user_skills if s.lower() in req_lower]
    gap  = [s for s in required if s.lower() not in {x.lower() for x in user_skills}]
    fit  = int(round(len(have) / len(required) * 100))
    return fit, have[:4], gap[:3]


def _assign_angles(
    nodes: list[dict],
    ring: str,
    user_skills: set[str],
    r: float,
    start_angle: float = -90.0,
) -> list[CareerTreeNode]:
    """Convert raw role dicts to positioned CareerTreeNode objects."""
    n = len(nodes)
    if n == 0:
        return []
    step = 360.0 / n if n > 1 else 0
    result: list[CareerTreeNode] = []
    for i, role in enumerate(nodes):
        fit, have, gap = _compute_fit(user_skills, role["skills"])
        # Slightly randomise base angle per ring to avoid overlap
        ring_offsets = {"direct": 0, "adjacent": 25, "stretch": 45, "peripheral": 15}
        angle = start_angle + ring_offsets.get(ring, 0) + i * step
        result.append(CareerTreeNode(
            title=role["title"],
            ring=ring,
            fit=fit,
            salary_range=role["salary"],
            have_skills=have,
            gap_skills=gap,
            angle=round(angle, 1),
            r=r,
        ))
    return result


# ── Public entry point ────────────────────────────────────────────────────────

def build_career_tree(profile: UserProfile) -> CareerTreeResponse:
    """Build a four-ring career tree from the user's profile data."""
    craft = _detect_craft(profile.target_role, profile.skills or [])
    level = _normalise_level(profile.experience_level)
    ring_data = _ROLES.get(craft, _FALLBACK_ROLES).get(level, _FALLBACK_ROLES["mid"])  # type: ignore[arg-type]

    user_skills = {s.lower() for s in (profile.skills or [])}

    # Ring radii match the existing SVG layout
    RADII = {"direct": 90.0, "adjacent": 150.0, "stretch": 210.0, "peripheral": 265.0}
    # Start angles staggered so rings don't perfectly overlap
    STARTS = {"direct": -90.0, "adjacent": -65.0, "stretch": -45.0, "peripheral": -20.0}

    center_title = profile.target_role or f"{level.title()} {craft.title()}"

    return CareerTreeResponse(
        center_title=center_title,
        direct=_assign_angles(ring_data.get("direct", []), "direct", user_skills, RADII["direct"], STARTS["direct"]),
        adjacent=_assign_angles(ring_data.get("adjacent", []), "adjacent", user_skills, RADII["adjacent"], STARTS["adjacent"]),
        stretch=_assign_angles(ring_data.get("stretch", []), "stretch", user_skills, RADII["stretch"], STARTS["stretch"]),
        peripheral=_assign_angles(ring_data.get("peripheral", []), "peripheral", user_skills, RADII["peripheral"], STARTS["peripheral"]),
    )
