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

__all__ = [
    "SUBROUTINE_PROMPT",
    "DICT_PROMPT",
    "CODE_SUGGESTION_PROMPT",
    "IMPACT_ANALYSIS_PROMPT",
    "QUICK_REPLIES",
    "get_quick_reply",
]