"""
ui/components.py
MVCore — reusable Streamlit render functions.
"""

import streamlit as st

# ── Question type labels + badge CSS classes ──────────────────────────────────
QTYPE_LABEL = {
    "subroutine":       "Code Analysis",
    "code_suggestion":  "Code Suggestion",
    "unibasic_general": "UniBasic",
    "jira":             "Jira",
    "confluence":       "Confluence",
    "history":          "Git History",
    "dict":             "Dict Layout",
    "chat":             "Chat",
    "not_found":        "Not Found",
}

_BADGE_CLASS = {
    "subroutine":       "badge-code",
    "code_suggestion":  "badge-suggest",
    "unibasic_general": "badge-code",
    "jira":             "badge-jira",
    "confluence":       "badge-conf",
    "history":          "badge-git",
    "dict":             "badge-dict",
    "chat":             "badge-chat",
    "not_found":        "badge-chat",
}


# ── Header ────────────────────────────────────────────────────────────────────

def _status(label: str, active: bool) -> str:
    dot   = "mv-dot-on" if active else "mv-dot-off"
    state = "mv-int-on" if active else "mv-int-off"
    return (
        f'<div class="mv-integration {state}">'
        f'<span class="mv-dot {dot}"></span>{label}'
        f'</div>'
    )


def render_header(gh: bool, jira: bool, conf: bool, llm_model: str = "", sb_hidden: bool = False):
    """Enterprise-grade topbar for client demo."""
    integrations = (
        _status("GitHub",     gh)
        + _status("Jira",       jira)
        + _status("Confluence", conf)
        + _status("RAG",        True)
        + _status("Graph",      True)
        + _status("Code Suggest",      True)
    )
    model_str  = llm_model or "Model"
    toggle_url = "?sb=0" if not sb_hidden else "?sb=1"
    st.markdown(f"""
<div class="mv-topbar">

  <!-- Left: hamburger + brand -->
  <div class="mv-topbar-left">
    <a href="{toggle_url}" class="mv-sb-toggle" title="Toggle sidebar">&#9776;</a>
    <div class="mv-brand">
      <div class="mv-brand-icon">&#x1F48E;</div>
      <div class="mv-brand-text">
        <span class="mv-brand-name">MVCore</span>
        <span class="mv-brand-tagline">AI Knowledge Assistant &nbsp;·&nbsp; MultiValue Teams</span>
      </div>
    </div>
    <div class="mv-topbar-sep"></div>
    <div class="mv-integrations">{integrations}</div>
  </div>

  <!-- Right: model + live badge -->
  <div class="mv-topbar-right">
    <div class="mv-model-pill">
      <span class="mv-model-label">MODEL</span>
      <span class="mv-model-name">{model_str}</span>
    </div>
    <div class="mv-live-badge">
      <span class="mv-live-dot"></span>LIVE
    </div>
  </div>

</div>
""", unsafe_allow_html=True)


def render_model_pill(llm_model: str):
    """No-op — model shown in render_header."""
    pass


# ── Response meta strip ───────────────────────────────────────────────────────
def _render_meta(q_type: str, elapsed: str = ""):
    label     = QTYPE_LABEL.get(q_type, q_type.title())
    badge_cls = _BADGE_CLASS.get(q_type, "badge-chat")
    timing    = (
        f'<span style="font-size:0.68rem;color:#9ca3af;margin-left:6px">{elapsed}</span>'
        if elapsed else ""
    )
    st.markdown(
        f'<div style="margin-bottom:10px;display:flex;align-items:center">'
        f'<span class="resp-badge {badge_cls}">{label}</span>{timing}'
        f'</div>',
        unsafe_allow_html=True,
    )


# ── Data expanders ────────────────────────────────────────────────────────────
def render_jira(data: dict):
    sprint_name = data.get("sprint_name", "")
    tickets = (
        data.get("tickets")               or
        data.get("related_tickets")       or
        data.get("recent_tickets")        or
        data.get("sprint_tickets")        or
        data.get("future_sprint_tickets") or
        data.get("backlog_tickets")       or
        data.get("open_bugs")             or
        ([data] if data.get("key") else [])
    )
    if not tickets:
        return
    label = f"🎫  {sprint_name} — {len(tickets)} ticket(s)" if sprint_name else f"🎫  Jira — {len(tickets)} ticket(s)"
    with st.expander(label):
        for t in tickets[:10]:
            key      = t.get("key", "—")
            url      = t.get("url", "")
            summ     = t.get("summary", "—")
            stat     = t.get("status", "")
            who      = t.get("assignee", "Unassigned")
            typ      = t.get("type", "")
            subtasks = t.get("subtasks", [])
            link     = f"[**{key}**]({url})" if url else f"**{key}**"
            st.markdown(
                f"{link} &nbsp; `{stat}` &nbsp; `{typ}`  \n"
                f"{summ}  \n"
                f"<span style='font-size:0.78rem;color:#64748b'>👤 {who}</span>",
                unsafe_allow_html=True,
            )
            if subtasks:
                st.markdown(
                    f"<span style='font-size:0.75rem;color:#64748b;font-weight:600'>"
                    f"↳ Subtasks ({len(subtasks)})</span>",
                    unsafe_allow_html=True,
                )
                for s in subtasks:
                    skey = s.get("key", "")
                    surl = s.get("url", "")
                    ssum = s.get("summary", "")
                    sstat = s.get("status", "")
                    slink = f"[{skey}]({surl})" if surl else skey
                    st.markdown(
                        f"<span style='font-size:0.78rem;color:#475569'>"
                        f"&nbsp;&nbsp;&nbsp;{slink} &nbsp;`{sstat}`&nbsp; {ssum}</span>",
                        unsafe_allow_html=True,
                    )
            st.divider()


