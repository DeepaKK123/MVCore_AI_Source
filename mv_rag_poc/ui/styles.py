"""
ui/styles.py — MVCore — Professional style AI chat UI.
"""

import streamlit as st

_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

*, *::before, *::after { box-sizing: border-box; }

html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    font-size: 15px;
}

/* ── HIDE STREAMLIT CHROME ── */
#MainMenu, footer              { visibility: hidden; }
[data-testid="stToolbar"]      { display: none !important; }
[data-testid="stDecoration"]   { display: none !important; }
header[data-testid="stHeader"] { display: none !important; }
/* Style but keep the native sidebar toggle */
[data-testid="collapsedControl"] {
    top: 8px !important;
    color: #6b7280 !important;
}

/* ── APP BACKGROUND ── */
.stApp { background: #ffffff !important; }

/* ── SIDEBAR — Claude-style ── */
section[data-testid="stSidebar"] {
    background: #f9f9f9 !important;
    border-right: 1px solid #e5e7eb !important;
}
section[data-testid="stSidebar"] > div:first-child {
    padding: 0.75rem 0.75rem 2rem !important;
}

/* ── SIDEBAR: hide Streamlit's own collapse arrow ── */
section[data-testid="stSidebar"] button[kind="header"] { display: none !important; }

/* Sidebar text defaults */
section[data-testid="stSidebar"] * { color: #374151 !important; }
section[data-testid="stSidebar"] h3 {
    font-size: 0.95rem !important;
    font-weight: 700 !important;
    color: #111827 !important;
    margin: 0 0 2px !important;
}

/* Sidebar section labels — like Claude's "Today", "Yesterday" */
section[data-testid="stSidebar"] p strong {
    color: #9ca3af !important;
    font-size: 0.67rem !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.08em !important;
}

/* Sidebar captions */
section[data-testid="stSidebar"] .stCaption,
section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {
    color: #9ca3af !important;
    font-size: 0.73rem !important;
}
section[data-testid="stSidebar"] label {
    color: #6b7280 !important;
    font-size: 0.73rem !important;
    font-weight: 500 !important;
}
section[data-testid="stSidebar"] hr {
    border: none !important;
    border-top: 1px solid #e9e9e9 !important;
    margin: 0.6rem 0 !important;
}

/* Sidebar text input */
section[data-testid="stSidebar"] .stTextInput input {
    background: #ffffff !important;
    border: 1px solid #e5e7eb !important;
    color: #111827 !important;
    border-radius: 8px !important;
    font-size: 0.82rem !important;
    padding: 7px 10px !important;
}
section[data-testid="stSidebar"] .stTextInput input:focus {
    border-color: #2563eb !important;
    box-shadow: 0 0 0 2px rgba(37,99,235,0.12) !important;
    outline: none !important;
}

/* Sidebar buttons — ghost style like Claude's conversation list */
section[data-testid="stSidebar"] .stButton button {
    width: 100% !important;
    border-radius: 8px !important;
    font-size: 0.78rem !important;
    text-align: left !important;
    border: none !important;
    color: #374151 !important;
    background: transparent !important;
    font-weight: 400 !important;
    padding: 7px 10px !important;
    transition: background 0.12s !important;
    line-height: 1.4 !important;
    white-space: normal !important;
    height: auto !important;
}
section[data-testid="stSidebar"] .stButton button:hover {
    background: #ececec !important;
    color: #111827 !important;
}

/* Sidebar metrics */
section[data-testid="stSidebar"] [data-testid="stMetric"] {
    background: #f0f0f0 !important;
    border: none !important;
    border-radius: 8px !important;
    padding: 8px 10px !important;
}
section[data-testid="stSidebar"] [data-testid="stMetricLabel"] p {
    color: #9ca3af !important;
    font-size: 0.65rem !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.06em !important;
}
section[data-testid="stSidebar"] [data-testid="stMetricValue"] {
    color: #1d4ed8 !important;
    font-weight: 700 !important;
    font-size: 1.25rem !important;
}

/* ══════════════════════════════════════════════════════════
   PROFESSIONAL TOPBAR — enterprise demo quality
   ══════════════════════════════════════════════════════════ */

.mv-topbar {
    position: fixed;
    top: 0; left: 0; right: 0;
    height: 50px;
    background: #0f172a;
    border-bottom: 1px solid rgba(255,255,255,0.07);
    box-shadow: 0 1px 0 rgba(0,0,0,0.5), 0 4px 20px rgba(0,0,0,0.3);
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 20px 0 12px;
    gap: 0;
    z-index: 9999;
    will-change: transform;
    transform: translateZ(0);
    backface-visibility: hidden;
}

/* ── LEFT SECTION ── */
.mv-topbar-left {
    display: flex;
    align-items: center;
    gap: 0;
    height: 100%;
    overflow: hidden;
}

/* Hamburger */
.mv-sb-toggle {
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
    width: 36px !important;
    height: 36px !important;
    background: transparent !important;
    color: rgba(255,255,255,0.5) !important;
    border: none !important;
    border-radius: 6px !important;
    font-size: 1rem !important;
    cursor: pointer !important;
    text-decoration: none !important;
    transition: color 0.15s, background 0.15s !important;
    flex-shrink: 0 !important;
    margin-right: 4px !important;
}
.mv-sb-toggle:hover {
    color: #ffffff !important;
    background: rgba(255,255,255,0.08) !important;
}

/* Brand block */
.mv-brand {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 0 16px 0 4px;
}
.mv-brand-icon {
    width: 30px;
    height: 30px;
    background: linear-gradient(135deg, #2563eb, #3b82f6);
    border-radius: 8px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.9rem;
    flex-shrink: 0;
    box-shadow: 0 0 0 1px rgba(59,130,246,0.5), 0 2px 8px rgba(37,99,235,0.4);
}
.mv-brand-text {
    display: flex;
    flex-direction: column;
    gap: 1px;
}
.mv-brand-name {
    font-size: 0.92rem;
    font-weight: 700;
    color: #ffffff;
    letter-spacing: -0.3px;
    line-height: 1;
}
.mv-brand-tagline {
    font-size: 0.62rem;
    color: rgba(255,255,255,0.38);
    font-weight: 400;
    letter-spacing: 0.01em;
    line-height: 1;
}

/* Vertical separator */
.mv-topbar-sep {
    width: 1px;
    height: 22px;
    background: rgba(255,255,255,0.1);
    margin: 0 16px;
    flex-shrink: 0;
}

/* Integration status pills */
.mv-integrations {
    display: flex;
    align-items: center;
    gap: 6px;
}
.mv-integration {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 3px 9px;
    border-radius: 20px;
    font-size: 0.62rem;
    font-weight: 500;
    letter-spacing: 0.02em;
    white-space: nowrap;
}
.mv-int-on {
    background: rgba(34,197,94,0.1);
    border: 1px solid rgba(34,197,94,0.25);
    color: rgba(255,255,255,0.75);
}
.mv-int-off {
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.08);
    color: rgba(255,255,255,0.25);
}
.mv-dot {
    width: 5px;
    height: 5px;
    border-radius: 50%;
    flex-shrink: 0;
}
.mv-dot-on  { background: #22c55e; box-shadow: 0 0 4px #22c55e; }
.mv-dot-off { background: rgba(255,255,255,0.2); }

/* ── RIGHT SECTION ── */
.mv-topbar-right {
    display: flex;
    align-items: center;
    gap: 10px;
    flex-shrink: 0;
}

/* Model pill */
.mv-model-pill {
    display: flex;
    align-items: center;
    gap: 6px;
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 6px;
    padding: 4px 10px;
}
.mv-model-label {
    font-size: 0.55rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    color: rgba(255,255,255,0.3);
    text-transform: uppercase;
}
.mv-model-name {
    font-size: 0.68rem;
    font-weight: 600;
    color: rgba(255,255,255,0.8);
    letter-spacing: 0.01em;
}

/* LIVE badge with pulse */
.mv-live-badge {
    display: flex;
    align-items: center;
    gap: 5px;
    background: rgba(34,197,94,0.1);
    border: 1px solid rgba(34,197,94,0.3);
    border-radius: 20px;
    padding: 3px 10px;
    font-size: 0.6rem;
    font-weight: 700;
    color: #4ade80;
    letter-spacing: 0.08em;
}
.mv-live-dot {
    width: 6px;
    height: 6px;
    background: #22c55e;
    border-radius: 50%;
    box-shadow: 0 0 6px #22c55e;
    animation: mv-pulse 2s ease-in-out infinite;
}
@keyframes mv-pulse {
    0%, 100% { opacity: 1; transform: scale(1); }
    50%       { opacity: 0.5; transform: scale(0.85); }
}

/* ── PERSISTENT TOPBAR SHIELD ──────────────────────────────────────────────────
   body::before is pure CSS — it never re-renders during st.rerun().
   It permanently covers the top 50px with the same gradient as .mv-topbar,
   so even when the st.markdown topbar HTML flickers between reruns,
   the background colour stays solid and content never bleeds through.
   ──────────────────────────────────────────────────────────────────────────── */
body::before {
    content: '' !important;
    position: fixed !important;
    top: 0 !important;
    left: 0 !important;
    right: 0 !important;
    height: 50px !important;
    background: #0f172a !important;
    z-index: 9998 !important;   /* one below .mv-topbar (9999) — always visible */
    pointer-events: none !important;
}

/* ── SCROLL CONTAINMENT ── */
html, body {
    overflow: hidden !important;
    height: 100vh !important;
    margin: 0 !important;
}
.stApp {
    height: 100vh !important;
    overflow: hidden !important;
}

/* Scroll area starts exactly at the bottom edge of the 50px topbar */
section[data-testid="stMain"],
section.main {
    position: fixed !important;
    top: 50px !important;
    bottom: 0 !important;
    left: 0 !important;
    right: 0 !important;
    height: auto !important;
    overflow-y: auto !important;
    overflow-x: hidden !important;
    background: #ffffff !important;
    scroll-behavior: smooth !important;
}
section.main > div { overflow: visible !important; }

.block-container {
    padding-top: 1.5rem !important;
    padding-bottom: 11rem !important;
    padding-left: 2.5rem !important;
    padding-right: 2.5rem !important;
    max-width: 880px !important;
    margin-left: auto !important;
    margin-right: auto !important;
}

/* ── CHAT MESSAGES — GPT/Claude style ── */
[data-testid="stChatMessage"] {
    background: transparent !important;
    border: none !important;
    border-radius: 0 !important;
    padding: 18px 0 !important;
    margin-bottom: 0 !important;
    box-shadow: none !important;
    border-bottom: 1px solid #f3f4f6 !important;
}
[data-testid="stChatMessage"]:last-of-type {
    border-bottom: none !important;
}

/* User message row — light gray background strip */
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
    background: #f7f7f8 !important;
    padding: 18px 24px !important;
    border-radius: 12px !important;
    border-bottom: none !important;
    margin-bottom: 6px !important;
}

/* Assistant message row */
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) {
    padding: 18px 4px !important;
    margin-bottom: 6px !important;
}

/* Avatar */
[data-testid="stChatMessageAvatarUser"],
[data-testid="stChatMessageAvatarAssistant"] {
    width: 30px !important;
    height: 30px !important;
    min-width: 30px !important;
    border-radius: 6px !important;
}

/* Message text */
[data-testid="stChatMessage"] p {
    color: #1a1a1a !important;
    line-height: 1.7 !important;
    font-size: 0.9rem !important;
    margin-bottom: 0.6em !important;
}
[data-testid="stChatMessage"] p:last-child { margin-bottom: 0 !important; }

/* Headings inside messages */
[data-testid="stChatMessage"] h1,
[data-testid="stChatMessage"] h2,
[data-testid="stChatMessage"] h3 {
    color: #111827 !important;
    font-weight: 600 !important;
    margin: 1em 0 0.4em !important;
}
[data-testid="stChatMessage"] h2 { font-size: 1rem !important; }
[data-testid="stChatMessage"] h3 { font-size: 0.9rem !important; }

/* Lists */
[data-testid="stChatMessage"] ul,
[data-testid="stChatMessage"] ol {
    padding-left: 1.4em !important;
    color: #1a1a1a !important;
    font-size: 0.9rem !important;
    line-height: 1.7 !important;
}

/* ── RESPONSE META STRIP ── */
.resp-badge {
    display: inline-block;
    padding: 1px 7px;
    border-radius: 4px;
    font-size: 0.58rem;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    margin-right: 6px;
}
.badge-code    { background: #eff6ff; color: #1d4ed8; }
.badge-suggest { background: #fff7ed; color: #c2410c; }
.badge-jira    { background: #eff6ff; color: #1e40af; }
.badge-conf    { background: #f0f9ff; color: #0369a1; }
.badge-git     { background: #f0fdf4; color: #15803d; }
.badge-dict    { background: #faf5ff; color: #7c3aed; }
.badge-chat    { background: #f3f4f6; color: #6b7280; }

/* ── EXPANDERS ── */
details[data-testid="stExpander"] {
    border-radius: 8px !important;
    margin: 6px 0 !important;
    border: 1px solid #e5e7eb !important;
    background: #fafafa !important;
    box-shadow: none !important;
}
details[data-testid="stExpander"] summary {
    font-size: 0.8rem;
    font-weight: 600;
    color: #374151;
    padding: 9px 14px;
    background: #f9fafb;
    border-radius: 8px;
    cursor: pointer;
}
details[data-testid="stExpander"][open] summary {
    border-bottom: 1px solid #e5e7eb;
    border-radius: 8px 8px 0 0;
}

/* ── CHAT INPUT — fixed at bottom with generous gradient fade ── */
[data-testid="stBottom"] {
    position: fixed !important;
    bottom: 0 !important;
    left: 0 !important;
    right: 0 !important;
    /* tall gradient so spinner/last message fades in clearly above input */
    background: linear-gradient(
        to top,
        #ffffff 0%,
        #ffffff 65%,
        rgba(255,255,255,0.92) 80%,
        rgba(255,255,255,0) 100%
    ) !important;
    padding: 28px 0 24px !important;   /* extra top padding = clear gap above input box */
    z-index: 998 !important;
}
[data-testid="stChatInput"] {
    max-width: 880px !important;
    margin: 0 auto !important;
    padding: 0 2.5rem !important;
}
[data-testid="stChatInput"] > div {
    border: 1px solid #d1d5db !important;
    border-radius: 14px !important;
    background: #ffffff !important;
    box-shadow: 0 2px 12px rgba(0,0,0,0.08) !important;
    transition: border-color 0.15s, box-shadow 0.15s !important;
}
[data-testid="stChatInput"] > div:focus-within {
    border-color: #2563eb !important;
    box-shadow: 0 0 0 3px rgba(37,99,235,0.1), 0 2px 12px rgba(0,0,0,0.08) !important;
}
[data-testid="stChatInput"] textarea {
    border: none !important;
    background: transparent !important;
    font-size: 0.92rem !important;
    color: #111827 !important;
    padding: 13px 16px !important;
    line-height: 1.55 !important;
    resize: none !important;
    box-shadow: none !important;
    outline: none !important;
}
[data-testid="stChatInput"] textarea:focus {
    outline: none !important;
    box-shadow: none !important;
    border: none !important;
}
[data-testid="stChatInput"] textarea::placeholder {
    color: #9ca3af !important;
    font-size: 0.88rem !important;
}

/* ── DIVIDERS ── */
hr { border: none !important; border-top: 1px solid #f3f4f6 !important; }

/* ── CODE BLOCKS ── */
code {
    background: #f3f4f6 !important;
    border-radius: 4px !important;
    padding: 1px 5px !important;
    font-size: 0.82em !important;
    color: #2563eb !important;
}
pre {
    background: #1e1e2e !important;
    border-radius: 10px !important;
    padding: 14px 18px !important;
    overflow-x: auto !important;
    margin: 10px 0 !important;
}
pre code {
    background: transparent !important;
    padding: 0 !important;
    color: #cdd6f4 !important;
    font-size: 0.85rem !important;
}

/* ── WELCOME / EMPTY STATE ── */
.mv-welcome {
    text-align: center;
    padding: 3.5rem 1rem 2.5rem;
}
.mv-welcome-icon {
    width: 58px;
    height: 58px;
    background: linear-gradient(135deg, #1d4ed8, #3b82f6);
    border-radius: 16px;
    display: flex;
    align-items: center;
    justify-content: center;
    margin: 0 auto 1.4rem;
    font-size: 1.6rem;
    box-shadow: 0 6px 20px rgba(29,78,216,0.28);
}
.mv-welcome-title {
    font-size: 1.65rem !important;
    font-weight: 700 !important;
    color: #0f172a !important;
    margin: 0 0 0.65rem !important;
    letter-spacing: -0.5px !important;
    line-height: 1.2 !important;
}
.mv-welcome-sub {
    color: #64748b !important;
    font-size: 0.9rem !important;
    line-height: 1.6 !important;
    margin: 0 0 2.5rem !important;
    max-width: 480px;
    margin-left: auto !important;
    margin-right: auto !important;
}

/* ── SUGGESTION CARDS (welcome screen) ── */
[data-testid="stMain"] .stButton button {
    background: #ffffff !important;
    border: 1.5px solid #e2e8f0 !important;
    border-radius: 12px !important;
    color: #1e293b !important;
    font-size: 0.84rem !important;
    font-weight: 500 !important;
    padding: 14px 18px !important;
    text-align: left !important;
    transition: all 0.15s ease !important;
    height: auto !important;
    min-height: 54px !important;
    line-height: 1.45 !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.05) !important;
}
[data-testid="stMain"] .stButton button:hover {
    background: #eff6ff !important;
    border-color: #93c5fd !important;
    color: #1d4ed8 !important;
    box-shadow: 0 2px 8px rgba(29,78,216,0.12) !important;
    transform: translateY(-1px) !important;
}

/* ── SUGGESTION CARD ACCENT COLOURS (left border per category) ──
   Column 1: cards 1,2,3  |  Column 2: cards 1,2,3
   Order matches app.py: Explain / Impact / Git / Jira / Docs / Dict  ── */

/* Column 1 */
[data-testid="stHorizontalBlock"] [data-testid="stColumn"]:nth-child(1) .stButton:nth-child(1) button {
    border-left: 4px solid #2563eb !important;  /* blue  — Explain a subroutine */
}
[data-testid="stHorizontalBlock"] [data-testid="stColumn"]:nth-child(1) .stButton:nth-child(2) button {
    border-left: 4px solid #16a34a !important;  /* green — Git history */
}
[data-testid="stHorizontalBlock"] [data-testid="stColumn"]:nth-child(1) .stButton:nth-child(3) button {
    border-left: 4px solid #0891b2 !important;  /* teal  — Search documentation */
}

/* Column 2 */
[data-testid="stHorizontalBlock"] [data-testid="stColumn"]:nth-child(2) .stButton:nth-child(1) button {
    border-left: 4px solid #ea580c !important;  /* orange  — Impact analysis */
}
[data-testid="stHorizontalBlock"] [data-testid="stColumn"]:nth-child(2) .stButton:nth-child(2) button {
    border-left: 4px solid #7c3aed !important;  /* purple  — Open Jira tickets */
}
[data-testid="stHorizontalBlock"] [data-testid="stColumn"]:nth-child(2) .stButton:nth-child(3) button {
    border-left: 4px solid #d97706 !important;  /* amber   — Dict file layout */
}

/* ── SPINNER — clear space above input ── */
[data-testid="stSpinner"] {
    margin-bottom: 1.5rem !important;
    padding: 0.5rem 0 !important;
}
[data-testid="stSpinner"] > div {
    display: flex !important;
    align-items: center !important;
    gap: 10px !important;
    font-size: 0.85rem !important;
    color: #6b7280 !important;
}

/* ── SIDEBAR HIDDEN ── */
section[data-testid="stSidebar"].mv-hidden { display: none !important; }
</style>
"""


def apply_styles():
    st.markdown(_CSS, unsafe_allow_html=True)
