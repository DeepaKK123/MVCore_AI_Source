"""
ui/sidebar.py
Renders the full left sidebar: subroutine focus input, example prompts,
knowledge-base metrics, GitHub sync, and chat controls.
"""

from typing import Callable

import streamlit as st

from config import GRAPH_PATH, SOURCE_DIR
from connectors.github_connector import sync_to_local, get_last_sync_info
from graph.dependency_graph import load_graph


def render_sidebar(gh: bool, rebuild_fn: Callable) -> str:
    """Render the sidebar and return the subroutine focus text entered by the user.

    Args:
        gh:         True if GitHub is configured in .env.
        rebuild_fn: Callable that rebuilds the graph + vector index (post-sync).

    Returns:
        The subroutine name typed into the Focus subroutine input (may be empty).
    """
    with st.sidebar:
        st.markdown("### 💎 MVCore")
        st.caption("AI Knowledge Assistant for MultiValue Teams")
        st.divider()

        subroutine = st.text_input(
            "Focus subroutine",
            placeholder="e.g. ORD.PROCESS",
            help="Pin a subroutine for follow-up questions.",
        )

        st.divider()
        st.markdown("**Sprint & Planning**")
        for ex in [
            "What's in the current sprint?",
            "What's in the upcoming sprint?",
            "What's been completed this sprint?",
            "What tasks are blocked?",
            "What open bugs do we have?",
            "Give me a project status update",
        ]:
            if st.button(ex, use_container_width=True, key=ex):
                st.session_state["prefill_question"] = ex

        st.markdown("**Code & Analysis**")
        for ex in [
            "Suggest code change for the current sprint task",
            "What does ORD.PROCESS do?",
            "If I change ORD.PROCESS what breaks?",
            "Who last changed UPDATE.ORDER?",
            "Find documentation about ORDER MAINTENANCE",
            "Show me the ORDERS dict file layout",
        ]:
            if st.button(ex, use_container_width=True, key=ex):
                st.session_state["prefill_question"] = ex

        st.divider()
        st.markdown("**Knowledge base**")
        try:
            G = load_graph(GRAPH_PATH)
            c1, c2 = st.columns(2)
            c1.metric("Subroutines", G.number_of_nodes())
            c2.metric("Call links",  G.number_of_edges())
        except Exception:
            st.caption("Graph not loaded")

        st.divider()
        st.markdown("**GitHub Sync**")
        if not gh:
            st.caption("Add `GITHUB_TOKEN` and `GITHUB_REPO` to `.env`")
        else:
            info = get_last_sync_info()
            st.caption(f"Last sync: {info['last_sync']}")
            st.caption(f"{info['files_synced']} synced · {info['files_total']} total")
            if st.button("🔄 Sync now", use_container_width=True):
                try:
                    with st.spinner("Syncing…"):
                        result = sync_to_local(SOURCE_DIR)
                    synced = len(result["synced"])
                    st.success(f"{synced} file(s) updated")
                    if synced > 0:
                        rebuild_fn()
                        st.rerun()
                except Exception as e:
                    st.error(str(e))

        st.divider()
        if st.button("🗑️ Clear chat", use_container_width=True):
            st.session_state["messages"]        = []
            st.session_state["last_subroutine"] = None
            st.rerun()

    return subroutine
