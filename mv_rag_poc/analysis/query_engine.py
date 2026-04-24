"""
analysis/query_engine.py
Core orchestration engine.
"""

import difflib
import json
import os
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from langchain_ollama import OllamaLLM as Ollama
from langchain_ollama import OllamaEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document
from graph.dependency_graph import get_impact, load_graph

from analysis.prompts import (
    SUBROUTINE_PROMPT,
    DICT_PROMPT,
    CODE_SUGGESTION_PROMPT,
    IMPACT_ANALYSIS_PROMPT,
    UNIBASIC_GENERAL_PROMPT,
    get_quick_reply,
)
from config import (
    LLM_MODEL,
    EMBED_MODEL,
    CHROMA_PATH,
    GRAPH_PATH,
    SOURCE_DIR,
    DICT_FILE_PATH,
    github_configured,
    jira_configured,
    confluence_configured,
)
from connectors.confluence_connector import (
    search_pages,
    get_page_by_title,
    get_pages_for_subroutine,
    get_recent_pages,
    get_space_pages,
    get_space_summary,
)
from connectors.github_connector import (
    get_file_commits,
    get_file_last_changed,
    get_recent_repo_commits,
    get_contributors,
    search_commits_by_author,
)
from connectors.jira_connector import (
    get_ticket,
    search_tickets,
    get_tickets_for_subroutine,
    get_recent_tickets,
    get_sprint_tickets,
    get_future_sprint_tickets,
    get_backlog_tickets,
    get_planned_features,
    get_open_bugs,
    get_tickets_by_assignee,
    get_project_summary,
)


# ── Paths (resolved from config) ───────────────────────────────────────────────
SOURCE_FILE_PATH = SOURCE_DIR.lstrip("./")


# ── Conversation history helpers ───────────────────────────────────────────────

def _build_history_ctx(history: list) -> str:
    """Format last few exchanges as context for the LLM prompt."""
    if not history:
        return ""
    lines = []
    for msg in history[-6:]:
        role    = "User" if msg["role"] == "user" else "Assistant"
        content = msg["content"]
        if msg["role"] == "assistant":
            content = content[:400]   # keep history brief
        lines.append(f"{role}: {content}")
    return "CONVERSATION HISTORY:\n" + "\n".join(lines) + "\n"


def _extract_ticket_from_history(history: list) -> str:
    """Return the most recently mentioned Jira ticket key from history."""
    for msg in reversed(history or []):
        m = JIRA_TICKET_PATTERN.search(msg.get("content", ""))
        if m:
            return m.group()
    return ""


def _extract_sub_from_history(history: list, known: list) -> str:
    """Return the most recently mentioned known subroutine from history."""
    for msg in reversed(history or []):
        content = msg.get("content", "").upper()
        for sub in sorted(known, key=len, reverse=True):
            if sub in content:
                return sub
    return ""


# ── Known subroutine names (auto-loaded from mv_source folder) ─────────────────
def get_known_subroutines() -> list[str]:
    """
    Scan the mv_source folder and return all filenames as uppercase list.
    e.g. ['CHECK.INVENTORY', 'CUSTOMER.LOOKUP', 'GET.ORDER.DETAILS', ...]
    """
    if not os.path.isdir(SOURCE_FILE_PATH):
        return []
    return [
        f.upper()
        for f in os.listdir(SOURCE_FILE_PATH)
        if os.path.isfile(os.path.join(SOURCE_FILE_PATH, f))
    ]


# ── Question type detection ────────────────────────────────────────────────────
DICT_KEYWORDS = [
    "dict", "dictionary", "layout", "file layout",
    "what fields", "structure of", "field definition",
    "file structure",
]

SUB_KEYWORDS = [
    "subroutine", "what does", "what do", "program",
    "process", "routine", "function", "module",
    "what is", "explain subroutine",
]

CONFLUENCE_KEYWORDS = [
    "confluence", "wiki", "documentation", "docs", "doc",
    "spec", "specification", "design doc", "runbook", "guide",
    "how-to", "how to", "business requirement", "requirement",
    "find the page", "show me the page", "is there a doc",
    "is there any doc", "what does the spec", "what does the doc",
    "what is documented", "knowledge base",
]

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

JIRA_TICKET_PATTERN = re.compile(r'\b[A-Z]{1,10}-\d+\b')
MV_DOT_PATTERN      = re.compile(r'\b([A-Z][A-Z0-9]*(?:\.[A-Z0-9]+){1,})\b')
UPPER_WORD_PATTERN  = re.compile(r'\b([A-Z]{3,})\b')

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


def _extract_directive_name(text: str, known: list[str]) -> str:
    """
    Find names declared via explicit directives like
    'Program to modify: UPDATE.ORDER' in ticket text.
    Prefers matches against known subroutines; falls back to any MV-shaped token.
    """
    if not text:
        return ""
    upper = text.upper()
    known_set = set(known or [])
    for pat in DIRECTIVE_PATTERNS:
        for m in pat.finditer(upper):
            candidate = m.group(1).strip().rstrip('.,;:)')
            if candidate in known_set:
                return candidate
            # Allow MV dot-notation even when not in known set
            if "." in candidate and MV_DOT_PATTERN.fullmatch(candidate):
                return candidate
    return ""

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

    # Which-file / which-program questions (asking where to make a change)
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


UNIBASIC_GENERAL_KEYWORDS = [
    # Explicit language reference
    "unibasic code", "mv basic code", "multivalue code",
    "unibasic syntax", "mv basic syntax", "multivalue syntax",
    "unibasic example", "mv basic example", "unibasic snippet",
    "unibasic program", "unibasic subroutine", "unibasic function",
    "write in unibasic", "code in unibasic", "in unibasic",
    "using unibasic", "with unibasic", "unibasic for",
    "give unibasic", "give me unibasic", "show unibasic",
    # General educational / code generation phrasing
    "hello world",
    "code example", "sample code", "code snippet", "example code", "working example",
    "how do i write", "how do i create", "how do i print",
    "how do i read a file", "how do i write a file",
    "how do i loop", "how do i declare", "how do i use",
    "what is the syntax", "syntax for",
    "teach me", "show me how to",
    "generate code for", "generate unibasic",
]

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


def detect_question_type(question: str, known: list[str] = None) -> str:
    """
    Detect question type. Priority order:
      1. Impact analysis keywords → 'impact_analysis'   (checked FIRST so
         phrases like "analyze the impact if we change..." do not get routed
         to code_suggestion by "change" / "fix" substring matches)
      2. Code suggestion keywords → 'code_suggestion'
      3. Jira ticket ID (PROJ-123) + suggestion → 'code_suggestion'
      4. Confluence keywords → 'confluence'
      5. Jira ticket ID only → 'jira'
      6. Jira keywords → 'jira'
      7. History keywords → 'history'
      8. Known subroutine name → 'subroutine'
      9. Dict keywords → 'dict'
     10. Default → 'subroutine'
    """
    q_lower = question.lower()

    # Priority 0: general UniBasic/MV BASIC code generation or syntax education
    # (no Jira ticket — those stay as code_suggestion)
    if (
        any(kw in q_lower for kw in UNIBASIC_GENERAL_KEYWORDS)
        and not JIRA_TICKET_PATTERN.search(question)
    ):
        return "unibasic_general"

    # Priority 1: impact analysis — must run BEFORE code_suggestion
    if any(kw in q_lower for kw in IMPACT_ANALYSIS_KEYWORDS):
        return "impact_analysis"

    # Priority 2: code suggestion / fix / implement request
    if any(kw in q_lower for kw in CODE_SUGGESTION_KEYWORDS):
        return "code_suggestion"

    # Priority 2a: Jira ticket + code-location language ("which program... MVAI-11",
    # "what subroutine needs to change for PROJ-123") → code_suggestion
    has_ticket = bool(JIRA_TICKET_PATTERN.search(question))
    if has_ticket and any(term in q_lower for term in CODE_CONTEXT_TERMS):
        return "code_suggestion"

    # Priority 2b: Jira ticket + no suggestion → pure Jira lookup
    if has_ticket:
        return "jira"

    # Priority 3: Confluence / documentation keywords
    if any(kw in q_lower for kw in CONFLUENCE_KEYWORDS):
        return "confluence"

    # Priority 4: Jira/project management keywords
    if any(kw in q_lower for kw in JIRA_KEYWORDS):
        return "jira"

    # Priority 5: history / change tracking questions
    if any(kw in q_lower for kw in HISTORY_KEYWORDS):
        return "history"

    q_upper = question.upper()
    for sub in (known or get_known_subroutines()):
        if sub in q_upper:
            return "subroutine"

    if any(kw in q_lower for kw in DICT_KEYWORDS):
        return "dict"
    if any(kw in q_lower for kw in SUB_KEYWORDS):
        return "subroutine"

    return "subroutine"


