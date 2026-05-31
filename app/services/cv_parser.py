"""
CV parser — extracts structured data from PDF and DOCX files.

Libraries used:
  - PyMuPDF  (fitz) for PDF text extraction
  - python-docx for DOCX
  - A curated skills taxonomy for skill detection
"""
import re
import io
from pathlib import Path
from typing import Any, Optional

try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False

try:
    import docx as python_docx
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False


# ── Skill taxonomy ────────────────────────────────────────────────────────────

TECH_SKILLS: set[str] = {
    # Languages
    "python", "javascript", "typescript", "java", "kotlin", "swift", "go", "golang",
    "rust", "c++", "c#", "php", "ruby", "scala", "r", "sql", "bash", "shell",
    # Frontend
    "react", "react native", "vue", "angular", "next.js", "svelte", "html", "css",
    "tailwind", "redux", "graphql", "webpack",
    # Backend
    "fastapi", "django", "flask", "node.js", "express", "spring", "rails",
    "rest api", "grpc", "websockets",
    # Data & Analytics tools
    "pandas", "numpy", "scikit-learn", "tensorflow", "pytorch", "keras",
    "spark", "kafka", "airflow", "dbt",
    "excel", "power bi", "tableau", "looker", "google analytics", "sap",
    # Cloud & Infra
    "aws", "gcp", "azure", "docker", "kubernetes", "terraform", "ansible",
    "ci/cd", "github actions", "jenkins", "linux",
    # Databases
    "postgresql", "mysql", "mongodb", "redis", "elasticsearch", "dynamodb",
    "bigquery", "snowflake", "salesforce", "hubspot", "zendesk",
    # Other tech
    "git", "agile", "scrum", "figma", "jira", "confluence",
}

SOFT_SKILLS: set[str] = {
    # Leadership & Management
    "leadership", "management", "team leadership", "people management",
    "stakeholder management", "change management", "performance management",
    "mentoring", "coaching", "training",

    # Strategy & Planning
    "strategy", "strategic planning", "product management", "project management",
    "account management", "portfolio management", "programme management",
    "budget management", "forecasting", "roadmap",

    # Communication & Collaboration
    "communication", "presentation", "negotiation", "collaboration",
    "cross-functional", "relationship management", "client management",
    "partnership management",

    # Customer & Sales
    "customer success", "customer service", "customer experience",
    "customer retention", "customer satisfaction", "client success",
    "sales", "business development", "account management",
    "upselling", "crm",

    # Data & Analysis
    "data analysis", "data analytics", "business intelligence", "reporting",
    "kpi", "metrics", "benchmarking", "analytical", "problem solving",
    "research", "insights",

    # Operations
    "operations", "operations management", "process improvement",
    "process optimization", "workflow", "compliance", "risk management",
    "quality assurance", "auditing", "supply chain", "logistics",

    # Finance
    "billing", "invoicing", "financial analysis", "budgeting", "reconciliation",
    "accounts receivable", "accounts payable",

    # Marketing & Content
    "digital marketing", "marketing", "content marketing", "seo", "social media",
    "campaign management", "brand management", "copywriting",

    # Soft / Interpersonal
    "communication", "organisation", "time management", "adaptability",
    "problem solving", "critical thinking", "creativity", "initiative",
}

ALL_SKILLS: set[str] = TECH_SKILLS | SOFT_SKILLS

EXPERIENCE_PATTERNS = [
    r"(\d+)\+?\s*years?\s+(?:of\s+)?experience",
    r"(\d+)\+?\s*yrs?\s+(?:of\s+)?experience",
    r"experience[:\s]+(\d+)\+?\s*years?",
]

LEVEL_KEYWORDS = {
    "junior": ["junior", "entry level", "entry-level", "graduate", "jr."],
    "mid":    ["mid", "mid-level", "intermediate"],
    "senior": ["senior", "sr.", "lead", "principal", "staff"],
    "head":   ["head of", "vp", "vice president", "director", "chief", "cto", "cpo", "coo"],
}

# Job titles for current-role extraction (ordered longest-first for greedy match)
_JOB_TITLE_PATTERNS: list[str] = sorted([
    # Operations / Settlements / Billing
    "settlements specialist", "billing specialist", "billing analyst",
    "operations analyst", "operations manager", "operations executive",
    "operations coordinator", "operations lead",
    # Customer Success / Service
    "customer success manager", "customer success specialist",
    "customer success lead", "customer success",
    "customer experience manager", "customer service manager",
    "customer service agent", "complaints manager", "complaints agent",
    "account manager", "account executive", "account director",
    "client success manager", "client manager",
    # Data & Analysis
    "data analyst", "data engineer", "data scientist", "business analyst",
    "business intelligence analyst", "reporting analyst",
    # Product & Project
    "product manager", "senior product manager", "product lead",
    "project manager", "programme manager", "delivery manager",
    # Engineering
    "software engineer", "senior software engineer", "software developer",
    "frontend engineer", "backend engineer", "full stack engineer",
    "engineering manager", "tech lead",
    # Marketing
    "marketing manager", "digital marketing manager", "content manager",
    "seo manager", "growth manager",
    # Finance
    "financial analyst", "finance manager",
    # Creative / Communications
    "communications director", "creative director", "content creator",
], key=len, reverse=True)

