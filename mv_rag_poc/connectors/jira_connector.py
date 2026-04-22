"""
connectors/jira_connector.py
Read-only Jira integration for the MV AI Knowledge Hub.

Fetches tickets, epics, stories, comments and links them to MV BASIC subroutines.
NO write operations — information only.

Requires in .env:
    JIRA_URL      — e.g. https://your-org.atlassian.net
    JIRA_EMAIL    — your Atlassian account email
    JIRA_TOKEN    — Atlassian API token (not your password)
    JIRA_PROJECT  — project key, e.g. "PROJ"

Create an API token at:
    Atlassian → Account Settings → Security → Create and manage API tokens
"""

from atlassian import Jira

from config import JIRA_URL, JIRA_EMAIL, JIRA_TOKEN, JIRA_PROJECT
from connectors._cache import ttl_cache


# ── Client ─────────────────────────────────────────────────────────────────────

def _get_client() -> Jira:
    if not all([JIRA_URL, JIRA_EMAIL, JIRA_TOKEN]):
        raise ValueError(
            "Jira not configured. Add JIRA_URL, JIRA_EMAIL, JIRA_TOKEN to .env\n"
            "Create a token at: Atlassian → Account Settings → Security → API tokens"
        )
    return Jira(url=JIRA_URL, username=JIRA_EMAIL, password=JIRA_TOKEN, cloud=True)


# ── Text extraction from Atlassian Document Format (ADF) ──────────────────────

def _adf_to_text(content) -> str:
    """Recursively extract plain text from Atlassian Document Format (ADF)."""
    if not content:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        if content.get("type") == "text":
            return content.get("text", "")
        parts = [_adf_to_text(child) for child in content.get("content", [])]
        return " ".join(p for p in parts if p)
    if isinstance(content, list):
        return " ".join(_adf_to_text(item) for item in content if item)
    return ""


# ── Ticket formatting ──────────────────────────────────────────────────────────

def _extract_sprint_name(fields: dict) -> str:
    """Extract sprint name from customfield_10020 (Jira Cloud sprint field)."""
    sprints = fields.get("customfield_10020") or []
    if isinstance(sprints, list) and sprints:
        # Pick the active or last sprint in the list
        for s in reversed(sprints):
            if isinstance(s, dict) and s.get("name"):
                return s["name"]
    return ""


def _format_issue(issue: dict) -> dict:
    """Extract the most useful fields from a raw Jira issue dict."""
    fields = issue.get("fields", {})

    assignee  = fields.get("assignee") or {}
    reporter  = fields.get("reporter") or {}
    priority  = fields.get("priority") or {}
    status    = fields.get("status") or {}
    issuetype = fields.get("issuetype") or {}
    epic      = fields.get("epic") or {}

    description = fields.get("description", "")
    if isinstance(description, dict):
        description = _adf_to_text(description)

    # Extract subtasks
    raw_subtasks = fields.get("subtasks") or []
    subtasks = [
        {
            "key":     s.get("key", ""),
            "summary": (s.get("fields") or {}).get("summary", ""),
            "status":  ((s.get("fields") or {}).get("status") or {}).get("name", ""),
            "url":     f"{JIRA_URL.rstrip('/')}/browse/{s.get('key', '')}",
        }
        for s in raw_subtasks
    ]

    return {
        "key":         issue.get("key", ""),
        "type":        issuetype.get("name", ""),
        "summary":     fields.get("summary", ""),
        "status":      status.get("name", ""),
        "priority":    priority.get("name", ""),
        "assignee":    assignee.get("displayName", "Unassigned"),
        "reporter":    reporter.get("displayName", ""),
        "created":     (fields.get("created", "") or "")[:10],
        "updated":     (fields.get("updated", "") or "")[:10],
        "description": description[:2000] if description else "",
        "labels":      fields.get("labels", []),
        "epic":        epic.get("summary", "") if epic else fields.get("customfield_10014", ""),
        "sprint":      _extract_sprint_name(fields),
        "subtasks":    subtasks,
        "url":         f"{JIRA_URL.rstrip('/')}/browse/{issue.get('key', '')}",
    }


# ── Read-only API functions ────────────────────────────────────────────────────

@ttl_cache(ttl_seconds=60)
def get_ticket(key: str) -> dict:
    """Get full details of a specific Jira ticket by key (e.g. PROJ-123)."""
    client = _get_client()
    try:
        issue = client.issue(key)
        result = _format_issue(issue)
        fields = issue.get("fields", {})

        # Acceptance criteria — try common custom field IDs
        ac = ""
        for cf in ["customfield_10028", "customfield_10034", "customfield_10500"]:
            val = fields.get(cf)
            if val:
                ac = _adf_to_text(val) if isinstance(val, dict) else str(val)
                break
        result["acceptance_criteria"] = ac[:1000] if ac else ""

        # All comments
        comments_raw = (fields.get("comment") or {}).get("comments", [])
        result["comments"] = [
            {
                "author": (c.get("author") or {}).get("displayName", ""),
                "date":   (c.get("created", "") or "")[:10],
                "body":   _adf_to_text(c.get("body", ""))[:500],
            }
            for c in comments_raw[-10:]
        ]

        # Linked issues (blocks / is blocked by / relates to)
        links_raw = fields.get("issuelinks") or []
        result["linked_issues"] = [
            {
                "type":    (lk.get("type") or {}).get("name", ""),
                "key":     (lk.get("inwardIssue") or lk.get("outwardIssue") or {}).get("key", ""),
                "summary": ((lk.get("inwardIssue") or lk.get("outwardIssue") or {}).get("fields") or {}).get("summary", ""),
            }
            for lk in links_raw
        ]
        return result
    except Exception as e:
        return {"error": f"Cannot fetch ticket '{key}': {e}"}