def extract_name_from_question(question: str, known: list[str] = None) -> str:
    """
    Extract the subroutine or dict file name from a question.

    Strategy:
      1. Exact match against known subroutine filenames (most reliable)
      2. MV dot-notation regex  e.g. GET.ORDER.DETAILS, ORD.PROCESS
      3. Uppercase word fallback

    Examples:
      'What does GET.ORDER.DETAILS do?'    → 'GET.ORDER.DETAILS'
      'Explain ORD.VALIDATE'               → 'ORD.VALIDATE'
      'What does CHECK.INVENTORY do?'      → 'CHECK.INVENTORY'
      'Explain the CUSTOMER dict file'     → 'CUSTOMER'
    """
    q_upper = question.upper()

    # Strip Jira ticket keys (e.g. "MVAI-11") so the prefix isn't mistaken
    # for a subroutine name in Strategy 3 below.
    q_upper_clean = JIRA_TICKET_PATTERN.sub(" ", q_upper)

    # Strategy 1: match against actual files on disk (most reliable)
    # Sort by length descending so GET.ORDER.DETAILS matches before ORDER
    for sub in sorted((known or get_known_subroutines()), key=len, reverse=True):
        if sub in q_upper_clean:
            return sub

    # Strategy 2: MV dot-notation regex — handles 2-part and 3-part names
    # Matches: ORD.PROCESS, GET.ORDER.DETAILS, INV.UPDATE etc.
    dot_matches = MV_DOT_PATTERN.findall(q_upper_clean)
    if dot_matches:
        # Return the longest match (most specific)
        return max(dot_matches, key=len)

    # Strategy 3: any uppercase word (min 3 chars), excluding stop words
    stop = {
        # Articles / conjunctions / pronouns
        "THE", "AND", "FOR", "YOU", "CAN", "ARE", "ANY", "ALL", "SOME",
        "THIS", "THAT", "THESE", "THOSE", "WITH", "FROM", "INTO", "ONTO",
        "HAVE", "HAS", "HAD", "BEEN", "BEING", "MUST", "SHOULD", "COULD",
        "WOULD", "MAY", "WILL", "WAS", "WERE",
        # Question words
        "HOW", "WHY", "WHO", "WHEN", "WHERE", "WHICH", "WHAT", "DOES", "DID",
        # Domain nouns that aren't subroutines
        "DICT", "FILE", "LAYOUT", "FIELDS", "STRUCTURE", "EXPLAIN",
        # Code-suggestion verbs (reported bug: "SUGGEST" was returned)
        "SUGGEST", "SUGGESTED", "SUGGESTION", "FIX", "FIXED", "BUG", "BUGS",
        "TASK", "TASKS", "TICKET", "TICKETS", "STORY", "STORIES", "ISSUE",
        "CODE", "CHANGE", "CHANGED", "CHANGES", "MODIFY", "MODIFIED",
        "IMPLEMENT", "IMPLEMENTED", "BUILD", "RESOLVE", "RESOLVED",
        "PROGRAM", "PROGRAMS", "SUBROUTINE", "SUBROUTINES", "ROUTINE",
        "ROUTINES", "MODULE", "MODULES", "FUNCTION", "FUNCTIONS",
        "WRITE", "UPDATE", "UPDATED", "SHOW", "GIVE", "GIVEN",
        "NEED", "NEEDS", "NEEDED", "MAKE", "MADE", "DEVELOP", "DEVELOPED",
        "ADD", "ADDED", "ENHANCE", "ENHANCEMENT", "PATCH", "APPLY",
        # Jira / project management nouns
        "SPRINT", "SPRINTS", "BACKLOG", "EPIC", "EPICS", "DEFECT",
        "DEFECTS", "STATUS", "PROJECT", "ASSIGNEE", "REPORTER",
        "BLOCKED", "BLOCKING", "COMPLETED", "DONE", "OPEN", "CLOSED",
        # Confluence / docs
        "PAGE", "PAGES", "DOC", "DOCS", "DOCUMENT", "DOCUMENTATION",
        "WIKI", "SPEC", "SPECIFICATION", "RUNBOOK", "GUIDE",
        # GitHub history
        "COMMIT", "COMMITS", "AUTHOR", "CONTRIBUTOR", "CONTRIBUTORS",
        "HISTORY", "RECENT", "LATEST",
        # Misc common English
        "ABOUT", "ALSO", "ONLY", "JUST", "MORE", "LESS", "THAN", "THEN",
        "HERE", "THERE", "NOT", "ITS", "OUR", "YOUR", "THEIR", "TELL",
        "FIND", "SEARCH", "LIST", "LAST", "LASTLY",
    }
    upper_words = UPPER_WORD_PATTERN.findall(q_upper_clean)
    known_set = set(known or [])
    filtered  = [w for w in upper_words if w not in stop]

    # Prefer a word that exactly matches a known subroutine name
    for w in filtered:
        if w in known_set:
            return w

    # Otherwise only accept a candidate if it clearly isn't a plain English word:
    # must be ≥4 chars AND not in the stop set. Single short words (<4) are
    # almost always false positives ("FIX", "BUG", "TASK").
    for w in filtered:
        if len(w) >= 4:
            return w

    return ""


def load_dict_file(name: str) -> str:
    """
    Load a dictionary layout .txt file from DICT_FILE_PATH.
    Tries loose match first, then exact candidate filenames.
    """
    if not name:
        return "Could not determine which dict file to load from the question."

    name_upper = name.upper()

    if os.path.isdir(DICT_FILE_PATH):
        # Loose match — name appears anywhere in filename
        for fname in os.listdir(DICT_FILE_PATH):
            if name_upper in fname.upper():
                fpath = os.path.join(DICT_FILE_PATH, fname)
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    return f.read()

        # Exact candidate filenames
        for candidate in [
            f"{name_upper}.txt",
            f"{name_upper}_DICT.txt",
            f"{name_upper}.DICT.txt",
            name_upper,
        ]:
            fpath = os.path.join(DICT_FILE_PATH, candidate)
            if os.path.exists(fpath):
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    return f.read()

    # List available dict files in error message to help user
    available = []
    if os.path.isdir(DICT_FILE_PATH):
        available = os.listdir(DICT_FILE_PATH)

    return (
        f"❌ Dict file for '{name}' not found in:\n"
        f"   {DICT_FILE_PATH}\n\n"
        f"Available dict files: {', '.join(available) if available else 'none found'}\n"
        f"Make sure '{name_upper}.txt' exists in that folder."
    )


def _detect_file_type(source_code: str) -> str:
    """
    Inspect the first non-comment line of a MV BASIC file.
    Returns 'SUBROUTINE' if it starts with SUBROUTINE/FUNCTION keyword,
    otherwise 'PROGRAM' (standalone executable).
    """
    for line in source_code.splitlines():
        stripped = line.strip().upper()
        if not stripped or stripped.startswith('*') or stripped.startswith('!'):
            continue
        if stripped.startswith('SUBROUTINE') or stripped.startswith('FUNCTION'):
            return 'SUBROUTINE'
        return 'PROGRAM'
    return 'PROGRAM'


_SOURCE_FILE_INDEX: dict[str, str] = {}


def _build_source_file_index() -> dict[str, str]:
    """Scan SOURCE_FILE_PATH once and map UPPERCASE filename -> full path."""
    index: dict[str, str] = {}
    if os.path.isdir(SOURCE_FILE_PATH):
        for fname in os.listdir(SOURCE_FILE_PATH):
            fpath = os.path.join(SOURCE_FILE_PATH, fname)
            if os.path.isfile(fpath):
                index[fname.upper()] = fpath
    return index


