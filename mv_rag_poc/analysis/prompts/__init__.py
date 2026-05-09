"""
analysis/prompts/__init__.py
Exposes all prompts and quick reply utilities from a single import point.

Usage:
    from analysis.prompts import SUBROUTINE_PROMPT, DICT_PROMPT, get_quick_reply
"""

from .subroutine_prompt import SUBROUTINE_PROMPT
from .dict_prompt import DICT_PROMPT
from .quick_replies import QUICK_REPLIES, get_quick_reply
from .code_suggestion_prompt import CODE_SUGGESTION_PROMPT
from .impact_analysis_prompt import IMPACT_ANALYSIS_PROMPT
from .unibasic_general_prompt import UNIBASIC_GENERAL_PROMPT
from .jira_prompts import (
    JIRA_KEYWORDS,
    JIRA_TICKET_PATTERN,
    DIRECTIVE_PATTERNS,
    CODE_SUGGESTION_KEYWORDS,
    CODE_CONTEXT_TERMS,
    IMPACT_ANALYSIS_KEYWORDS,
    build_jira_list_prompt,
    build_jira_detail_prompt,
)
from .github_prompts import HISTORY_KEYWORDS, build_github_prompt

__all__ = [
    "SUBROUTINE_PROMPT",
    "DICT_PROMPT",
    "CODE_SUGGESTION_PROMPT",
    "IMPACT_ANALYSIS_PROMPT",
    "UNIBASIC_GENERAL_PROMPT",
    "QUICK_REPLIES",
    "get_quick_reply",
    # Jira
    "JIRA_KEYWORDS",
    "JIRA_TICKET_PATTERN",
    "DIRECTIVE_PATTERNS",
    "CODE_SUGGESTION_KEYWORDS",
    "CODE_CONTEXT_TERMS",
    "IMPACT_ANALYSIS_KEYWORDS",
    "build_jira_list_prompt",
    "build_jira_detail_prompt",
    # GitHub
    "HISTORY_KEYWORDS",
    "build_github_prompt",
]