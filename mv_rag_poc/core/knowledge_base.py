"""
core/knowledge_base.py
Engine loading (cached) and knowledge-base rebuild after a GitHub sync.
"""

import streamlit as st

from analysis.query_engine import MVAnalysisEngine, refresh_source_file_index
from graph.dependency_graph import build_graph, save_graph
from rag.ingest import ingest_corpus
from config import SOURCE_DIR, DOCS_DIR, CHROMA_PATH, GRAPH_PATH


@st.cache_resource(show_spinner="Loading AI engine…")
def load_engine() -> MVAnalysisEngine:
    """Load and cache the MVAnalysisEngine (embeddings + LLM + graph)."""
    return MVAnalysisEngine()


def rebuild_knowledge_base() -> None:
    """Rebuild the dependency graph and re-index changed source files.

    Called after a GitHub sync so the vector store and graph stay in sync
    with the latest code.
    """
    with st.spinner("Rebuilding graph…"):
        save_graph(build_graph(SOURCE_DIR), GRAPH_PATH)
    with st.spinner("Re-indexing changed files…"):
        ingest_corpus(SOURCE_DIR, DOCS_DIR, chroma_path=CHROMA_PATH, incremental=True)
    refresh_source_file_index()
    try:
        from connectors.github_connector import (
            get_file_commits, get_recent_repo_commits, get_contributors,
        )
        get_file_commits.cache_clear()
        get_recent_repo_commits.cache_clear()
        get_contributors.cache_clear()
    except Exception:
        pass
    st.cache_resource.clear()