def refresh_source_file_index() -> dict[str, str]:
    """Rebuild the filename->path index. Call after GitHub sync."""
    global _SOURCE_FILE_INDEX
    _SOURCE_FILE_INDEX = _build_source_file_index()
    return _SOURCE_FILE_INDEX


def load_source_file(name: str) -> str:
    """
    Directly load a subroutine source file from SOURCE_FILE_PATH.
    Used as fallback when ChromaDB doesn't return the right chunks.
    """
    if not name:
        return ""

    global _SOURCE_FILE_INDEX
    if not _SOURCE_FILE_INDEX:
        _SOURCE_FILE_INDEX = _build_source_file_index()

    fpath = _SOURCE_FILE_INDEX.get(name.upper())
    if not fpath:
        return ""

    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


# ── Shared singletons (module-level) ──────────────────────────────────────────
_SHARED_EMBEDDINGS: OllamaEmbeddings | None = None
_SHARED_VECTORSTORES: dict[str, Chroma]    = {}


def _get_embeddings() -> OllamaEmbeddings:
    global _SHARED_EMBEDDINGS
    if _SHARED_EMBEDDINGS is None:
        print(f"  Loading embeddings: {EMBED_MODEL} ...")
        _SHARED_EMBEDDINGS = OllamaEmbeddings(model=EMBED_MODEL)
    return _SHARED_EMBEDDINGS


def _get_vectorstore(chroma_path: str) -> Chroma:
    vs = _SHARED_VECTORSTORES.get(chroma_path)
    if vs is None:
        print(f"  Loading ChromaDB from {chroma_path} ...")
        vs = Chroma(persist_directory=chroma_path, embedding_function=_get_embeddings())
        _SHARED_VECTORSTORES[chroma_path] = vs
    return vs


def _safe_similarity_search(vectorstore, query: str, k: int, filter_kv: dict | None = None):
    """
    Chroma similarity_search with filter syntax that varies across versions.
    Tries (1) plain filter, (2) $eq wrapped filter, (3) unfiltered + Python post-filter.
    Never raises — returns [] on total failure and logs the reason.
    """
    if filter_kv:
        # Attempt 1: short form — {"key": "value"}
        try:
            return vectorstore.similarity_search(query, k=k, filter=filter_kv)
        except Exception as e1:
            print(f"  Chroma filter (short-form) failed: {e1}")

        # Attempt 2: $eq form — {"key": {"$eq": "value"}}
        try:
            key, val = next(iter(filter_kv.items()))
            return vectorstore.similarity_search(
                query, k=k, filter={key: {"$eq": val}}
            )
        except Exception as e2:
            print(f"  Chroma filter ($eq form) failed: {e2}")

        # Attempt 3: unfiltered + Python post-filter
        try:
            docs = vectorstore.similarity_search(query, k=max(k * 3, 12))
            key, val = next(iter(filter_kv.items()))
            return [d for d in docs if d.metadata.get(key) == val][:k]
        except Exception as e3:
            print(f"  Chroma unfiltered search failed: {e3}")
            return []

    # No filter path
    try:
        return vectorstore.similarity_search(query, k=k)
    except Exception as e:
        print(f"  Chroma similarity_search failed: {e}")
        return []


