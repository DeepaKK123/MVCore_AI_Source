"""
analysis/prompts/quick_replies.py
"""

import re

QUICK_REPLIES: dict[str, str] = {
    "hi": (
        "Hello. I'm MVCore, your AI assistant for MultiValue codebases. "
        "Ask me about a subroutine, Jira ticket, Git history, or Confluence documentation."
    ),
    "hello": (
        "Hello. How can I assist you today? "
        "You can ask me about code analysis, impact assessment, Jira tasks, or documentation."
    ),
    "hey": (
        "Hi there. What would you like to explore in your MultiValue codebase?"
    ),
    "how are you": (
        "Ready to assist. What would you like to analyse?"
    ),
    "what can you do": (
        "MVCore can assist with:\n\n"
        "**Code Analysis** — Explain what any subroutine does and how it works\n"
        "**Impact Assessment** — Identify what breaks if a subroutine changes\n"
        "**Code Suggestions** — Suggest MV BASIC changes based on Jira tickets\n"
        "**Jira Integration** — View tickets, sprints, backlog, and bugs\n"
        "**Confluence Docs** — Search and retrieve documentation pages\n"
        "**Git History** — Who changed what, and when\n"
        "**Dict Files** — Explain dictionary file layouts and field structures\n\n"
        "Type a question or pin a subroutine name in the sidebar to get started."
    ),
    "who are you": (
        "I am MVCore — an AI-powered knowledge assistant for MultiValue development teams. "
        "I connect your MV BASIC source code, Jira project, Confluence documentation, "
        "and Git history into a single queryable interface."
    ),
    "thanks":     "Glad to help. Let me know if you have further questions.",
    "thank you":  "You're welcome. Feel free to ask anything else.",
    "bye":        "Goodbye. Return anytime you need assistance with your codebase.",
    "help": (
        "**MVCore — Quick Reference**\n\n"
        "| What to ask | Example |\n"
        "|---|---|\n"
        "| Explain a subroutine | *What does ORD.PROCESS do?* |\n"
        "| Impact analysis | *What breaks if I change INV.UPDATE?* |\n"
        "| Code suggestion | *Suggest a fix for ticket MVAI-12* |\n"
        "| Jira sprint | *What is in the current sprint?* |\n"
        "| Jira bugs | *Show me open bugs* |\n"
        "| Confluence | *Find documentation about order processing* |\n"
        "| Git history | *Who last changed UPDATE.RECORD?* |\n"
        "| Dict layout | *Show me the ORDERS dict file layout* |\n\n"
        "Pin a subroutine name in the sidebar to enable dependency graph analysis."
    ),
}


def get_quick_reply(question: str) -> str | None:
    """
    Return instant reply for greetings and small talk.
    Returns None for real queries that need LLM processing.
    Uses whole-word matching so 'hi' does not match 'this', 'which', 'their' etc.
    """
    cleaned = question.lower().strip().rstrip("!?.,")
    for pattern, reply in QUICK_REPLIES.items():
        if re.search(r'\b' + re.escape(pattern) + r'\b', cleaned):
            return reply
    return None