# Common UK city names for location extraction
_UK_CITIES: list[str] = [
    "london", "manchester", "birmingham", "bristol", "leeds", "sheffield",
    "edinburgh", "glasgow", "liverpool", "newcastle", "nottingham", "cardiff",
    "oxford", "cambridge", "reading", "southampton", "coventry", "leicester",
    "swindon", "bath", "exeter", "brighton", "portsmouth", "york", "derby",
    "wolverhampton", "stoke-on-trent", "hull", "middlesbrough", "aberdeen",
    "dundee", "belfast", "dublin",
]


# ── Text extraction ───────────────────────────────────────────────────────────

def extract_text_from_pdf(file_bytes: bytes) -> str:
    if not HAS_PYMUPDF:
        raise RuntimeError("PyMuPDF not installed — run: pip install PyMuPDF")
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    return "\n".join(page.get_text() for page in doc)


def extract_text_from_docx(file_bytes: bytes) -> str:
    if not HAS_DOCX:
        raise RuntimeError("python-docx not installed — run: pip install python-docx")
    document = python_docx.Document(io.BytesIO(file_bytes))
    return "\n".join(para.text for para in document.paragraphs)


def extract_text(file_bytes: bytes, filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        return extract_text_from_pdf(file_bytes)
    elif suffix in (".docx", ".doc"):
        return extract_text_from_docx(file_bytes)
    elif suffix == ".txt":
        return file_bytes.decode("utf-8", errors="replace")
    raise ValueError(f"Unsupported file type: {suffix}")


# ── Field extraction ──────────────────────────────────────────────────────────

def extract_skills(text: str) -> list[str]:
    text_lower = text.lower()
    found: set[str] = set()
    for skill in ALL_SKILLS:
        pattern = r"\b" + re.escape(skill) + r"\b"
        if re.search(pattern, text_lower):
            found.add(skill)
    return sorted(found)


def extract_experience_years(text: str) -> Optional[int]:
    text_lower = text.lower()
    for pattern in EXPERIENCE_PATTERNS:
        match = re.search(pattern, text_lower)
        if match:
            return int(match.group(1))
    return None


def infer_experience_level(text: str, years: Optional[int]) -> str:
    text_lower = text.lower()
    for level, keywords in LEVEL_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            return level
    if years is not None:
        if years < 2:  return "junior"
        if years < 5:  return "mid"
        if years < 10: return "senior"
        return "head"
    return "mid"


def extract_email(text: str) -> Optional[str]:
    match = re.search(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", text)
    return match.group(0) if match else None


def extract_name(text: str) -> Optional[str]:
    """Best-effort: first non-empty short line (2–3 words, no digits) is the name."""
    for line in text.splitlines():
        line = line.strip()
        if line and len(line.split()) in (2, 3) and not any(c.isdigit() for c in line):
            return line
    return None


def extract_recent_job_title(text: str) -> Optional[str]:
    """
    Extract the candidate's most recent job title from the CV text.

    Strategy: scan the first 2 000 chars (where most recent role appears)
    for any line that matches a known job-title pattern.  Returns the first
    (topmost) match — CVs are written reverse-chronologically so the first
    title found is the most recent.
    """
    search_zone = text[:2000].lower()
    for title in _JOB_TITLE_PATTERNS:
        if re.search(r"\b" + re.escape(title) + r"\b", search_zone):
            return title
    return None


def extract_location(text: str) -> Optional[str]:
    """Return the first UK city found in the CV header (first 400 chars)."""
    header = text[:400].lower()
    for city in _UK_CITIES:
        if re.search(r"\b" + re.escape(city) + r"\b", header):
            return city.title()
    return None


# ── Public API ────────────────────────────────────────────────────────────────

def parse_cv(file_bytes: bytes, filename: str) -> dict[str, Any]:
    """Full CV parse pipeline. Returns structured profile data."""
    raw_text = extract_text(file_bytes, filename)
    skills   = extract_skills(raw_text)
    years    = extract_experience_years(raw_text)
    level    = infer_experience_level(raw_text, years)

    return {
        "raw_text":         raw_text,
        "skills":           skills,
        "experience_years": years,
        "experience_level": level,
        "detected_email":   extract_email(raw_text),
        "detected_name":    extract_name(raw_text),
        "detected_title":   extract_recent_job_title(raw_text),
        "detected_location": extract_location(raw_text),
    }
