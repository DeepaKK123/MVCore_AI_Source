"""
core/streaming.py
Background thread workers and session-state helpers for LLM token streaming.

Two streaming modes:
  - LLM stream  : tokens arrive from Ollama via engine.stream()
  - Quick stream : a canned reply is word-by-word delayed to feel natural
"""

import queue as _queue
import threading
import time

import streamlit as st


# ── Background thread workers ─────────────────────────────────────────────────

def stream_worker(engine, prompt: str, chunk_q: _queue.Queue,
                  stop_ev: threading.Event, use_code_llm: bool = False) -> None:
    """Feed LLM token chunks into chunk_q.  Puts None as a completion sentinel."""
    try:
        for chunk in engine.stream(prompt, use_code_llm=use_code_llm):
            if stop_ev.is_set():
                break
            if chunk:
                chunk_q.put(chunk)
    finally:
        chunk_q.put(None)


def quick_stream_worker(reply: str, chunk_q: _queue.Queue,
                        stop_ev: threading.Event) -> None:
    """Emit a quick reply word-by-word with a short leading pause for natural feel."""
    time.sleep(0.5)
    for word in reply.split(" "):
        if stop_ev.is_set():
            break
        chunk_q.put(word + " ")
        time.sleep(0.03)
    chunk_q.put(None)


# ── Session-state helpers ─────────────────────────────────────────────────────

def start_llm_stream(engine, result: dict, t_prep: float) -> None:
    """Start a background LLM thread and initialise all sv_* session-state keys."""
    stop_ev      = threading.Event()
    chunk_q: _queue.Queue = _queue.Queue()
    use_code_llm = result.get("question_type") in ("code_suggestion", "impact_analysis")

    threading.Thread(
        target=stream_worker,
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


def start_quick_stream(reply: str) -> None:
    """Start a word-by-word quick-reply thread and initialise all sv_* keys."""
    stop_ev = threading.Event()
    chunk_q: _queue.Queue = _queue.Queue()

    threading.Thread(
        target=quick_stream_worker,
        args=(reply, chunk_q, stop_ev),
        daemon=True,
    ).start()

    st.session_state.sv_active  = True
    st.session_state.sv_buf     = ""
    st.session_state.sv_queue   = chunk_q
    st.session_state.sv_stop_ev = stop_ev
    st.session_state.sv_result  = {
        "question_type": "chat",
        "sources": [], "impact": {},
        "jira_data": {}, "confluence_data": {}, "git_data": {},
    }
    st.session_state.sv_t0 = 0.0
    st.session_state.sv_t1 = time.time()
