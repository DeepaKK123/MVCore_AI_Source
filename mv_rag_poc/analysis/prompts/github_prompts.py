"""
analysis/prompts/github_prompts.py
GitHub history detection keywords and prompt builder.
"""

import json


# ── Detection keywords ────────────────────────────────────────────────────────

HISTORY_KEYWORDS = [
    "who changed", "who modified", "who wrote", "who created",
    "who made", "who did", "who committed", "who updated",
    "last changed", "last modified", "last updated", "last commit",
    "commit history", "change history", "history of",
    "what changed", "what was changed", "recent changes", "recent commits",
    "when was", "when did", "modified by", "changed by",
    "contributors", "who works on", "who developed",
    "made the change", "made the commit", "did the change",
]


# ── Prompt builder ────────────────────────────────────────────────────────────

def build_github_prompt(git_data: dict, history_ctx: str, question: str) -> str:
    """Build the GitHub history prompt."""
    return (
        "You are an MVCore assistant. Answer using the GitHub data below.\n"
        "List each commit as: SHA — Author (Date): message\n"
        "Close with one sentence summarising the change pattern. Under 150 words.\n\n"
        f"{history_ctx}\n"
        f"GITHUB DATA:\n{json.dumps(git_data, indent=2)}\n\n"
        f"QUESTION: {question}"
    )
