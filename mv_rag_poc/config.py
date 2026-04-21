"""
config.py
Centralised configuration — loads all settings from .env

Create a .env file based on .env.example before running the app.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── GitHub ─────────────────────────────────────────────────────────────────────
GITHUB_TOKEN     = os.getenv("GITHUB_TOKEN", "")
GITHUB_REPO      = os.getenv("GITHUB_REPO", "")        # e.g. "owner/repo-name"
GITHUB_BRANCH    = os.getenv("GITHUB_BRANCH", "main")
GITHUB_MV_FOLDER = os.getenv("GITHUB_MV_FOLDER", "mv_source")

# ── LLM & Embeddings ──────────────────────────────────────────────────────────
LLM_MODEL   = os.getenv("LLM_MODEL",   "qwen2.5-coder:32b")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")

# ── Local paths ────────────────────────────────────────────────────────────────
SOURCE_DIR  = os.getenv("SOURCE_DIR",  "./mv_source")
DOCS_DIR    = os.getenv("DOCS_DIR",    "./documents")
CHROMA_PATH = os.getenv("CHROMA_PATH", "./chroma_db")
GRAPH_PATH  = os.getenv("GRAPH_PATH",  "./graph.json")

DICT_FILE_PATH   = os.path.join(DOCS_DIR.lstrip("./"), "dict_file_layout")
MV_SYNTAX_DIR    = os.path.join(DOCS_DIR.lstrip("./"), "mv_syntax")

# ── Confluence ─────────────────────────────────────────────────────────────────
# Reuses Jira URL, email and token — only space key is new
CONFLUENCE_SPACE = os.getenv("CONFLUENCE_SPACE", "")   # e.g. "TECH" or "PROJ"

# ── Jira ───────────────────────────────────────────────────────────────────────
JIRA_URL     = os.getenv("JIRA_URL", "")        # e.g. https://your-org.atlassian.net
JIRA_EMAIL   = os.getenv("JIRA_EMAIL", "")
JIRA_TOKEN   = os.getenv("JIRA_TOKEN", "")      # Atlassian API token
JIRA_PROJECT = os.getenv("JIRA_PROJECT", "")    # e.g. "PROJ"

# ── Sync metadata ──────────────────────────────────────────────────────────────
SYNC_META_PATH = ".sync_meta.json"


def github_configured() -> bool:
    """Return True if GitHub credentials are set in .env."""
    return bool(GITHUB_TOKEN and GITHUB_REPO)


def jira_configured() -> bool:
    """Return True if Jira credentials are set in .env."""
    return bool(JIRA_URL and JIRA_EMAIL and JIRA_TOKEN)


def confluence_configured() -> bool:
    """Return True if Confluence credentials are set in .env."""
    return bool(JIRA_URL and JIRA_EMAIL and JIRA_TOKEN)