@ttl_cache(ttl_seconds=60)
def search_tickets(jql: str, max_results: int = 20) -> list[dict]:
    """Search Jira tickets using JQL (Jira Query Language)."""
    client = _get_client()
    try:
        results = client.jql(jql, limit=max_results)
        return [_format_issue(issue) for issue in results.get("issues", [])]
    except Exception as e:
        return [{"error": f"JQL search failed: {e}"}]


def get_tickets_for_subroutine(subroutine_name: str, max_results: int = 10) -> list[dict]:
    """
    Find Jira tickets that mention a subroutine name in summary or description.
    This is the key cross-linking function — connects code to business tickets.
    """
    project_clause = f'project = "{JIRA_PROJECT}" AND ' if JIRA_PROJECT else ""
    jql = (
        f'{project_clause}text ~ "{subroutine_name}" '
        f'ORDER BY updated DESC'
    )
    return search_tickets(jql, max_results=max_results)


def get_recent_tickets(max_results: int = 20) -> list[dict]:
    """Get most recently updated tickets in the project."""
    project_clause = f'project = "{JIRA_PROJECT}" AND ' if JIRA_PROJECT else ""
    jql = f"{project_clause}ORDER BY updated DESC"
    return search_tickets(jql, max_results=max_results)


def get_sprint_tickets(max_results: int = 50) -> dict:
    """Get current active sprint name and all its tickets."""
    project_clause = f'project = "{JIRA_PROJECT}" AND ' if JIRA_PROJECT else ""
    jql = f"{project_clause}sprint in openSprints() ORDER BY priority DESC"
    tickets = search_tickets(jql, max_results=max_results)
    sprint_name = tickets[0].get("sprint", "Current Sprint") if tickets else "Current Sprint"
    return {"sprint_name": sprint_name, "sprint_type": "current", "tickets": tickets}


def get_future_sprint_tickets(max_results: int = 50) -> dict:
    """Get next upcoming sprint name and all its tickets."""
    project_clause = f'project = "{JIRA_PROJECT}" AND ' if JIRA_PROJECT else ""
    jql = f"{project_clause}sprint in futureSprints() ORDER BY priority DESC"
    tickets = search_tickets(jql, max_results=max_results)
    sprint_name = tickets[0].get("sprint", "Upcoming Sprint") if tickets else "Upcoming Sprint"
    return {"sprint_name": sprint_name, "sprint_type": "upcoming", "tickets": tickets}


def get_backlog_tickets(max_results: int = 50) -> list[dict]:
    """Get tickets in the backlog — not assigned to any sprint, not done."""
    project_clause = f'project = "{JIRA_PROJECT}" AND ' if JIRA_PROJECT else ""
    jql = (
        f"{project_clause}sprint is EMPTY AND status != Done "
        f"ORDER BY priority DESC"
    )
    return search_tickets(jql, max_results=max_results)


def get_planned_features(max_results: int = 30) -> list[dict]:
    """Get stories and features planned for future sprints."""
    project_clause = f'project = "{JIRA_PROJECT}" AND ' if JIRA_PROJECT else ""
    jql = (
        f"{project_clause}issuetype in (Story, Feature, Epic) "
        f"AND sprint in futureSprints() ORDER BY priority DESC"
    )
    return search_tickets(jql, max_results=max_results)


def get_open_bugs(max_results: int = 20) -> list[dict]:
    """Get all open bugs in the project."""
    project_clause = f'project = "{JIRA_PROJECT}" AND ' if JIRA_PROJECT else ""
    jql = f'{project_clause}issuetype = Bug AND status != Done ORDER BY priority DESC'
    return search_tickets(jql, max_results=max_results)


def get_epic_tickets(epic_key: str, max_results: int = 30) -> list[dict]:
    """Get all stories/tasks under a specific epic."""
    jql = f'"Epic Link" = {epic_key} OR parent = {epic_key} ORDER BY status ASC'
    return search_tickets(jql, max_results=max_results)


def get_tickets_by_assignee(assignee_name: str, max_results: int = 20) -> list[dict]:
    """Get open tickets assigned to a specific person."""
    project_clause = f'project = "{JIRA_PROJECT}" AND ' if JIRA_PROJECT else ""
    jql = (
        f'{project_clause}assignee = "{assignee_name}" '
        f'AND status != Done ORDER BY updated DESC'
    )
    return search_tickets(jql, max_results=max_results)


@ttl_cache(ttl_seconds=60)
def get_project_summary() -> dict:
    """Return a high-level summary of the Jira project."""
    client = _get_client()
    try:
        project_clause = f'project = "{JIRA_PROJECT}" AND ' if JIRA_PROJECT else ""

        total    = client.jql(f"{project_clause}ORDER BY created", limit=1).get("total", 0)
        open_    = client.jql(f"{project_clause}status != Done", limit=1).get("total", 0)
        bugs     = client.jql(f'{project_clause}issuetype = Bug AND status != Done', limit=1).get("total", 0)
        in_sprint = client.jql(f"{project_clause}sprint in openSprints()", limit=1).get("total", 0)

        return {
            "project":          JIRA_PROJECT,
            "total_tickets":    total,
            "open_tickets":     open_,
            "open_bugs":        bugs,
            "in_sprint":        in_sprint,
            "jira_url":         JIRA_URL,
        }
    except Exception as e:
        return {"error": f"Cannot fetch project summary: {e}"}
