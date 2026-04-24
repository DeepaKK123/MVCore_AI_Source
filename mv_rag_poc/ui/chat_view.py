"""
ui/chat_view.py
All chat-area rendering:
  - render_data()          — expanders (Jira / Confluence / Git / sources)
  - render_welcome()       — empty-state suggestion cards
  - render_chat_history()  — replay stored messages
  - render_stream_handler()— live streaming response with blinking cursor
"""

import queue as _queue
import time

import streamlit as st

from ui.components import (
    QTYPE_LABEL,
    render_jira, render_confluence, render_git,
    render_impact, render_sources, render_message,
    render_code_suggestion_banner,
)


# ── Data expanders ────────────────────────────────────────────────────────────

def render_data(result: dict, q_type: str) -> None:
    """Render the appropriate expanders (Jira, Confluence, Git, sources) for a result."""
    confluence_data = result.get("confluence_data") or {}
    jira_data       = result.get("jira_data") or {}
    git_data        = result.get("git_data") or {}

    if q_type == "confluence":
        render_confluence(confluence_data)
    elif q_type == "jira":
        render_confluence(confluence_data)
        render_jira(jira_data)
    elif q_type == "history":
        render_git(git_data)
    elif q_type in ("subroutine", "dict"):
        render_impact(result.get("impact") or {})
        render_sources(result.get("sources") or [])
    elif q_type == "code_suggestion":
        render_confluence(confluence_data)
        render_jira(jira_data)
        render_sources(result.get("sources") or [])
    elif q_type == "unibasic_general":
        render_sources(result.get("sources") or [])


# ── Welcome screen ────────────────────────────────────────────────────────────

def render_welcome() -> None:
    """Render the empty-state welcome screen with quick-start suggestion cards."""
    st.markdown("""
<div class="mv-welcome">
  <div class="mv-welcome-icon">💎</div>
  <h2 class="mv-welcome-title">How can I help you today?</h2>
  <p class="mv-welcome-sub">
    Ask about your MultiValue codebase, Jira tickets,<br>GitHub history, or Confluence documentation.
  </p>
</div>
""", unsafe_allow_html=True)

    c1, c2 = st.columns(2, gap="medium")
    suggestions = [
        ("What's in the current sprint?",  "What's in the current sprint?"),
        ("What's in the upcoming sprint?", "What's in the upcoming sprint?"),
        ("Suggest code for a sprint task", "Suggest code change for the current sprint task"),
        ("What bugs are open?",            "What open bugs do we have?"),
        ("Impact analysis",                "If I change ORD.PROCESS what breaks?"),
        ("Explain a subroutine",           "What does ORD.PROCESS do?"),
    ]
    for i, (title, prompt) in enumerate(suggestions):
        col = c1 if i % 2 == 0 else c2
        with col:
            if st.button(title, key=f"sug_{i}", use_container_width=True):
                st.session_state["prefill_question"] = prompt
                st.rerun()


# ── Chat history ──────────────────────────────────────────────────────────────

def render_chat_history() -> None:
    """Replay all stored messages from session state into the chat area."""
    for msg in st.session_state["messages"]:
        with st.chat_message(msg["role"]):
            if msg["role"] == "assistant":
                render_message(msg)
            else:
                st.markdown(msg["content"])


# ── Live stream handler ───────────────────────────────────────────────────────

def render_stream_handler(llm_model: str) -> None:
    """Drain the chunk queue and render the in-progress streaming response.

    Reruns every 0.25 s while streaming is active so the UI updates smoothly.
    Finalises the message and clears streaming state when the stream ends.
    """
    if not st.session_state.sv_active:
        return

    result = st.session_state.sv_result
    q_type = result.get("question_type", "chat")
    label  = QTYPE_LABEL.get(q_type, q_type.title())
    t_prep = st.session_state.sv_t0

    with st.chat_message("assistant"):
        if q_type != "chat":
            st.caption(f"`{label}` · Retrieved in {t_prep:.1f}s · {llm_model}")
        if q_type == "code_suggestion":
            render_code_suggestion_banner()

        placeholder = st.empty()

        # Drain whatever chunks arrived since the last rerun
        q    = st.session_state.sv_queue
        done = False
        while True:
            try:
                chunk = q.get_nowait()
            except _queue.Empty:
                break
            if chunk is None:
                done = True
                break
            st.session_state.sv_buf += chunk

        stopped = st.session_state.sv_stop_ev.is_set()
        cursor  = "" if (done or stopped) else "▌"
        placeholder.markdown(st.session_state.sv_buf + cursor)

        if done or stopped:
            elapsed = (
                f"Retrieved {t_prep:.1f}s · "
                f"Generated {time.time() - st.session_state.sv_t1:.1f}s"
                + (" · stopped" if stopped else "")
            )
            render_data(result, q_type)
            st.session_state["messages"].append({
                "role":            "assistant",
                "content":         st.session_state.sv_buf,
                "question_type":   q_type,
                "impact":          result.get("impact", {}),
                "sources":         result.get("sources", []),
                "git_data":        result.get("git_data") or {},
                "jira_data":       result.get("jira_data") or {},
                "confluence_data": result.get("confluence_data") or {},
                "elapsed":         elapsed,
            })
            st.session_state.sv_active = False
            st.session_state.sv_buf    = ""
            st.session_state.sv_result = None
            st.rerun()
        else:
            time.sleep(0.25)
            st.rerun()
