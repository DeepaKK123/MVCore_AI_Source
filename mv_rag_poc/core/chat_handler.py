"""
core/chat_handler.py
Handles a single user question: routes to quick reply or LLM, then starts
the appropriate streaming session.
"""

import time

import streamlit as st

from analysis.query_engine import get_quick_reply
from core.streaming import start_llm_stream, start_quick_stream


def handle_question(question: str, engine, subroutine: str) -> None:
    """Process one user question and start a streaming response.

    Steps:
      1. Display and record the user message.
      2. Check for a quick reply (greetings, small talk).
      3. If not a quick reply: run RAG retrieval via engine.prepare(),
         then start an LLM streaming session.
    """
    with st.chat_message("user"):
        st.markdown(question)
    st.session_state["messages"].append({"role": "user", "content": question})

    quick = get_quick_reply(question)
    if quick:
        start_quick_stream(quick)
        st.rerun()
        return

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

        start_llm_stream(engine, result, t_prep)
        st.rerun()

    except Exception as e:
        err = f"⚠️ Error: {e}\n\nCheck Ollama is running (`ollama serve`)."
        st.error(err)
        st.session_state["messages"].append({"role": "assistant", "content": err})
        st.rerun()