def render_confluence(data: dict):
    pages = (
        data.get("related_pages")  or data.get("recent_pages") or
        data.get("search_results") or data.get("pages") or
        ([data] if data.get("title") else [])
    )
    if not pages:
        return
    with st.expander(f"📚  Confluence — {len(pages)} page(s)"):
        for p in pages[:10]:
            title   = p.get("title", "—")
            url     = p.get("url", "")
            updated = p.get("last_updated", "")
            by      = p.get("updated_by", "")
            snippet = p.get("content", "")[:200]
            link    = f"[**{title}**]({url})" if url else f"**{title}**"
            meta    = " · ".join(filter(None, [updated, f"by {by}" if by else ""]))
            st.markdown(link, unsafe_allow_html=True)
            if meta:
                st.caption(meta)
            if snippet:
                st.caption(snippet + "…")
            st.divider()


def render_git(data: dict):
    commits = (
        data.get("commits") or data.get("recent_commits") or
        ([data] if data.get("sha") or data.get("author") else [])
    )
    if not commits:
        return
    label = data.get("file", "repository")
    with st.expander(f"🐙  GitHub — {len(commits)} commit(s) · {label}"):
        for c in commits[:10]:
            sha  = (c.get("sha") or "")[:7]
            msg  = c.get("message") or c.get("commit_message", "—")
            auth = c.get("author", "—")
            date = (c.get("date") or c.get("committed_date", ""))[:10]
            url  = c.get("url", "")
            ref  = f"[`{sha}`]({url})" if url else f"`{sha}`"
            st.markdown(
                f"{ref} &nbsp; **{auth}** &nbsp; "
                f"<span style='color:#64748b;font-size:0.78rem'>{date}</span>  \n{msg}",
                unsafe_allow_html=True,
            )
            st.divider()


def render_impact(impact: dict):
    if not impact:
        return
    callers = impact.get("callers", [])
    callees = impact.get("callees", [])
    risks   = impact.get("risk_flags", [])
    with st.expander(f"📈  Dependency graph — {len(callers)} callers · {len(callees)} callees"):
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Called by**")
            for c in callers:
                st.code(c, language=None)
            if not callers:
                st.caption("No callers")
        with c2:
            st.markdown("**Calls into**")
            for c in callees:
                st.code(c, language=None)
            if not callees:
                st.caption("No callees")
        for r in risks:
            st.warning(r)


def render_sources(sources: list):
    unique = sorted(set(s for s in sources if s))
    if not unique:
        return
    with st.expander(f"📁  Source files — {len(unique)} referenced"):
        for s in unique:
            st.code(s, language=None)


def render_code_suggestion_banner():
    st.info(
        "**SUGGESTED CHANGES ONLY** — No files have been modified. "
        "Analyse the code, apply manually, then compile and test.",
        icon="💡",
    )


# ── Full message render ───────────────────────────────────────────────────────
def render_message(msg: dict):
    q_type  = msg.get("question_type", "chat")
    elapsed = msg.get("elapsed", "")
    _render_meta(q_type, elapsed)
    if q_type == "code_suggestion":
        render_code_suggestion_banner()
    st.markdown(msg["content"])
    if q_type == "confluence":
        render_confluence(msg.get("confluence_data") or {})
    elif q_type == "jira":
        render_confluence(msg.get("confluence_data") or {})
        render_jira(msg.get("jira_data") or {})
    elif q_type == "history":
        render_git(msg.get("git_data") or {})
    elif q_type in ("subroutine", "dict"):
        render_impact(msg.get("impact") or {})
        render_sources(msg.get("sources") or [])
    elif q_type == "code_suggestion":
        render_confluence(msg.get("confluence_data") or {})
        render_jira(msg.get("jira_data") or {})
        render_sources(msg.get("sources") or [])
