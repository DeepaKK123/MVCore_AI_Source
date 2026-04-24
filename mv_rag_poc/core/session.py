"""
core/session.py
Centralises all Streamlit session-state keys so every engineer can see
the full state schema in one place.
"""

import streamlit as st

_DEFAULTS: list[tuple] = [
    ("messages",        []),
    ("last_subroutine", None),
    ("last_ticket_key", None),
    ("sv_active",       False),   # True while the LLM is streaming
    ("sv_buf",          ""),      # accumulated streamed text
    ("sv_queue",        None),    # Queue[str | None] fed by the background thread
    ("sv_stop_ev",      None),    # threading.Event — set to interrupt the stream
    ("sv_result",       None),    # dict returned by engine.prepare()
    ("sv_t0",           0.0),     # RAG retrieval duration (seconds)
    ("sv_t1",           0.0),     # timestamp when LLM streaming started
]


def init_session_state() -> None:
    """Initialise every session-state key with its default value if not yet set."""
    for key, default in _DEFAULTS:
        if key not in st.session_state:
            st.session_state[key] = default
