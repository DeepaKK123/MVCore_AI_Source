"""
connectors/confluence_connector.py
Read-only Confluence integration for the MV AI Knowledge Hub.

Fetches pages, specs, runbooks and business docs — links them to MV BASIC subroutines.
NO write operations — information only.

Reuses Jira credentials (same Atlassian account):
    JIRA_URL      — e.g. https://your-org.atlassian.net
    JIRA_EMAIL    — your Atlassian account email
    JIRA_TOKEN    — Atlassian API token
    CONFLUENCE_SPACE — space key e.g. "TECH", "PROJ", "DEV"

Find your space key:
    Confluence → Space → Space Settings → Space Details → Space Key
"""

import re
from atlassian import Confluence

from config import JIRA_URL, JIRA_EMAIL, JIRA_TOKEN, CONFLUENCE_SPACE


# ── Client ─────────────────────────────────────────────────────────────────────

def _get_client() -> Confluence:
    if not all([JIRA_URL, JIRA_EMAIL, JIRA_TOKEN]):
        raise ValueError(
            "Confluence not configured. Add JIRA_URL, JIRA_EMAIL, JIRA_TOKEN to .env\n"
            "Also add CONFLUENCE_SPACE (your space key, e.g. TECH)"
        )
    return Confluence(url=JIRA_URL, username=JIRA_EMAIL, password=JIRA_TOKEN, cloud=True)


# ── HTML stripping ─────────────────────────────────────────────────────────────

_HTML_TAG = re.compile(r'<[^>]+>')
_WHITESPACE = re.compile(r'\s+')

def _strip_html(html: str) -> str:
    """Strip Confluence storage HTML to plain readable text."""
    if not html:
        return ""
    text = _HTML_TAG.sub(' ', html)
    text = _WHITESPACE.sub(' ', text).strip()
    return text


# ── Page formatting ────────────────────────────────────────────────────────────

def _format_page(page: dict, include_body: bool = True) -> dict:
    """Extract the most useful fields from a raw Confluence page dict."""
    body     = page.get("body", {})
    storage  = body.get("storage", {}) if body else {}
    html     = storage.get("value", "") if storage else ""
    plain    = _strip_html(html)[:1500] if include_body else ""

    version  = page.get("version", {}) or {}
    space    = page.get("space", {}) or {}
    history  = page.get("history", {}) or {}
    last_upd = history.get("lastUpdated", {}) or {}
    by       = last_upd.get("by", {}) or {}

    return {
        "id":           page.get("id", ""),
        "title":        page.get("title", ""),
        "space":        space.get("key", CONFLUENCE_SPACE),
        "version":      version.get("number", ""),
        "last_updated": last_upd.get("when", "")[:10] if last_upd.get("when") else "",
        "updated_by":   by.get("displayName", ""),
        "content":      plain,
        "url":          f"{JIRA_URL.rstrip('/')}/wiki{page.get('_links', {}).get('webui', '')}",
    }


# ── Read-only API functions ────────────────────────────────────────────────────

def search_pages(query: str, max_results: int = 10) -> list[dict]:
    """
    Full-text search across Confluence using CQL.
    Searches titles and body content.
    """
    client = _get_client()
    space_clause = f' AND space = "{CONFLUENCE_SPACE}"' if CONFLUENCE_SPACE else ""
    cql = f'text ~ "{query}"{space_clause} ORDER BY lastModified DESC'
    try:
        results = client.cql(cql, limit=max_results)
        pages = []
        for r in results.get("results", []):
            page_id = r.get("content", {}).get("id", "")
            if page_id:
                try:
                    full = client.get_page_by_id(
                        page_id, expand="body.storage,version,space,history.lastUpdated.by"
                    )
                    pages.append(_format_page(full))
                except Exception:
                    pages.append({
                        "id":    page_id,
                        "title": r.get("content", {}).get("title", ""),
                        "url":   f"{JIRA_URL.rstrip('/')}/wiki{r.get('url', '')}",
                    })
        return pages
    except Exception as e:
        return [{"error": f"Confluence search failed: {e}"}]


