"""
app.py — MVCore main Streamlit entry point.
"""

import asyncio
import logging
import time
import threading
import queue as _queue
import streamlit as st
from pathlib import Path


# ── Silence benign Tornado websocket-closed noise ─────────────────────────────
# When a user closes the browser tab mid-stream, Streamlit's background write
# raises tornado.websocket.WebSocketClosedError / StreamClosedError. asyncio
# reports it as "Task exception was never retrieved" — harmless, but noisy.
# Install a custom asyncio exception handler and a logging filter to drop
# *only* these closed-connection errors; real errors still surface normally.
try:
    from tornado.websocket import WebSocketClosedError
    from tornado.iostream import StreamClosedError
except Exception:                          # tornado not importable? skip.
    WebSocketClosedError = ()              # type: ignore[assignment]
    StreamClosedError    = ()              # type: ignore[assignment]

_WS_CLOSED_EXC = tuple(
    t for t in (WebSocketClosedError, StreamClosedError)
    if isinstance(t, type)
)


def _silence_ws_closed(loop, context):
    exc = context.get("exception")
    if _WS_CLOSED_EXC and isinstance(exc, _WS_CLOSED_EXC):
        return
    loop.default_exception_handler(context)


def _install_ws_silencer():
    # Install on the current (and any future) asyncio loop we can reach.
    try:
        asyncio.get_event_loop().set_exception_handler(_silence_ws_closed)
    except RuntimeError:
        pass
    try:
        policy = asyncio.get_event_loop_policy()
        loop   = policy.get_event_loop()
        loop.set_exception_handler(_silence_ws_closed)
    except Exception:
        pass


_install_ws_silencer()


class _DropWsClosed(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        if "WebSocketClosedError" in msg or "Stream is closed" in msg:
            return False
        return True


for _name in ("tornado.application", "tornado.general", "asyncio"):
    logging.getLogger(_name).addFilter(_DropWsClosed())

from analysis.query_engine import MVAnalysisEngine, get_quick_reply, refresh_source_file_index
from graph.dependency_graph import load_graph, build_graph, save_graph
from rag.ingest import ingest_corpus
from config import (
    CHROMA_PATH, GRAPH_PATH, SOURCE_DIR, DOCS_DIR,
    LLM_MODEL, github_configured, jira_configured, confluence_configured,
)
from connectors.github_connector import sync_to_local, get_last_sync_info
from ui.styles import apply_styles
from ui.components import (
    QTYPE_LABEL,
    render_header,
    render_jira, render_confluence, render_git,
    render_impact, render_sources, render_message,
    render_code_suggestion_banner,
)

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="MVCore",
    page_icon="💎",
    layout="wide",
    initial_sidebar_state="expanded",
)

apply_styles()

# ── Pre-flight check ──────────────────────────────────────────────────────────
missing = []
if not Path(CHROMA_PATH).exists():
    missing.append("`chroma_db/`")
if not Path(GRAPH_PATH).exists():
    missing.append("`graph.json`")
if missing:
    st.error("Setup incomplete — missing: " + ", ".join(missing) + ". Run `python setup.py`")
    st.stop()

# ── Load engine ───────────────────────────────────────────────────────────────
@st.cache_resource(show_spinner="Loading AI engine…")
def load_engine():
    return MVAnalysisEngine()

engine = load_engine()


def rebuild_knowledge_base():
    with st.spinner("Rebuilding graph…"):
        save_graph(build_graph(SOURCE_DIR), GRAPH_PATH)
    with st.spinner("Re-indexing changed files…"):
        ingest_corpus(SOURCE_DIR, DOCS_DIR, chroma_path=CHROMA_PATH, incremental=True)
    refresh_source_file_index()
    # Drop cached GitHub commit data — source has changed
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


# ── Header ────────────────────────────────────────────────────────────────────
gh   = github_configured()
jira = jira_configured()
conf = confluence_configured()

# sb=0 → hidden; sb=1 or absent → visible
sb_param  = st.query_params.get("sb", "1")
sb_hidden = sb_param == "0"

render_header(gh, jira, conf, LLM_MODEL, sb_hidden=sb_hidden)

# Hide sidebar and reclaim its space when sb=0
if sb_hidden:
    st.markdown("""
<style>
section[data-testid="stSidebar"] { display: none !important; }
[data-testid="stMain"]           { margin-left: 0 !important; }
</style>""", unsafe_allow_html=True)

# ── Sidebar ───────────────────────────────────────────────────────────────────
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
    examples = [
        "What's in the current sprint?",
        "What's in the upcoming sprint?",
        "What's been completed this sprint?",
        "What tasks are blocked?",
        "What open bugs do we have?",
        "Give me a project status update",
    ]
    for ex in examples:
        if st.button(ex, use_container_width=True, key=ex):
            st.session_state["prefill_question"] = ex

    st.markdown("**Code & Analysis**")
    examples2 = [
        "Suggest code change for the current sprint task",
        "What does ORD.PROCESS do?",
        "If I change ORD.PROCESS what breaks?",
        "Who last changed UPDATE.ORDER?",
        "Find documentation about ORDER MAINTENANCE",
        "Show me the ORDERS dict file layout",
    ]
    for ex in examples2:
        if st.button(ex, use_container_width=True, key=ex):
            st.session_state["prefill_question"] = ex

    st.divider()
    st.markdown("**Knowledge base**")
    try:
        G = load_graph(GRAPH_PATH)
        c1, c2 = st.columns(2)
        c1.metric("Subroutines", G.number_of_nodes())
        c2.metric("Call links", G.number_of_edges())
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
                    rebuild_knowledge_base()
                    st.rerun()
            except Exception as e:
                st.error(str(e))

    st.divider()
    if st.button("🗑️ Clear chat", use_container_width=True):
        st.session_state["messages"] = []
        st.session_state["last_subroutine"] = None
        st.rerun()

