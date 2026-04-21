"""
analysis/query_engine.py
Core orchestration engine.
"""

import difflib
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor

from langchain_ollama import OllamaLLM as Ollama
from langchain_ollama import OllamaEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document
from graph.dependency_graph import get_impact, load_graph

from analysis.prompts import (
    SUBROUTINE_PROMPT,
    DICT_PROMPT,
    CODE_SUGGESTION_PROMPT,
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

    # Manager-style requests referencing sprint tasks
    "code for the sprint task", "code for the current task",
    "how do i implement the sprint", "code change for the task",
    "develop the sprint task", "implement the sprint task",
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
      1. Code suggestion keywords → 'code_suggestion'
      2. Jira ticket ID (PROJ-123) + suggestion → 'code_suggestion'
      3. Confluence keywords → 'confluence'
      4. Jira ticket ID only → 'jira'
      5. Jira keywords → 'jira'
      6. History keywords → 'history'
      7. Known subroutine name → 'subroutine'
      8. Dict keywords → 'dict'
      9. Default → 'subroutine'
    """
    q_lower = question.lower()

    # Priority 1: code suggestion / fix / implement request
    if any(kw in q_lower for kw in CODE_SUGGESTION_KEYWORDS):
        return "code_suggestion"

    # Priority 2: Jira ticket + no suggestion → pure Jira lookup
    if JIRA_TICKET_PATTERN.search(question):
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

    # Strategy 1: match against actual files on disk (most reliable)
    # Sort by length descending so GET.ORDER.DETAILS matches before ORDER
    for sub in sorted((known or get_known_subroutines()), key=len, reverse=True):
        if sub in q_upper:
            return sub

    # Strategy 2: MV dot-notation regex — handles 2-part and 3-part names
    # Matches: ORD.PROCESS, GET.ORDER.DETAILS, INV.UPDATE etc.
    dot_matches = re.findall(
        r'\b([A-Z][A-Z0-9]*(?:\.[A-Z0-9]+){1,})\b',
        q_upper
    )
    if dot_matches:
        # Return the longest match (most specific)
        return max(dot_matches, key=len)

    # Strategy 3: any uppercase word (min 3 chars), excluding stop words
    stop = {
        "THE", "AND", "FOR", "DICT", "FILE", "WHAT",
        "DOES", "EXPLAIN", "LAYOUT", "FIELDS", "STRUCTURE",
        "HOW", "WHY", "WHO", "WHEN", "ARE", "CAN", "YOU",
    }
    upper_words = re.findall(r'\b([A-Z]{3,})\b', q_upper)
    filtered = [w for w in upper_words if w not in stop]
    if filtered:
        return filtered[0]

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


def load_source_file(name: str) -> str:
    """
    Directly load a subroutine source file from SOURCE_FILE_PATH.
    Used as fallback when ChromaDB doesn't return the right chunks.
    """
    if not name:
        return ""

    name_upper = name.upper()

    if os.path.isdir(SOURCE_FILE_PATH):
        for fname in os.listdir(SOURCE_FILE_PATH):
            if fname.upper() == name_upper:
                fpath = os.path.join(SOURCE_FILE_PATH, fname)
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    return f.read()

    return ""


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
            num_predict=768,
            num_ctx=4096,
            num_thread=8,
        )
        # Larger context LLM for code suggestion — needs to read full source files
        print(f"  Loading code-suggestion LLM (8K ctx): {llm_model} ...")
        self.code_llm = Ollama(
            model=llm_model,
            temperature=0,
            num_predict=1024,
            num_ctx=8192,
            num_thread=8,
        )

        print(f"  Loading embeddings: {EMBED_MODEL} ...")
        self.embeddings = OllamaEmbeddings(model=EMBED_MODEL)

        print(f"  Loading ChromaDB from {chroma_path} ...")
        self.vectorstore = Chroma(
            persist_directory=chroma_path,
            embedding_function=self.embeddings,
        )
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

        If subroutine_name is given:
          1. Try exact file match from ChromaDB
          2. If no exact match found, load directly from SOURCE_FILE_PATH
          3. Combine with semantic results
        """
        relevant_docs = self.retriever.invoke(question)

        if subroutine_name and subroutine_name.strip():
            target = subroutine_name.strip().upper()

            # Split into exact match vs others
            matching = [
                d for d in relevant_docs
                if target in d.metadata.get("source", "").upper()
            ]
            others = [
                d for d in relevant_docs
                if target not in d.metadata.get("source", "").upper()
            ]

            # Direct similarity search scoped to subroutine name
            direct_docs = self.vectorstore.similarity_search(subroutine_name, k=5)
            direct_matching = [
                d for d in direct_docs
                if target in d.metadata.get("source", "").upper()
            ]

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

        return relevant_docs

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

        # ── 1. Full source code from disk ────────────────────────────────────
        source_code = load_source_file(name) if name else ""
        if not source_code:
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

                    # If no subroutine name yet, try to find one in the ticket text
                    if not name:
                        ticket_text = (
                            jira_data.get("summary", "") + " " +
                            jira_data.get("description", "")
                        )
                        name = extract_name_from_question(ticket_text.upper(), self.known_subroutines)
                        if name:
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
        # Two-pass search: first try source-type filtered, then unfiltered
        syntax_query = f"UniBasic MV BASIC {question} {name or ''}".strip()
        syntax_docs  = self.vectorstore.similarity_search(
            syntax_query, k=6,
            filter={"source_type": "mv_syntax"},
        )
        if not syntax_docs:
            # Fallback: search without filter — may return syntax PDFs anyway
            all_docs    = self.vectorstore.similarity_search(syntax_query, k=8)
            syntax_docs = [d for d in all_docs if d.metadata.get("source_type") == "mv_syntax"]
            if not syntax_docs:
                syntax_docs = all_docs[:4]   # last resort: best semantic match

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

                # Try each term until we get results
                found_pages = []
                seen_ids = set()
                for term in search_attempts:
                    if len(found_pages) >= 5:
                        break
                    results = search_pages(term, max_results=3)
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