def get_page_by_title(title: str) -> dict:
    """Get a specific Confluence page by its exact or partial title."""
    client = _get_client()
    try:
        space_clause = f' AND space = "{CONFLUENCE_SPACE}"' if CONFLUENCE_SPACE else ""
        cql = f'title ~ "{title}"{space_clause} ORDER BY lastModified DESC'
        results = client.cql(cql, limit=1)
        hits = results.get("results", [])
        if not hits:
            return {"error": f"No page found with title matching '{title}'"}
        page_id = hits[0].get("content", {}).get("id", "")
        full = client.get_page_by_id(
            page_id, expand="body.storage,version,space,history.lastUpdated.by"
        )
        return _format_page(full)
    except Exception as e:
        return {"error": f"Cannot fetch page '{title}': {e}"}


def get_pages_for_subroutine(subroutine_name: str, max_results: int = 5) -> list[dict]:
    """
    Find Confluence pages that mention a subroutine name.
    Key cross-linking function — connects code to business documentation.
    """
    return search_pages(subroutine_name, max_results=max_results)


def get_recent_pages(max_results: int = 10) -> list[dict]:
    """Get most recently updated pages in the Confluence space."""
    client = _get_client()
    space_clause = f'space = "{CONFLUENCE_SPACE}" AND ' if CONFLUENCE_SPACE else ""
    cql = f'{space_clause}type = page ORDER BY lastModified DESC'
    try:
        results = client.cql(cql, limit=max_results)
        pages = []
        for r in results.get("results", []):
            page_id = r.get("content", {}).get("id", "")
            if page_id:
                try:
                    full = client.get_page_by_id(
                        page_id, expand="version,space,history.lastUpdated.by"
                    )
                    pages.append(_format_page(full, include_body=False))
                except Exception:
                    pages.append({
                        "title": r.get("content", {}).get("title", ""),
                        "url":   f"{JIRA_URL.rstrip('/')}/wiki{r.get('url', '')}",
                    })
        return pages
    except Exception as e:
        return [{"error": f"Cannot fetch recent pages: {e}"}]


def get_space_pages(max_results: int = 50) -> list[dict]:
    """List all pages in the configured Confluence space (titles only)."""
    client = _get_client()
    if not CONFLUENCE_SPACE:
        return [{"error": "CONFLUENCE_SPACE not set in .env"}]
    try:
        pages = client.get_all_pages_from_space(CONFLUENCE_SPACE, limit=max_results)
        return [
            {
                "id":    p.get("id", ""),
                "title": p.get("title", ""),
                "url":   f"{JIRA_URL.rstrip('/')}/wiki{p.get('_links', {}).get('webui', '')}",
            }
            for p in pages
        ]
    except Exception as e:
        return [{"error": f"Cannot list space pages: {e}"}]


def get_space_summary() -> dict:
    """Return high-level info about the Confluence space."""
    client = _get_client()
    if not CONFLUENCE_SPACE:
        return {"error": "CONFLUENCE_SPACE not set in .env"}
    try:
        space    = client.get_space(CONFLUENCE_SPACE, expand="description.plain")
        cql      = f'space = "{CONFLUENCE_SPACE}" AND type = page'
        total    = client.cql(cql, limit=1).get("totalSize", 0)
        desc_obj = space.get("description", {}).get("plain", {})
        desc     = desc_obj.get("value", "") if desc_obj else ""
        return {
            "space_key":   CONFLUENCE_SPACE,
            "name":        space.get("name", ""),
            "description": desc[:300],
            "total_pages": total,
            "url":         f"{JIRA_URL.rstrip('/')}/wiki/spaces/{CONFLUENCE_SPACE}",
        }
    except Exception as e:
        return {"error": f"Cannot fetch space summary: {e}"}
