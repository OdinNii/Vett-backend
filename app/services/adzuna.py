"""
Adzuna API client.

Docs: https://developer.adzuna.com/overview
"""
import httpx
from urllib.parse import urlencode, quote
from typing import Any, Optional
from app.config import get_settings

settings = get_settings()


class AdzunaClient:
    def __init__(self) -> None:
        self._base = settings.adzuna_base_url
        self._app_id = settings.adzuna_app_id
        self._api_key = settings.adzuna_api_key

    def _auth_params(self) -> dict[str, str]:
        return {"app_id": self._app_id, "app_key": self._api_key}

    async def search_jobs(
        self,
        *,
        country: str = "gb",
        keywords: str,
        location: Optional[str] = None,
        salary_min: Optional[int] = None,
        salary_max: Optional[int] = None,
        full_time: Optional[bool] = None,
        permanent: Optional[bool] = None,
        max_days_old: int = 30,
        results_per_page: int = 50,
        page: int = 1,
        sort_by: str = "date",
    ) -> dict[str, Any]:
        # Note: page is in the URL PATH (/search/{page}), NOT a query param
        params: dict[str, Any] = {
            **self._auth_params(),
            "results_per_page": results_per_page,
            "sort_by": sort_by,
            "max_days_old": max_days_old,
        }
        # Adzuna requires %20 for spaces, not + (rejects + encoding).
        # Build query string with quote() which uses %20, then pass as raw URL.
        str_params: dict[str, str] = {k: str(v) for k, v in params.items()}
        if keywords:
            str_params["what"] = keywords
        if location:
            str_params["where"] = location
        if salary_min is not None:
            str_params["salary_min"] = str(salary_min)
        if salary_max is not None:
            str_params["salary_max"] = str(salary_max)
        if full_time is not None:
            str_params["full_time"] = "1" if full_time else "0"
        if permanent is not None:
            str_params["permanent"] = "1" if permanent else "0"

        # urlencode with quote_via=quote uses %20 instead of +
        qs = urlencode(str_params, quote_via=quote)
        url = f"{self._base}/jobs/{country}/search/{page}?{qs}"

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.json()

    async def get_job_details(self, job_id: str, country: str = "gb") -> dict[str, Any]:
        url = f"{self._base}/jobs/{country}/search/1"
        params = {**self._auth_params(), "what_or": job_id, "results_per_page": 1}

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            results = data.get("results", [])
            return results[0] if results else {}

    def parse_job(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Normalise a raw Adzuna result into our internal job shape."""
        salary = raw.get("salary_min"), raw.get("salary_max")
        location_data = raw.get("location", {})
        location_areas = location_data.get("area", [])
        location_str = ", ".join(str(a) for a in location_areas if a) if location_areas else location_data.get("display_name", "")

        # Detect remote from title/description
        description = raw.get("description", "")
        title = raw.get("title", "")
        is_remote = any(
            kw in (title + " " + description).lower()
            for kw in ("remote", "work from home", "wfh", "fully remote", "100% remote")
        )

        return {
            "adzuna_id": str(raw.get("id", "")),
            "title": title,
            "company": raw.get("company", {}).get("display_name", ""),
            "location": location_str,
            "description": description,
            "description_short": description[:400] if description else "",
            "redirect_url": raw.get("redirect_url", ""),
            "salary_min": salary[0],
            "salary_max": salary[1],
            "salary_currency": "GBP",
            "category": raw.get("category", {}).get("label", ""),
            "contract_type": raw.get("contract_type", ""),
            "contract_time": raw.get("contract_time", ""),
            "is_remote": is_remote,
            "posted_at": raw.get("created"),
        }


adzuna_client = AdzunaClient()
