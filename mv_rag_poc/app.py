"""
app.py — MVCore entry point.

Thin orchestrator: page config, pre-flight check, and wiring.
All logic lives in core/ and ui/ — nothing substantial should be added here.

  core/knowledge_base.py  — engine loading + KB rebuild
  core/session.py         — session-state schema + initialisation
  core/streaming.py       — background thread workers + stream helpers
  core/chat_handler.py    — question routing (quick reply vs LLM)
  ui/sidebar.py           — left sidebar rendering
  ui/chat_view.py         — welcome screen, history, live stream handler
  ui/components.py        — reusable render functions (Jira, Git, sources…)
  ui/styles.py            — global CSS
  utils/logging_setup.py  — silences harmless Tornado websocket noise
"""

import streamlit as st
from pathlib import Path

# Must run before Streamlit renders anything
from utils.logging_setup import install_silence
install_silence()

from config import (
    CHROMA_PATH, GRAPH_PATH, LLM_MODEL,
    github_configured, jira_configured, confluence_configured,
)
from ui.styles import apply_styles
from ui.components import render_header
from ui.sidebar import render_sidebar
from ui.chat_view import render_welcome, render_chat_history, render_stream_handler
from core.session import init_session_state
from core.knowledge_base import load_engine, rebuild_knowledge_base
from core.chat_handler import handle_question

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
if not Path(CHROMA_PATH).exists(): missing.append("`chroma_db/`")
if not Path(GRAPH_PATH).exists():  missing.append("`graph.json`")
if missing:
    st.error("Setup incomplete — missing: " + ", ".join(missing) + ". Run `python setup.py`")
    st.stop()

# ── Engine ────────────────────────────────────────────────────────────────────
engine = load_engine()

# ── Header ────────────────────────────────────────────────────────────────────
gh        = github_configured()
jira      = jira_configured()
conf      = confluence_configured()
sb_hidden = st.query_params.get("sb", "1") == "0"

render_header(gh, jira, conf, LLM_MODEL, sb_hidden=sb_hidden)

if sb_hidden:
    st.markdown("""
<style>
section[data-testid="stSidebar"] { display: none !important; }
[data-testid="stMain"]           { margin-left: 0 !important; }
</style>""", unsafe_allow_html=True)

# ── Sidebar ───────────────────────────────────────────────────────────────────
subroutine = render_sidebar(gh, rebuild_knowledge_base)

# ── Session state ─────────────────────────────────────────────────────────────
init_session_state()

# ── Chat area ─────────────────────────────────────────────────────────────────
if not st.session_state["messages"] and not st.session_state.sv_active:
    render_welcome()

render_chat_history()
render_stream_handler(LLM_MODEL)

# ── Chat input ────────────────────────────────────────────────────────────────
prefill  = st.session_state.pop("prefill_question", None)
question = st.chat_input("Ask about your MV codebase, Jira, GitHub or Confluence…") or prefill

if question and not st.session_state.sv_active:
    handle_question(question, engine, subroutine)
