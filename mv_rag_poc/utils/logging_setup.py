"""
utils/logging_setup.py
Suppresses harmless Tornado websocket-closed noise that Streamlit emits
when a browser tab is closed mid-stream.  Call install_silence() once at
startup before any other imports.
"""

import asyncio
import logging

try:
    from tornado.websocket import WebSocketClosedError
    from tornado.iostream import StreamClosedError
except Exception:
    WebSocketClosedError = ()   # type: ignore[assignment]
    StreamClosedError    = ()   # type: ignore[assignment]

_WS_CLOSED_EXC = tuple(
    t for t in (WebSocketClosedError, StreamClosedError)
    if isinstance(t, type)
)


def _silence_ws_closed(loop, context):
    exc = context.get("exception")
    if _WS_CLOSED_EXC and isinstance(exc, _WS_CLOSED_EXC):
        return
    loop.default_exception_handler(context)


class _DropWsClosed(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        if "WebSocketClosedError" in msg or "Stream is closed" in msg:
            return False
        return True


def install_silence():
    """Install asyncio exception handler + logging filter to drop websocket-closed noise."""
    try:
        asyncio.get_event_loop().set_exception_handler(_silence_ws_closed)
    except RuntimeError:
        pass
    try:
        loop = asyncio.get_event_loop_policy().get_event_loop()
        loop.set_exception_handler(_silence_ws_closed)
    except Exception:
        pass
    for name in ("tornado.application", "tornado.general", "asyncio"):
        logging.getLogger(name).addFilter(_DropWsClosed())