# ── Session state ─────────────────────────────────────────────────────────────
for _k, _v in [
    ("messages",        []),
    ("last_subroutine", None),
    ("last_ticket_key", None),
    ("sv_active",       False),
    ("sv_buf",          ""),
    ("sv_queue",        None),
    ("sv_stop_ev",      None),
    ("sv_result",       None),
    ("sv_t0",           0.0),
    ("sv_t1",           0.0),
]:
    if _k not in st.session_state:
        st.session_state[_k] = _v


# ── Streaming worker (runs in background thread) ──────────────────────────────
def _stream_worker(engine, prompt, chunk_q, stop_ev, use_code_llm=False):
    try:
        for chunk in engine.stream(prompt, use_code_llm=use_code_llm):
            if stop_ev.is_set():
                break
            if chunk:
                chunk_q.put(chunk)
    finally:
        chunk_q.put(None)          # sentinel — signals completion


def _render_data(result, q_type):
    """Render Jira / Confluence / Git / source expanders based on question type."""
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


# ── Welcome screen — shown only when no messages yet ─────────────────────────
if not st.session_state["messages"] and not st.session_state.sv_active:
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
        ("What's in the current sprint?",       "What's in the current sprint?"),
        ("What's in the upcoming sprint?",      "What's in the upcoming sprint?"),
        ("Suggest code for a sprint task",      "Suggest code change for the current sprint task"),
        ("What bugs are open?",                 "What open bugs do we have?"),
        ("Impact analysis",                     "If I change ORD.PROCESS what breaks?"),
        ("Explain a subroutine",                "What does ORD.PROCESS do?"),
    ]
    for i, (title, prompt) in enumerate(suggestions):
        col = c1 if i % 2 == 0 else c2
        with col:
            if st.button(title, key=f"sug_{i}", use_container_width=True):
                st.session_state["prefill_question"] = prompt
                st.rerun()

# ── Chat history — always rendered so user messages stay visible ──────────────
for msg in st.session_state["messages"]:
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant":
            render_message(msg)
        else:
            st.markdown(msg["content"])

# ── Mid-stream handler — appended below history while streaming ───────────────
if st.session_state.sv_active:
    result  = st.session_state.sv_result
    q_type  = result.get("question_type", "chat")
    label   = QTYPE_LABEL.get(q_type, q_type.title())
    t_prep  = st.session_state.sv_t0

    with st.chat_message("assistant"):
        st.caption(f"`{label}` · Retrieved in {t_prep:.1f}s · {LLM_MODEL}")
        if q_type == "code_suggestion":
            render_code_suggestion_banner()

        placeholder = st.empty()

        # ── Drain the chunk queue ─────────────────────────────────────────────
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

        cursor = "" if (done or stopped) else "▌"
        placeholder.markdown(st.session_state.sv_buf + cursor)

        if done or stopped:
            elapsed = (
                f"Retrieved {t_prep:.1f}s · "
                f"Generated {time.time() - st.session_state.sv_t1:.1f}s"
                + (" · stopped" if stopped else "")
            )
            _render_data(result, q_type)

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

# ── Chat input ────────────────────────────────────────────────────────────────
prefill  = st.session_state.pop("prefill_question", None)
question = st.chat_input("Ask about your MV codebase, Jira, GitHub or Confluence…") or prefill

if question and not st.session_state.sv_active:
    with st.chat_message("user"):
        st.markdown(question)
    st.session_state["messages"].append({"role": "user", "content": question})

    quick = get_quick_reply(question)
    if quick:
        st.session_state["messages"].append({
            "role": "assistant", "content": quick, "question_type": "chat",
        })
        st.rerun()
    else:
        try:
            active_sub = subroutine.strip() if subroutine else st.session_state["last_subroutine"]

            t0 = time.time()
            with st.spinner("Analysing your question…"):
                result = engine.prepare(
                    question,
                    subroutine_name=active_sub,
                    history=st.session_state["messages"][-8:],
                    last_ticket_key=st.session_state.get("last_ticket_key"),
                )
            t_prep = time.time() - t0

            if result.get("detected_subroutine"):
                st.session_state["last_subroutine"] = result["detected_subroutine"]
            if result.get("detected_ticket"):
                st.session_state["last_ticket_key"] = result["detected_ticket"]

            stop_ev       = threading.Event()
            chunk_q       = _queue.Queue()
            use_code_llm  = result.get("question_type") in ("code_suggestion", "impact_analysis")
            threading.Thread(
                target=_stream_worker,
                args=(engine, result["prompt"], chunk_q, stop_ev, use_code_llm),
                daemon=True,
            ).start()

            st.session_state.sv_active  = True
            st.session_state.sv_buf     = ""
            st.session_state.sv_queue   = chunk_q
            st.session_state.sv_stop_ev = stop_ev
            st.session_state.sv_result  = result
            st.session_state.sv_t0      = t_prep
            st.session_state.sv_t1      = time.time()
            st.rerun()

        except Exception as e:
            err = f"⚠️ Error: {e}\n\nCheck Ollama is running (`ollama serve`)."
            st.error(err)
            st.session_state["messages"].append({"role": "assistant", "content": err})
            st.rerun()
