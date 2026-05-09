"""
analysis/prompts/jira_prompts.py
All Jira-related detection keywords, regex patterns, and prompt builders.

Kept separate from query_engine.py so the engine focuses on orchestration
while this module owns everything "Jira-flavoured".
"""

import json
import re


# ── Detection keywords ────────────────────────────────────────────────────────

JIRA_KEYWORDS = [
    # Core Jira terms
    "jira", "ticket", "tickets", "story", "stories", "epic", "epics",
    "sprint", "backlog", "issue", "issues", "bug", "bugs", "defect",
    "task", "tasks", "subtask", "user story",

    # Manager-style sprint questions
    "what's in the sprint", "what is in the sprint",
    "what's in the current sprint", "what is in the current sprint",
    "what's in the upcoming sprint", "what is in the upcoming sprint",
    "what's in the next sprint", "what is in the next sprint",
    "current sprint", "active sprint", "this sprint", "sprint tasks",
    "sprint items", "sprint stories", "sprint tickets", "sprint status",
    "upcoming sprint", "next sprint", "planned for next",
    "what are we working on", "what is the team working on",
    "what are we building", "what's being built",
    "what's planned", "what is planned", "what is coming",
    "sprint goal", "sprint scope",

    # Delivery & progress
    "what did we complete", "what was completed", "what was delivered",
    "what was done", "what has been done", "completed tickets",
    "closed tickets", "done this sprint", "delivered this sprint",
    "what's at risk", "what is at risk", "overdue", "blocked",
    "what is blocked", "blocking", "impediment",

    # Team & assignment
    "assigned to", "working on", "who is working on",
    "what is deepa working on", "what is the developer working on",
    "team workload", "who owns", "owner of", "responsible for",

    # Planning & roadmap
    "roadmap", "next release", "what is coming", "future work",
    "planned feature", "planned sprint", "what is planned for",
    "release plan", "delivery plan",

    # Project health
    "project status", "how is the project", "project overview",
    "project summary", "how are we doing", "progress update",
    "open bugs", "known issues", "bug count",

    # Relation lookups
    "related ticket", "which ticket", "what ticket", "ticket for",
    "stories for", "linked to", "what stories", "business requirement",
    "requirement for",
]

CODE_SUGGESTION_KEYWORDS = [
    # Direct suggestion requests
    "suggest", "suggest a fix", "suggest code", "suggest the fix",
    "suggest code change", "suggest the code change",
    "suggest code for the task", "suggest code for the sprint",
    "suggest code for the ticket", "suggest code for the story",
    "suggest change for", "suggest fix for",

    # Fix / resolve
    "fix the code", "fix the bug", "fix the defect", "fix this",
    "how to fix", "how do i fix", "resolve the bug", "resolve the issue",
    "resolve the defect", "resolve the ticket",
    "to fix task", "to fix the task", "to fix this task",
    "to fix ticket", "to fix the ticket", "to fix the story",
    "to fix the bug", "to resolve",

    # Implement / build
    "how to implement", "how do i implement",
    "implement the", "implement this", "implement the task",
    "implement the story", "implement the ticket", "implement the feature",
    "build the feature", "build the", "develop the feature",

    # Code operations
    "add the feature", "add feature", "enhance", "enhancement",
    "update the code", "modify the code", "change the code",
    "write the code", "write code for", "write code to",
    "code change", "code for the", "code suggestion",
    "what code", "give me the code", "show me the code",
    "defect fix", "patch", "apply the fix",

    # Which-file / which-program questions
    "which program", "what program", "which file", "what file",
    "which subroutine", "what subroutine", "which routine", "what routine",
    "which module", "what module", "where do i change", "where to change",
    "where do i modify", "where to modify",
    "needs to be modified", "needs to be changed", "needs modification",
    "has to be modified", "has to be changed",
    "needs to change", "need to modify", "need to change",
    "should be modified", "should be changed",
    "program to modify", "program to change", "program to fix",
    "subroutine to modify", "subroutine to change", "subroutine to fix",
    "file to modify", "file to change", "file to fix",

    # Manager-style requests referencing sprint tasks
    "code for the sprint task", "code for the current task",
    "how do i implement the sprint", "code change for the task",
    "develop the sprint task", "implement the sprint task",
]

# When a Jira ticket ID appears alongside any of these, treat as code_suggestion
# instead of a generic ticket detail lookup.
CODE_CONTEXT_TERMS = (
    "program", "subroutine", "routine", "module", "file",
    "modify", "modified", "modification",
    "change", "changed",
    "fix", "fixed",
    "implement", "resolve", "code",
)

IMPACT_ANALYSIS_KEYWORDS = [
    # Direct impact-analysis phrasing
    "impact analysis", "impact analyses", "impact assessment",
    "analyze the impact", "analyse the impact",
    "analyze impact", "analyse impact",
    "what is the impact", "what's the impact", "whats the impact",
    "what will be the impact", "what would be the impact",
    "assess the impact", "evaluate the impact",
    "impact of the change", "impact of changing", "impact of this change",
    "impact on", "side effect", "side-effect", "side effects",
    "what breaks", "what will break", "what would break",
    "what gets affected", "what is affected", "what would be affected",
    "what is the effect", "what's the effect", "effect of changing",
    "downstream impact", "upstream impact", "ripple effect",
    "who is affected", "what is impacted",
    "blast radius", "risk of changing",
    # Phrasing that often pairs with a ticket
    "impact if we change", "impact if we modify",
    "impact of fixing", "impact of the fix",
]


