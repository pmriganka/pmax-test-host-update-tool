"""
Lazy loader + lookup helper for qTest test-case field metadata
(project-scoped). Fetches once per session, caches to disk to avoid
repeated 3 MB+ downloads.

Used to back the "Program Team", "Scrum Team ID", "Scrum Team",
"System Test Pillars" and "Test Type" dropdowns on the
Test Case Management page.
"""
from __future__ import annotations

import json
import os
from typing import Any, Iterable, List, Optional

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://qtest.gtie.dell.com/api/v3"
# Test cases live in project 442, but the field metadata endpoint for that
# project returns 403 for most tokens. Project 1 exposes the same field
# catalog with read access, so we query the fields there by default and
# allow an override via env var if needed.
PROJECT_ID = os.getenv("QTEST_PROJECT_ID", "442")
FIELDS_PROJECT_ID = os.getenv("QTEST_FIELDS_PROJECT_ID", "1")

_HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(_HERE, f"api_all_fields_{FIELDS_PROJECT_ID}.json")
# Fallback chain so we try alternative projects if the primary returns 403.
_FIELDS_PROJECT_FALLBACKS = [FIELDS_PROJECT_ID, PROJECT_ID, "1"]

# Custom fields we expose on the Test Case Management page.
TARGET_FIELDS = [
    "Program Team",
    "Scrum Team ID",
    "Scrum Team",
    "System Test Pillars",
    "Test Type",
]


class FieldMetadata:
    """Thin wrapper around the project `settings/test-cases/fields` endpoint."""

    def __init__(self, headers: Optional[dict] = None):
        self.headers = headers or {}
        self._all_fields: Optional[list] = None

    # ------------------------------------------------------------------ fetch
    def _load_from_cache(self) -> Optional[list]:
        # Prefer the project-scoped cache for the fields project; fall back
        # to the legacy `api_all_fields.json` that the repo already ships.
        for path in (
            CACHE_PATH,
            os.path.join(_HERE, "api_all_fields.json"),
        ):
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        return json.load(f)
                except Exception:
                    continue
        return None

    def _header_variants(self) -> list:
        """Yield the auth header sets to try, starting with the user's
        session token and falling back to the admin token in .env."""
        variants: list = []
        if self.headers:
            variants.append(self.headers)
        env_token = os.getenv("API_TOKEN")
        if env_token:
            env_headers = {
                "Authorization": env_token,
                "Cache-Control": "no-cache",
                "Content-Type": "application/json",
                "Accept-Type": "application/json",
            }
            # Avoid a duplicate request if the session headers already carry
            # the same token.
            session_auth = (self.headers or {}).get("Authorization", "")
            if env_token not in session_auth:
                variants.append(env_headers)
        return variants or [{}]

    def _fetch_remote(self) -> list:
        last_error: Optional[Exception] = None
        tried: set = set()
        for pid in _FIELDS_PROJECT_FALLBACKS:
            if pid in tried:
                continue
            tried.add(pid)
            url = f"{BASE_URL}/projects/{pid}/settings/test-cases/fields"
            for headers in self._header_variants():
                try:
                    r = requests.get(url, headers=headers, timeout=60)
                    r.raise_for_status()
                except Exception as e:  # noqa: BLE001
                    last_error = e
                    continue
                data = r.json()
                try:
                    cache_path = os.path.join(_HERE, f"api_all_fields_{pid}.json")
                    with open(cache_path, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=4)
                except Exception:
                    pass
                return data
        raise last_error if last_error else RuntimeError("Could not fetch field metadata")

    @staticmethod
    def _has_target_fields(fields: list) -> bool:
        labels = {item.get("label") for item in (fields or [])}
        return any(t in labels for t in TARGET_FIELDS)

    def get_all_fields(self, force_refresh: bool = False) -> list:
        if force_refresh:
            self._all_fields = self._fetch_remote()
            return self._all_fields
        if self._all_fields is not None:
            return self._all_fields
        cached = self._load_from_cache()
        # If the cached catalog is incomplete (e.g. stale project-1 dump that
        # lacks the project-442 custom fields), attempt a live fetch first
        # using the admin-token fallback; only keep the cache if the live
        # call fails.
        if cached is not None and self._has_target_fields(cached):
            self._all_fields = cached
            return self._all_fields
        try:
            self._all_fields = self._fetch_remote()
        except Exception:
            if cached is not None:
                self._all_fields = cached
                return self._all_fields
            raise
        return self._all_fields

    # --------------------------------------------------------------- lookups
    def get_field(self, name: str) -> Optional[dict]:
        for item in self.get_all_fields():
            if item.get("label") == name or item.get("original_name") == name:
                return item
        return None

    def get_attribute_type(self, name: str) -> Optional[str]:
        f = self.get_field(name)
        return f.get("attribute_type") if f else None

    def is_multi(self, name: str) -> bool:
        return (self.get_attribute_type(name) or "").startswith("Array")

    def get_active_labels(self, name: str) -> List[str]:
        f = self.get_field(name)
        if not f:
            return []
        return [
            v.get("label")
            for v in (f.get("allowed_values") or [])
            if v.get("is_active", True) and v.get("label")
        ]

    def lookup_value(self, name: str, label: str) -> Any:
        f = self.get_field(name)
        if not f:
            return None
        for v in f.get("allowed_values") or []:
            if v.get("label") == label:
                return v.get("value")
        return None

    def lookup_values(self, name: str, labels: Iterable[str]) -> List[Any]:
        out = []
        for lbl in labels or []:
            v = self.lookup_value(name, lbl)
            if v is not None:
                out.append(v)
        return out

    def format_field_value(self, name: str, selection) -> str:
        """Format a selection (single label or list of labels) into the
        string representation qTest expects when PUT-ing a test case."""
        if self.is_multi(name):
            labels = selection if isinstance(selection, (list, tuple)) else [selection]
            ids = self.lookup_values(name, [l for l in labels if l])
            return "[" + ",".join(str(x) for x in ids) + "]"
        v = self.lookup_value(name, selection)
        return "" if v is None else str(v)


# Convenience helpers for Streamlit callers --------------------------------
def get_metadata(headers: Optional[dict] = None) -> FieldMetadata:
    """Return a per-session FieldMetadata instance cached in st.session_state."""
    try:
        import streamlit as st

        inst = st.session_state.get("_field_metadata")
        if inst is None:
            inst = FieldMetadata(headers)
            st.session_state["_field_metadata"] = inst
        elif headers:
            inst.headers = headers
        return inst
    except Exception:
        return FieldMetadata(headers)