# ── Main engine ────────────────────────────────────────────────────────────────
class MVAnalysisEngine:

    def __init__(
        self,
        chroma_path: str = CHROMA_PATH,
        graph_path: str = GRAPH_PATH,
        llm_model: str = LLM_MODEL,
        top_k: int = 3,
    ):
        print(f"  Loading LLM: {llm_model} ...")
        self.llm = Ollama(
            model=llm_model,
            temperature=0,
            num_predict=512,
            num_ctx=4096,
        )
        # Larger context LLM for code suggestion — needs to read full source files
        # and emit a 7-section structured response (JIRA Task → Target Program →
        # Current Behaviour → Gap Analysis → Changes Required → Suggested Code →
        # Risks & Verification). num_predict must be large enough for the full
        # Suggested Code block; num_ctx large enough to hold source + RAG excerpts.
        print(f"  Loading code-suggestion LLM (8K ctx): {llm_model} ...")
        self.code_llm = Ollama(
            model=llm_model,
            temperature=0,
            num_predict=4096,
            num_ctx=16384,
        )

        self.embeddings  = _get_embeddings()
        self.vectorstore = _get_vectorstore(chroma_path)
        self.retriever = self.vectorstore.as_retriever(
            search_type="similarity",
            search_kwargs={"k": top_k},
        )

        print(f"  Loading dependency graph from {graph_path} ...")
        self.graph = load_graph(graph_path)
        print("  Engine ready.")

        # Cache known subroutine list at startup
        self.known_subroutines = get_known_subroutines()
        print(f"  Known subroutines: {len(self.known_subroutines)} loaded")

    def _get_relevant_docs(self, question: str, subroutine_name: str = None) -> list:
        """
        Retrieve relevant document chunks from ChromaDB.

        Single similarity search with k=10, then split into exact-match vs others.
        If subroutine_name is given and has no exact match, load file directly from disk.
        """
        if subroutine_name and subroutine_name.strip():
            target = subroutine_name.strip().upper()

            # One retrieval call, wider k, filter in Python
            relevant_docs = _safe_similarity_search(self.vectorstore, question, k=10)

            matching = [
                d for d in relevant_docs
                if target in d.metadata.get("source", "").upper()
            ]
            others = [
                d for d in relevant_docs
                if target not in d.metadata.get("source", "").upper()
            ]
            direct_matching = matching  # alias kept for downstream readability

            # ── KEY FIX: If ChromaDB has NO exact match, load file directly ──
            if not matching and not direct_matching:
                print(f"  ⚠ ChromaDB has no chunks for '{target}'. "
                      f"Loading directly from disk...")
                raw_source = load_source_file(target)
                if raw_source:
                    fallback_doc = Document(
                        page_content=raw_source,
                        metadata={"source": target, "loaded_from": "disk_fallback"}
                    )
                    return [fallback_doc] + others[:2]
                else:
                    print(f"  ✗ '{target}' not found on disk either.")

            # Combine: exact matches first, then others
            seen = set()
            combined = []
            for d in direct_matching + matching + others:
                key = d.page_content[:100]
                if key not in seen:
                    seen.add(key)
                    combined.append(d)

            return combined[:5]

        try:
            return self.retriever.invoke(question)
        except Exception as e:
            print(f"  Retriever failed, using safe search: {e}")
            return _safe_similarity_search(self.vectorstore, question, k=3)

    def prepare(
        self,
        question: str,
        subroutine_name: str = None,
        history: list = None,
        last_ticket_key: str = None,
    ) -> dict:
        """
        Step 1 — RAG retrieval + graph lookup OR dict file load OR connector fetch.
        Runs under the Streamlit spinner.
        """
        history = history or []
        q_type  = detect_question_type(question, self.known_subroutines)

        # Carry forward context from history when question is a follow-up
        history_ticket = (
            JIRA_TICKET_PATTERN.search(question) and
            JIRA_TICKET_PATTERN.search(question).group()
        ) or last_ticket_key or _extract_ticket_from_history(history)

        history_sub = (
            extract_name_from_question(question.upper(), self.known_subroutines)
            or subroutine_name
            or _extract_sub_from_history(history, self.known_subroutines)
        )

        # ── UNIBASIC GENERAL (syntax / code generation / education) ───────────
        if q_type == "unibasic_general":
            return self._prepare_unibasic_general(question, history)

        # ── IMPACT ANALYSIS ────────────────────────────────────────────────────
        if q_type == "impact_analysis":
            return self._prepare_impact_analysis(
                question, history_sub, history, history_ticket
            )

        # ── CODE SUGGESTION ────────────────────────────────────────────────────
        if q_type == "code_suggestion":
            return self._prepare_code_suggestion(
                question, history_sub, history, history_ticket
            )

        # ── CONFLUENCE QUESTION ────────────────────────────────────────────────
        if q_type == "confluence":
            return self._prepare_confluence(question, history_sub, history)

        # ── JIRA QUESTION ──────────────────────────────────────────────────────
        if q_type == "jira":
            return self._prepare_jira(question, history_sub, history)

        # ── GITHUB HISTORY QUESTION ────────────────────────────────────────────
        if q_type == "history":
            return self._prepare_history(question, history_sub, history)

        # ── DICT FILE QUESTION ─────────────────────────────────────────────────
        if q_type == "dict":
            name = history_sub or extract_name_from_question(question.upper(), self.known_subroutines)
            dict_content = load_dict_file(name)
            history_ctx  = _build_history_ctx(history)
            prompt = DICT_PROMPT.format(
                dict_context=dict_content,
                question=f"{history_ctx}\nQUESTION: {question}" if history_ctx else question,
            )
            return {
                "prompt": prompt,
                "sources": [f"dict_file_layout/{name}.txt"],
                "impact": {},
                "question_type": "dict",
            }

        # ── SUBROUTINE QUESTION ────────────────────────────────────────────────
        subroutine_name = (
            (subroutine_name.strip() if subroutine_name else None)
            or history_sub
        )
        if subroutine_name:
            print(f"  Resolved subroutine: '{subroutine_name}'")

        relevant_docs = self._get_relevant_docs(question, subroutine_name)

        # Check if we actually got anything useful
        if not relevant_docs:
            available = ", ".join(self.known_subroutines)
            not_found_prompt = (
                f"The subroutine '{subroutine_name}' was not found in the codebase.\n"
                f"Available subroutines: {available}"
            )
            return {
                "prompt": not_found_prompt,
                "sources": [],
                "impact": {},
                "question_type": "not_found",
            }

        context = "\n\n---\n\n".join(
            [f"[Source: {d.metadata.get('source', 'unknown')}]\n{d.page_content}"
             for d in relevant_docs]
        )

        graph_context = "No specific subroutine identified for graph traversal."
        impact = {}
        if subroutine_name:
            impact = get_impact(self.graph, subroutine_name)
            graph_context = json.dumps(impact, indent=2)

        # ── Cross-linking: Jira + Confluence in parallel ──────────────────────
        jira_data       = {}
        confluence_data = {}
        extra_context   = ""

        if subroutine_name:
            _futures = {}
            with ThreadPoolExecutor(max_workers=2) as _pool:
                if jira_configured():
                    _futures["jira"] = _pool.submit(
                        get_tickets_for_subroutine, subroutine_name, 5
                    )
                if confluence_configured():
                    _futures["confluence"] = _pool.submit(
                        get_pages_for_subroutine, subroutine_name, 3
                    )

            if "jira" in _futures:
                try:
                    tickets = _futures["jira"].result()
                    if tickets and "error" not in tickets[0]:
                        jira_data = {"related_tickets": tickets}
                        extra_context += (
                            f"\n\nRELATED JIRA TICKETS:\n"
                            f"{json.dumps(tickets, indent=2)}"
                        )
                except Exception:
                    pass

            if "confluence" in _futures:
                try:
                    pages = _futures["confluence"].result()
                    if pages and "error" not in pages[0]:
                        confluence_data = {"related_pages": pages}
                        extra_context += (
                            f"\n\nRELATED CONFLUENCE PAGES:\n"
                            f"{json.dumps(pages, indent=2)}"
                        )
                except Exception:
                    pass

        history_ctx = _build_history_ctx(history)
        full_question = (
            f"{history_ctx}\nQUESTION: {question}" if history_ctx else question
        )

        prompt = SUBROUTINE_PROMPT.format(
            context=context,
            graph_context=graph_context + extra_context,
            question=full_question,
        )

        return {
            "prompt":              prompt,
            "sources":             [d.metadata.get("source", "") for d in relevant_docs],
            "impact":              impact,
            "question_type":       "subroutine",
            "detected_subroutine": subroutine_name,
            "detected_ticket":     history_ticket or "",
            "jira_data":           jira_data,
            "confluence_data":     confluence_data,
        }

    # UniBasic statement keywords used to run targeted per-operation searches
    _MV_OPS = [
        "OPEN", "READ", "READU", "READV", "READVU",
        "WRITE", "WRITEV", "WRITEU", "WRITET",
        "DELETE", "DELETEU",
        "LOCATE", "EXTRACT", "INSERT", "REMOVE", "REPLACE",
        "PRINT", "DISPLAY", "INPUT", "INPUTNULL", "CRT",
        "CALL", "RETURN", "SUBROUTINE", "FUNCTION",
        "SELECT", "READNEXT", "CLEARSELECT", "SELECTV",
        "FOR", "NEXT", "LOOP", "REPEAT", "WHILE", "UNTIL",
        "IF", "CASE", "BEGIN CASE", "END CASE",
        "MATREAD", "MATWRITE", "DIM", "MAT",
        "LOCK", "UNLOCK", "COMMIT", "ROLLBACK",
        "CONVERT", "TRIM", "FIELD", "LEN", "NUM", "STR",
    ]

    _NL_TO_OP = {
        "open": "OPEN", "read": "READ", "write": "WRITE",
        "print": "PRINT", "display": "PRINT", "show": "PRINT",
        "delete": "DELETE", "loop": "LOOP", "select": "SELECT",
        "find": "LOCATE", "input": "INPUT", "call": "CALL",
        "lock": "READU", "extract": "EXTRACT", "insert": "INSERT",
    }

    def _prepare_unibasic_general(self, question: str, history: list = None) -> dict:
        """Handle general UniBasic/MV BASIC code generation and syntax questions.

        Uses multi-query retrieval: one search per detected operation keyword so
        that a question like 'OPEN + READ + PRINT' retrieves syntax docs for all
        three operations, not just whichever scored highest in a single search.
        """
        history = history or []

        # ── Detect UniBasic operation keywords from the question ───────────────
        q_upper = question.upper()
        q_lower = question.lower()

        detected_ops: list[str] = []
        for op in self._MV_OPS:
            if re.search(r'\b' + op + r'\b', q_upper):
                detected_ops.append(op)
        for word, op in self._NL_TO_OP.items():
            if word in q_lower and op not in detected_ops:
                detected_ops.append(op)

        # ── Multi-query retrieval — one search per detected operation ──────────
        all_docs: list = []
        seen: set = set()

        def _add(docs):
            for d in docs:
                key = d.page_content[:120]
                if key not in seen:
                    seen.add(key)
                    all_docs.append(d)

        # Primary search: full question
        _add(_safe_similarity_search(
            self.vectorstore, question, k=6,
            filter_kv={"source_type": "mv_syntax"},
        ))

        # Targeted search per detected operation (cap at 6 ops to stay fast)
        for op in detected_ops[:6]:
            _add(_safe_similarity_search(
                self.vectorstore,
                f"UniBasic {op} statement syntax example",
                k=3, filter_kv={"source_type": "mv_syntax"},
            ))

        # Fallback: unfiltered if mv_syntax collection is empty / not yet indexed
        if not all_docs:
            _add(_safe_similarity_search(self.vectorstore, question, k=8))

        syntax_context = (
            "\n\n---\n\n".join(d.page_content for d in all_docs[:14])
            if all_docs else
            "No syntax reference found in the knowledge base."
        )

        history_ctx  = _build_history_ctx(history)
        ops_hint     = (
            f"\nRequired operations — ALL must appear in the generated code: "
            + ", ".join(detected_ops)
            if detected_ops else ""
        )
        full_question = (
            f"{history_ctx}\nQUESTION: {question}{ops_hint}"
            if history_ctx else
            f"QUESTION: {question}{ops_hint}"
        )

        prompt = UNIBASIC_GENERAL_PROMPT.format(
            syntax_context=syntax_context,
            question=full_question,
        )

        print(f"  UniBasic general: detected_ops={detected_ops}, "
              f"syntax_chunks={len(all_docs)}")

        return {
            "prompt":        prompt,
            "sources":       list({d.metadata.get("source", "") for d in all_docs}),
            "impact":        {},
            "question_type": "unibasic_general",
        }

    def _prepare_impact_analysis(
        self,
        question: str,
        subroutine_name: str = None,
        history: list = None,
        ticket_key_hint: str = None,
    ) -> dict:
        """
        Build an IMPACT ANALYSIS prompt — analysis only, NO code suggestion.

        Reuses the same program-discovery hierarchy as _prepare_code_suggestion
        (explicit name → directive in ticket → RAG), plus injects the dependency
        graph context so the LLM can reason about callers / callees / impacted
        files without writing code.
        """
        history = history or []
        name    = subroutine_name or extract_name_from_question(question.upper(), self.known_subroutines)

        # Reject noise names (same logic as code_suggestion)
        if name and name not in self.known_subroutines and "." not in name:
            print(f"  Ignoring non-MV name '{name}' — will extract from ticket instead.")
            name = ""

        source_code = load_source_file(name) if name else ""
        if not source_code and name:
            docs = self._get_relevant_docs(question, name)
            source_code = "\n\n".join(d.page_content for d in docs) if docs else ""
        file_type = _detect_file_type(source_code) if source_code else "PROGRAM"

        jira_data  = {}
        ticket_key = (
            (JIRA_TICKET_PATTERN.search(question) and
             JIRA_TICKET_PATTERN.search(question).group())
            or ticket_key_hint
            or _extract_ticket_from_history(history)
        )

        history_ctx = _build_history_ctx(history)
        requirement = f"{history_ctx}\nDeveloper request: {question}" if history_ctx else f"Developer request: {question}"

        if ticket_key and jira_configured():
            try:
                jira_data = get_ticket(ticket_key)
                if "error" not in jira_data:
                    parts = [
                        f"Ticket  : {jira_data.get('key')} — {jira_data.get('summary')}",
                        f"Type    : {jira_data.get('type')} | Priority: {jira_data.get('priority')} | Status: {jira_data.get('status')}",
                        f"Assignee: {jira_data.get('assignee')}",
                    ]
                    if jira_data.get("description"):
                        parts.append(f"\nDescription:\n{jira_data['description']}")
                    if jira_data.get("acceptance_criteria"):
                        parts.append(f"\nAcceptance Criteria:\n{jira_data['acceptance_criteria']}")
                    if jira_data.get("comments"):
                        comment_lines = "\n".join(
                            f"  [{c['date']}] {c['author']}: {c['body']}"
                            for c in jira_data["comments"][-5:]
                        )
                        parts.append(f"\nComments:\n{comment_lines}")
                    ticket_block = "\n".join(parts)

                    comments_text = " ".join(
                        c.get("body", "") for c in jira_data.get("comments", [])
                    )
                    full_ticket_text = (
                        (jira_data.get("summary", "") or "") + "\n" +
                        (jira_data.get("description", "") or "") + "\n" +
                        (jira_data.get("acceptance_criteria", "") or "") + "\n" +
                        comments_text
                    )

                    if not name:
                        directive_name = _extract_directive_name(
                            full_ticket_text, self.known_subroutines
                        )
                        if directive_name:
                            print(f"  [impact] Directive-matched subroutine: {directive_name}")
                            name = directive_name
                            source_code = load_source_file(name) or source_code
                            file_type   = _detect_file_type(source_code) if source_code else "PROGRAM"

                    if not name:
                        name = extract_name_from_question(
                            full_ticket_text.upper(), self.known_subroutines
                        )
                        if name:
                            print(f"  [impact] Extracted subroutine from ticket text: {name}")
                            source_code = load_source_file(name) or source_code
                            file_type   = _detect_file_type(source_code) if source_code else "PROGRAM"

                    if not name:
                        rag_query = (
                            jira_data.get("summary", "") + " " +
                            jira_data.get("description", "")[:500]
                        ).strip() or question
                        src_docs = _safe_similarity_search(
                            self.vectorstore, rag_query, k=8,
                            filter_kv={"source_type": "source_code"},
                        )
                        file_hits: Counter = Counter()
                        for d in src_docs:
                            src = d.metadata.get("source", "")
                            if src:
                                file_hits[Path(src).name.upper()] += 1
                        if file_hits:
                            best_file, _ = file_hits.most_common(1)[0]
                            candidate = best_file
                            if candidate in self.known_subroutines:
                                name = candidate
                            else:
                                stem = Path(best_file).stem
                                if stem in self.known_subroutines:
                                    name = stem
                            if name:
                                print(f"  [impact] RAG-discovered subroutine: {name}")
                                source_code = load_source_file(name) or source_code
                                file_type   = _detect_file_type(source_code) if source_code else "PROGRAM"

                    requirement = f"{history_ctx}\n{ticket_block}\n\nDeveloper request: {question}"
            except Exception:
                pass

        # Dependency graph context — callers / callees / impacted files
        impact = {}
        if name:
            try:
                impact = get_impact(self.graph, name)
            except Exception:
                impact = {}
        graph_context = json.dumps(impact, indent=2) if impact else (
            "No dependency graph data available for this file."
        )

        print(f"  Impact analysis: file={name}, type={file_type}, "
              f"source_len={len(source_code)}, ticket={ticket_key or 'none'}")

        prompt = IMPACT_ANALYSIS_PROMPT.format(
            subroutine     = name or "Unknown",
            file_type      = file_type,
            source_code    = source_code if source_code else "Source code not found in codebase.",
            requirement    = requirement,
            question       = question,
            graph_context  = graph_context,
        )

        return {
            "prompt":              prompt,
            "sources":             [name] if name else [],
            "impact":              impact,
            "question_type":       "impact_analysis",
            "detected_subroutine": name,
            "detected_ticket":     ticket_key or "",
            "jira_data":           {"tickets": [jira_data]} if jira_data and "error" not in jira_data else {},
            "confluence_data":     {},
        }

    def _prepare_code_suggestion(
        self,
        question: str,
        subroutine_name: str = None,
        history: list = None,
        ticket_key_hint: str = None,
    ) -> dict:
        """
        Build a code suggestion prompt combining:
          1. Complete MV BASIC source file from disk (full file, no truncation)
          2. Jira ticket — description, acceptance criteria, comments
          3. Confluence pages linked to the ticket
          4. mv_syntax RAG docs as the authoritative UniBasic syntax reference
          5. Conversation history for follow-up context
        """
        history = history or []
        name    = subroutine_name or extract_name_from_question(question.upper(), self.known_subroutines)

        # Reject noise names: if the extracted word isn't a known subroutine and
        # doesn't look like MV dot-notation, drop it. Lets the Jira ticket text
        # drive name resolution below instead of searching for "SUGGEST"/"FIX".
        if name and name not in self.known_subroutines and "." not in name:
            print(f"  Ignoring non-MV name '{name}' — will extract from ticket instead.")
            name = ""

        # ── 1. Full source code from disk ────────────────────────────────────
        source_code = load_source_file(name) if name else ""
        if not source_code and name:
            # RAG fallback — retrieve relevant chunks
            docs = self._get_relevant_docs(question, name)
            source_code = "\n\n".join(d.page_content for d in docs) if docs else ""
        file_type = _detect_file_type(source_code) if source_code else "PROGRAM"

        # ── 2. Jira ticket — from question OR conversation history ────────────
        jira_data       = {}
        confluence_data = {}
        ticket_key      = (
            (JIRA_TICKET_PATTERN.search(question) and
             JIRA_TICKET_PATTERN.search(question).group())
            or ticket_key_hint
            or _extract_ticket_from_history(history)
        )

        history_ctx = _build_history_ctx(history)
        requirement = f"{history_ctx}\nDeveloper request: {question}" if history_ctx else f"Developer request: {question}"

        if ticket_key and jira_configured():
            try:
                jira_data = get_ticket(ticket_key)
                if "error" not in jira_data:
                    parts = [
                        f"Ticket  : {jira_data.get('key')} — {jira_data.get('summary')}",
                        f"Type    : {jira_data.get('type')} | Priority: {jira_data.get('priority')} | Status: {jira_data.get('status')}",
                        f"Assignee: {jira_data.get('assignee')}",
                    ]
                    if jira_data.get("description"):
                        parts.append(f"\nDescription:\n{jira_data['description']}")
                    if jira_data.get("acceptance_criteria"):
                        parts.append(f"\nAcceptance Criteria:\n{jira_data['acceptance_criteria']}")
                    if jira_data.get("comments"):
                        comment_lines = "\n".join(
                            f"  [{c['date']}] {c['author']}: {c['body']}"
                            for c in jira_data["comments"][-5:]
                        )
                        parts.append(f"\nComments:\n{comment_lines}")
                    if jira_data.get("linked_issues"):
                        linked = ", ".join(
                            f"{lk['key']} ({lk['type']})" for lk in jira_data["linked_issues"]
                        )
                        parts.append(f"\nLinked Issues: {linked}")
                    if jira_data.get("subtasks"):
                        subs = ", ".join(
                            f"{s['key']}: {s['summary']} [{s['status']}]"
                            for s in jira_data["subtasks"]
                        )
                        parts.append(f"\nSubtasks: {subs}")

                    ticket_block = "\n".join(parts)

                    # Build the full ticket text — summary + description + ALL
                    # comments — so directives like "Program to modify: X" that
                    # developers add in comments are also scanned.
                    comments_text = " ".join(
                        c.get("body", "") for c in jira_data.get("comments", [])
                    )
                    full_ticket_text = (
                        (jira_data.get("summary", "") or "") + "\n" +
                        (jira_data.get("description", "") or "") + "\n" +
                        (jira_data.get("acceptance_criteria", "") or "") + "\n" +
                        comments_text
                    )

                    # (a) Explicit directive match first — highest signal
                    if not name:
                        directive_name = _extract_directive_name(
                            full_ticket_text, self.known_subroutines
                        )
                        if directive_name:
                            print(f"  Directive-matched subroutine: {directive_name} "
                                  f"(from ticket comments/description)")
                            name = directive_name
                            source_code = load_source_file(name) or source_code
                            file_type   = _detect_file_type(source_code) if source_code else "PROGRAM"

                    # (b) Generic extraction across summary + description + comments
                    if not name:
                        name = extract_name_from_question(
                            full_ticket_text.upper(), self.known_subroutines
                        )
                        if name:
                            print(f"  Extracted subroutine from ticket text: {name}")
                            source_code = load_source_file(name) or source_code
                            file_type   = _detect_file_type(source_code) if source_code else "PROGRAM"

                    # (c) RAG discovery: if ticket text still didn't mention a
                    # subroutine by exact name, search the MV source chunks for
                    # the most relevant program against the ticket text.
                    if not name:
                        rag_query = (
                            jira_data.get("summary", "") + " " +
                            jira_data.get("description", "")[:500]
                        ).strip() or question
                        src_docs = _safe_similarity_search(
                            self.vectorstore, rag_query, k=8,
                            filter_kv={"source_type": "source_code"},
                        )
                        # Tally which file had the most relevant chunks
                        file_hits: Counter = Counter()
                        for d in src_docs:
                            src = d.metadata.get("source", "")
                            if src:
                                file_hits[Path(src).name.upper()] += 1
                        if file_hits:
                            best_file, _ = file_hits.most_common(1)[0]
                            # Verify against known subroutines
                            candidate = best_file
                            if candidate in self.known_subroutines:
                                name = candidate
                            else:
                                # Filename may include extension; strip and retry
                                stem = Path(best_file).stem
                                if stem in self.known_subroutines:
                                    name = stem
                            if name:
                                print(f"  RAG-discovered subroutine: {name} "
                                      f"(from {len(src_docs)} ticket-relevant chunks)")
                                source_code = load_source_file(name) or source_code
                                file_type   = _detect_file_type(source_code) if source_code else "PROGRAM"

                    # ── 3. Confluence docs for this ticket ───────────────────
                    if confluence_configured():
                        try:
                            pages = search_pages(ticket_key, max_results=4)
                            if pages and "error" not in pages[0]:
                                confluence_data = {"related_pages": pages}
                                conf_snippets = "\n\n".join(
                                    f"[{p.get('title')}]\n{p.get('content', '')[:600]}"
                                    for p in pages[:3]
                                )
                                ticket_block += f"\n\nConfluence Documentation:\n{conf_snippets}"
                        except Exception:
                            pass

                    requirement = f"{history_ctx}\n{ticket_block}\n\nDeveloper request: {question}"
            except Exception:
                pass

        # ── 4. mv_syntax RAG — authoritative UniBasic reference ──────────────
        # Resilient filtered search — tolerates Chroma version differences
        syntax_query = f"UniBasic MV BASIC {question} {name or ''}".strip()
        syntax_docs  = _safe_similarity_search(
            self.vectorstore, syntax_query, k=6,
            filter_kv={"source_type": "mv_syntax"},
        )

        syntax_context = (
            "\n\n---\n\n".join(d.page_content for d in syntax_docs)
            if syntax_docs else
            "No syntax reference found in the knowledge base."
        )

        print(f"  Code suggestion: file={name}, type={file_type}, "
              f"source_len={len(source_code)}, syntax_docs={len(syntax_docs)}, "
              f"ticket={ticket_key or 'none'}")

        prompt = CODE_SUGGESTION_PROMPT.format(
            subroutine     = name or "Unknown",
            file_type      = file_type,
            source_code    = source_code if source_code else "Source code not found in codebase.",
            requirement    = requirement,
            syntax_context = syntax_context,
            question       = question,
        )

        return {
            "prompt":              prompt,
            "sources":             [name] if name else [],
            "impact":              {},
            "question_type":       "code_suggestion",
            "detected_subroutine": name,
            "detected_ticket":     ticket_key or "",
            "jira_data":           {"tickets": [jira_data]} if jira_data and "error" not in jira_data else {},
            "confluence_data":     confluence_data,
        }

    def _prepare_confluence(self, question: str, subroutine_name: str = None, history: list = None) -> dict:
        """Handle Confluence / documentation questions via live Confluence API."""
        if not confluence_configured():
            return {
                "prompt": (
                    "Confluence is not configured. Add JIRA_URL, JIRA_EMAIL, JIRA_TOKEN "
                    "and CONFLUENCE_SPACE to .env\n"
                    f"Question: {question}"
                ),
                "sources": [], "impact": {}, "question_type": "confluence",
                "confluence_data": {}, "detected_subroutine": None,
            }

        q_lower = question.lower()
        name = subroutine_name or extract_name_from_question(question.upper(), self.known_subroutines)
        confluence_data = {}

        # ── Title extraction: strip trigger phrase to get the actual page title ──
        # e.g. "Show me the page CR_ORDER_MAINTENANCE_ORD-2025-OCT_Doc"
        #       → title = "CR_ORDER_MAINTENANCE_ORD-2025-OCT_Doc"
        _TITLE_TRIGGERS = [
            "show me the page", "get the page", "find the page",
            "show me the doc", "get the doc", "find the doc",
            "open the page", "open the doc",
        ]

        def _extract_page_title(q: str) -> str:
            q_l = q.lower()
            for trigger in _TITLE_TRIGGERS:
                if trigger in q_l:
                    idx = q_l.index(trigger) + len(trigger)
                    return q[idx:].strip().strip('"\'')
            return ""

        # ── Search query: strip question words for cleaner CQL ─────────────────
        _QUESTION_STOPWORDS = re.compile(
            r'\b(find|search|show|get|is there|are there|any|the|a|an|'
            r'documentation|docs|doc|about|for|related to|what is|tell me)\b',
            re.IGNORECASE,
        )

        def _clean_search_query(q: str) -> str:
            cleaned = _QUESTION_STOPWORDS.sub("", q).strip()
            # collapse whitespace
            return re.sub(r'\s+', ' ', cleaned).strip() or q

        try:
            # Space-level overview
            if any(k in q_lower for k in ["how much doc", "how many page", "space summary", "tell me about the wiki", "wiki overview"]):
                confluence_data = get_space_summary()

            # List all pages
            elif any(k in q_lower for k in ["list all", "list doc", "all pages", "all wiki", "what documentation exists"]):
                confluence_data = {"pages": get_space_pages(max_results=50)}

            # Recently updated pages
            elif any(k in q_lower for k in ["recent", "latest", "last updated", "recently updated"]):
                confluence_data = {"recent_pages": get_recent_pages(max_results=10)}

            # Get a specific page by title — extract title after the trigger phrase
            elif any(k in q_lower for k in _TITLE_TRIGGERS):
                title = _extract_page_title(question)
                if not title:
                    title = name or question
                confluence_data = get_page_by_title(title)

            # Pages mentioning a known subroutine
            elif name and name in self.known_subroutines:
                pages = get_pages_for_subroutine(name, max_results=5)
                confluence_data = {"related_pages": pages, "subroutine": name}

            # General search — use cleaned keywords, not the full question sentence
            else:
                query = _clean_search_query(question)
                print(f"  Confluence search query: '{query}'")
                results = search_pages(query, max_results=10)
                # If no results, retry with the original question
                if not results or (results and "error" in results[0]):
                    results = search_pages(question, max_results=10)
                confluence_data = {"search_results": results, "query": query}

        except Exception as e:
            confluence_data = {"error": str(e)}

        history_ctx = _build_history_ctx(history or [])
        prompt = (
            "You are an MVCore assistant. Answer using the Confluence data below.\n"
            "List each relevant page: title, one-line description, and URL.\n"
            "Follow with a direct one-sentence answer to the question. Under 150 words.\n\n"
            f"{history_ctx}\n"
            f"CONFLUENCE DATA:\n{json.dumps(confluence_data, indent=2)}\n\n"
            f"QUESTION: {question}"
        )

        return {
            "prompt":              prompt,
            "sources":             [],
            "impact":              {},
            "question_type":       "confluence",
            "confluence_data":     confluence_data,
            "detected_subroutine": name,
            "detected_ticket":     _extract_ticket_from_history(history or []),
        }

    def _prepare_jira(self, question: str, subroutine_name: str = None, history: list = None) -> dict:
        """Handle Jira questions — routes to the right Jira API call."""
        if not jira_configured():
            return {
                "prompt": (
                    "Jira is not configured. Add JIRA_URL, JIRA_EMAIL, JIRA_TOKEN to .env\n"
                    f"Question: {question}"
                ),
                "sources": [], "impact": {}, "question_type": "jira", "jira_data": {},
                "detected_subroutine": None,
            }

        q_lower = question.lower()
        name    = subroutine_name or extract_name_from_question(question.upper(), self.known_subroutines)
        jira_data = {}

        try:
            # Specific ticket key e.g. PROJ-123
            ticket_match = JIRA_TICKET_PATTERN.search(question)
            if ticket_match:
                jira_data = get_ticket(ticket_match.group())
                # Wrap single ticket so render_jira can find it
                if jira_data and "error" not in jira_data:
                    jira_data = {"tickets": [jira_data]}

            # Tickets related to a subroutine
            elif any(k in q_lower for k in [
                "related ticket", "which ticket", "what ticket", "ticket for",
                "stories for", "linked to",
            ]):
                jira_data = {"related_tickets": get_tickets_for_subroutine(name) if name else []}

            # Upcoming / next / future sprint — MUST come before current sprint check
            elif any(k in q_lower for k in [
                "upcoming sprint", "next sprint", "future sprint",
                "what's in the upcoming", "what is in the upcoming",
                "what's in the next sprint", "what is in the next sprint",
                "planned for next", "what is planned", "what is coming",
                "future task", "future feature", "planned feature",
                "planned sprint", "upcoming feature", "roadmap", "next release",
                "what are we building next", "what is coming next",
            ]):
                jira_data = get_future_sprint_tickets()

            # Backlog
            elif any(k in q_lower for k in ["backlog", "not in sprint", "unplanned"]):
                jira_data = {"backlog_tickets": get_backlog_tickets()}

            # Completed / delivered work
            elif any(k in q_lower for k in [
                "what did we complete", "what was completed", "what was delivered",
                "what was done", "completed tickets", "closed tickets",
                "done this sprint", "delivered this sprint", "what has been done",
            ]):
                from connectors.jira_connector import search_tickets
                project_clause = f'project = "{__import__("config").JIRA_PROJECT}" AND ' if __import__("config").JIRA_PROJECT else ""
                done_tickets = search_tickets(f"{project_clause}status = Done ORDER BY updated DESC", max_results=20)
                jira_data = {"tickets": done_tickets, "sprint_name": "Completed Work"}

            # Blocked / at risk
            elif any(k in q_lower for k in [
                "blocked", "blocking", "what is blocked", "what's blocked",
                "at risk", "what's at risk", "what is at risk", "impediment", "overdue",
            ]):
                from connectors.jira_connector import search_tickets
                project_clause = f'project = "{__import__("config").JIRA_PROJECT}" AND ' if __import__("config").JIRA_PROJECT else ""
                blocked = search_tickets(f"{project_clause}status = Blocked OR labels = blocked ORDER BY priority DESC", max_results=20)
                jira_data = {"tickets": blocked, "sprint_name": "Blocked / At Risk"}

            # Open bugs / known issues
            elif any(k in q_lower for k in ["bug", "bugs", "open bug", "known issue", "defect"]):
                jira_data = {"open_bugs": get_open_bugs()}

            # Who is working on what / team workload
            elif any(k in q_lower for k in [
                "assigned to", "working on", "who is working", "team workload",
                "who owns", "tickets for", "what is the team",
            ]):
                person = extract_name_from_question(question.upper(), self.known_subroutines)
                jira_data = {"tickets": get_tickets_by_assignee(person or "")}

            # Recent activity
            elif any(k in q_lower for k in ["recent", "latest", "last updated", "recently"]):
                jira_data = {"recent_tickets": get_recent_tickets()}

            # Project health / overview
            elif any(k in q_lower for k in [
                "summary", "overview", "status", "how is the project",
                "project status", "progress update", "how are we doing",
                "project health", "bug count",
            ]):
                jira_data = get_project_summary()

            # Current sprint (catch-all for sprint questions)
            elif any(k in q_lower for k in [
                "sprint", "current sprint", "this sprint", "active sprint",
                "what's in the sprint", "what is in the sprint",
                "what are we working on", "sprint tasks", "sprint items",
                "sprint stories", "sprint goal", "sprint scope",
            ]):
                jira_data = get_sprint_tickets()

            # Default: search by subroutine name or general recent tickets
            else:
                jira_data = (
                    {"related_tickets": get_tickets_for_subroutine(name)}
                    if name else
                    {"recent_tickets": get_recent_tickets(max_results=10)}
                )

        except Exception as e:
            jira_data = {"error": str(e)}

        # ── Cross-link: search Confluence for related docs ───────────────────────
        confluence_data = {}
        if confluence_configured():
            try:
                tickets     = jira_data.get("tickets", [])
                sprint_name = jira_data.get("sprint_name", "")

                # Build ordered list of search terms — most specific first
                search_attempts = []

                # 1. Individual ticket keys (most likely to appear in Confluence docs)
                for t in tickets[:3]:
                    key = t.get("key", "")
                    if key:
                        search_attempts.append(key)

                # 2. Ticket summary keywords (first 4 words)
                for t in tickets[:2]:
                    summary = t.get("summary", "")
                    if summary:
                        keywords = " ".join(summary.split()[:4])
                        search_attempts.append(keywords)

                # 3. Epic name if present
                for t in tickets[:3]:
                    epic = t.get("epic", "")
                    if epic and epic not in search_attempts:
                        search_attempts.append(epic[:50])

                # 4. Sprint name as last resort
                if sprint_name:
                    search_attempts.append(sprint_name)

                # 5. Subroutine name or question
                if name:
                    search_attempts.append(name)

                # Fire all search attempts in parallel (up to 5) — ordered merge
                found_pages = []
                seen_ids = set()
                if search_attempts:
                    top_attempts = search_attempts[:5]
                    with ThreadPoolExecutor(max_workers=len(top_attempts)) as pool:
                        futures = [
                            pool.submit(search_pages, term, 3) for term in top_attempts
                        ]
                        for fut in futures:
                            if len(found_pages) >= 5:
                                break
                            try:
                                results = fut.result()
                            except Exception:
                                continue
                            if results and "error" not in results[0]:
                                for p in results:
                                    pid = p.get("id") or p.get("title")
                                    if pid and pid not in seen_ids:
                                        seen_ids.add(pid)
                                        found_pages.append(p)

                if found_pages:
                    confluence_data = {
                        "related_pages": found_pages[:5],
                        "query": search_attempts[0] if search_attempts else "",
                    }
            except Exception:
                pass

        sprint_name  = jira_data.get("sprint_name", "")
        conf_pages   = confluence_data.get("related_pages", [])
        conf_context = ""
        if conf_pages:
            titles_list = [p.get("title", "") for p in conf_pages[:3] if p.get("title")]
            conf_context = f"\n\nRELATED CONFLUENCE DOCS: {', '.join(titles_list)}"

        history_ctx = _build_history_ctx(history or [])
        ticket_key  = (
            (JIRA_TICKET_PATTERN.search(question) and
             JIRA_TICKET_PATTERN.search(question).group())
            or _extract_ticket_from_history(history or [])
        )

        # ── Detect intent: single-ticket detail vs sprint/list overview ───────
        q_lower_intent = question.lower()
        _detail_triggers = [
            "more detail", "details of", "tell me about", "explain", "describe",
            "what is in ticket", "what does ticket", "full detail", "show me ticket",
            "read the task", "read task", "read ticket", "what is the task",
        ]
        is_detail_query = (
            ticket_key and
            (any(t in q_lower_intent for t in _detail_triggers) or
             not any(k in q_lower_intent for k in ["sprint", "backlog", "upcoming", "current", "open bug"]))
        )

        if is_detail_query:
            # ── Detail prompt — show every field ─────────────────────────────
            prompt = (
                "You are an MVCore assistant. The user wants FULL DETAILS of a Jira ticket.\n"
                "IMPORTANT: Copy all field values VERBATIM — do NOT paraphrase or alter any names.\n\n"
                "Format your response using these sections (skip any section that has no data):\n\n"
                "**[KEY] — Summary**\n"
                "- **Type:** | **Priority:** | **Status:** | **Assignee:** | **Reporter:**\n"
                "- **Created:** | **Updated:** | **Sprint:** | **Epic:**\n"
                "- **URL:** (if available)\n\n"
                "**Description**\n"
                "Full description text from the ticket.\n\n"
                "**Acceptance Criteria**\n"
                "List each criterion on a new line.\n\n"
                "**Subtasks** (if any)\n"
                "- SUBKEY: Summary (Status)\n\n"
                "**Linked Issues** (if any)\n"
                "- TYPE: KEY — Summary\n\n"
                "**Comments** (most recent first, all comments)\n"
                "- [Date] Author: comment text\n\n"
                "**Related Confluence Docs** (if any)\n"
                "List page titles.\n\n"
                f"{history_ctx}\n"
                f"JIRA DATA:\n{json.dumps(jira_data, indent=2)}"
                f"{conf_context}\n\n"
                f"QUESTION: {question}"
            )
        else:
            # ── List prompt — concise overview per ticket ──────────────────
            prompt = (
                "You are an MVCore assistant. Answer using the Jira data below.\n"
                "IMPORTANT: Copy all field values (sprint name, ticket keys, summaries, assignee names) "
                "VERBATIM from the data — do NOT paraphrase, correct spelling, or alter any names.\n"
                f"{'Start with exactly: **Sprint: ' + sprint_name + '**' if sprint_name else ''}\n"
                "For each ticket show:\n"
                "  **KEY** — Summary\n"
                "  Type: X | Priority: X | Status: X | Assignee: X\n"
                "  > One sentence from the description (if available)\n"
                "  - SUBKEY: Subtask summary (Status)  ← indent subtasks\n\n"
                "Group tickets by status if there are more than 5. "
                "End with a one-line summary (e.g. '3 In Progress, 2 To Do, 1 Done').\n"
                "If Confluence docs are referenced, list them at the end.\n\n"
                f"{history_ctx}\n"
                f"JIRA DATA:\n{json.dumps(jira_data, indent=2)}"
                f"{conf_context}\n\n"
                f"QUESTION: {question}"
            )

        return {
            "prompt":              prompt,
            "sources":             [],
            "impact":              {},
            "question_type":       "jira",
            "jira_data":           jira_data,
            "confluence_data":     confluence_data,
            "detected_subroutine": name,
            "detected_ticket":     ticket_key or "",
        }

    def _prepare_history(self, question: str, subroutine_name: str = None, history: list = None) -> dict:
        """Handle GitHub history/change questions via live GitHub API."""
        if not github_configured():
            prompt = (
                "GitHub is not configured. The user is asking a history question "
                "but GITHUB_TOKEN and GITHUB_REPO are not set in .env.\n"
                f"Question: {question}"
            )
            return {"prompt": prompt, "sources": [], "impact": {}, "question_type": "history", "git_data": {}}

        q_lower = question.lower()
        name = subroutine_name or extract_name_from_question(question.upper(), self.known_subroutines)

        # ── Fuzzy match typos (e.g. "UPADTE.ORDER" → "UPDATE.ORDER") ──────────
        if name and self.known_subroutines and name not in self.known_subroutines:
            close = difflib.get_close_matches(name, self.known_subroutines, n=1, cutoff=0.7)
            if close:
                print(f"  Fuzzy matched '{name}' → '{close[0]}'")
                name = close[0]

        git_data = {}

        try:
            # Who changed / who last modified / who wrote
            if any(k in q_lower for k in [
                "who changed", "who modified", "who wrote", "who last",
                "last changed", "last modified", "last updated", "changed the",
            ]):
                git_data = get_file_last_changed(name) if name else {}

            # Full commit history for a file
            elif any(k in q_lower for k in ["history", "commit history", "change history", "how many times"]):
                git_data = {"commits": get_file_commits(name) if name else [], "file": name}

            # What changed recently across repo
            elif any(k in q_lower for k in ["recent changes", "recent commits", "what changed", "last week", "last sprint"]):
                git_data = {"recent_commits": get_recent_repo_commits(max_commits=20)}

            # Contributors / who works on codebase
            elif any(k in q_lower for k in ["contributor", "who works", "who developed"]):
                git_data = {"contributors": get_contributors()}

            # Changed by a specific person
            elif any(k in q_lower for k in ["changed by", "modified by", "commits by"]):
                git_data = {"commits": get_file_commits(name) if name else []}

            else:
                # General history — file commits if name known, else recent repo commits
                git_data = (
                    {"commits": get_file_commits(name), "file": name}
                    if name else
                    {"recent_commits": get_recent_repo_commits(max_commits=10)}
                )

        except Exception as e:
            git_data = {"error": str(e)}

        history_ctx = _build_history_ctx(history or [])
        prompt = (
            "You are an MVCore assistant. Answer using the GitHub data below.\n"
            "List each commit as: SHA — Author (Date): message\n"
            "Close with one sentence summarising the change pattern. Under 150 words.\n\n"
            f"{history_ctx}\n"
            f"GITHUB DATA:\n{json.dumps(git_data, indent=2)}\n\n"
            f"QUESTION: {question}"
        )

        return {
            "prompt":              prompt,
            "sources":             [],
            "impact":              {},
            "question_type":       "history",
            "git_data":            git_data,
            "detected_subroutine": name,
            "detected_ticket":     _extract_ticket_from_history(history or []),
        }

    def stream(self, prompt: str, use_code_llm: bool = False):
        """Stream LLM tokens one by one. Uses larger-context LLM for code suggestions."""
        llm = self.code_llm if use_code_llm else self.llm
        for chunk in llm.stream(prompt):
            yield chunk

    def analyse(self, question: str, subroutine_name: str = None) -> dict:
        """
        Convenience method for CLI/testing.
        """
        quick = get_quick_reply(question)
        if quick:
            return {
                "answer": quick,
                "sources": [],
                "impact": {},
                "question_type": "chat",
            }

        result = self.prepare(question, subroutine_name)

        # Handle not_found case without calling LLM
        if result["question_type"] == "not_found":
            return {
                "answer": (
                    f"⚠️ Subroutine not found in the codebase.\n\n"
                    f"**Available subroutines:**\n"
                    + "\n".join(f"- {s}" for s in self.known_subroutines)
                ),
                "sources": [],
                "impact": {},
                "question_type": "not_found",
            }

        full_response = "".join(self.stream(result["prompt"]))

        return {
            "answer": full_response,
            "sources": result["sources"],
            "impact": result["impact"],
            "question_type": result["question_type"],
        }