# ── Regex patterns ────────────────────────────────────────────────────────────

JIRA_TICKET_PATTERN = re.compile(r'\b[A-Z]{1,10}-\d+\b')

# Directive patterns developers add to Jira comments / descriptions, e.g.
#   "Program need to be modified: UPDATE.ORDER"
#   "Program to modify - ORD.PROCESS"
#   "File: CUSTOMER.LOOKUP"
#   "Subroutine to update: GET.ORDER.DETAILS"
# Captures the name token that follows the colon / dash.
DIRECTIVE_PATTERNS = [
    re.compile(
        r'(?:PROGRAM|FILE|SUBROUTINE|ROUTINE|MODULE|FUNCTION)'
        r'(?:\s+(?:NAME|TO|THAT|WHICH|NEED(?:S|ED)?|HAS|HAVE|MUST|SHOULD|WILL))*'
        r'\s*(?:TO\s+BE\s+|NEED(?:S|ED)?\s+TO\s+BE\s+)?'
        r'(?:MODIFIED|MODIFY|UPDATED|UPDATE|CHANGED|CHANGE|FIXED|FIX|TOUCHED)?'
        r'\s*[:\-–=]\s*'
        r'([A-Z][A-Z0-9._]*)',
        re.IGNORECASE,
    ),
]


# ── Prompt builders ───────────────────────────────────────────────────────────

def build_jira_list_prompt(
    jira_data: dict,
    sprint_name: str,
    history_ctx: str,
    conf_context: str,
    question: str,
) -> str:
    """Concise per-ticket list with an overall summary and clickable links."""
    return (
        "You are an MVCore assistant. Answer using the Jira data below.\n"
        "IMPORTANT: Copy all field values (sprint name, ticket keys, summaries, assignee names) "
        "VERBATIM from the data — do NOT paraphrase, correct spelling, or alter any names.\n\n"
        "Structure your response exactly like this:\n\n"
        "1. SUMMARY (2-3 sentences): Give an overall summary of what is in this list — "
        "how many tickets, what statuses, what the work is about.\n\n"
        f"2. {'Start the ticket list with exactly: **Sprint: ' + sprint_name + '**' if sprint_name else 'Then list the tickets:'}\n"
        "For each ticket show:\n"
        "  [**KEY**](url) — Summary\n"
        "  Type: X | Priority: X | Status: X | Assignee: X\n"
        "  > One sentence from the description (if available)\n"
        "  - [SUBKEY](url): Subtask summary (Status)  ← indent subtasks\n\n"
        "Group tickets by status if there are more than 5.\n\n"
        "3. End with a one-line count summary (e.g. '3 In Progress, 2 To Do, 1 Done').\n\n"
        "If Confluence docs are referenced, list them with links at the end.\n\n"
        f"{history_ctx}\n"
        f"JIRA DATA:\n{json.dumps(jira_data, indent=2)}"
        f"{conf_context}\n\n"
        f"QUESTION: {question}"
    )


def build_jira_detail_prompt(
    jira_data: dict,
    history_ctx: str,
    conf_context: str,
    question: str,
) -> str:
    """Full single-ticket detail with a plain-English summary and clickable links."""
    return (
        "You are an MVCore assistant. The user wants FULL DETAILS of a Jira ticket.\n"
        "IMPORTANT: Copy all field values VERBATIM — do NOT paraphrase or alter any names.\n\n"
        "Structure your response exactly like this:\n\n"
        "Start with a 2-3 sentence plain-English summary of what this ticket is about "
        "and its current status.\n\n"
        "Then show the full ticket details:\n\n"
        "**[KEY] — Summary**\n"
        "- **Type:** | **Priority:** | **Status:** | **Assignee:** | **Reporter:**\n"
        "- **Created:** | **Updated:** | **Sprint:** | **Epic:**\n"
        "- **Link:** [KEY](url)  ← use the url field from the data\n\n"
        "**Description**\n"
        "Full description text from the ticket.\n\n"
        "**Acceptance Criteria**\n"
        "List each criterion on a new line.\n\n"
        "**Subtasks** (if any)\n"
        "- [SUBKEY](url) — Summary (Status)\n\n"
        "**Linked Issues** (if any)\n"
        "- TYPE: [KEY](url) — Summary\n\n"
        "**Comments** (most recent first, all comments)\n"
        "- [Date] Author: comment text\n\n"
        "**Related Confluence Docs** (if any)\n"
        "List page titles with links.\n\n"
        f"{history_ctx}\n"
        f"JIRA DATA:\n{json.dumps(jira_data, indent=2)}"
        f"{conf_context}\n\n"
        f"QUESTION: {question}"
    )
