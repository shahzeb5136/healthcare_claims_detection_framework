"""
Visual system for the workbench.

One accent, a restrained navy/slate palette, and severity as the only place
colour is allowed to shout. The measure of this surface is how long a competent
auditor takes to reach a confident decision on a claim with six findings — so
density, alignment and typographic hierarchy matter more than decoration.
"""

from __future__ import annotations

import html

import streamlit as st

INK = "#0F2C4C"
INK_SOFT = "#3A5772"
MUTED = "#6B7C8F"
LINE = "#E3E8ED"
SURFACE = "#FFFFFF"
CANVAS = "#F5F7F9"
ACCENT = "#0E7C7B"

SEVERITY_COLOUR = {
    "critical": ("#B3261E", "#FDECEA"),
    "major": ("#B4530A", "#FDF0E4"),
    "moderate": ("#8A6A00", "#FBF4DE"),
    "minor": ("#54687C", "#EEF1F4"),
}

RESULT_COLOUR = {
    "finding": ("#B3261E", "#FDECEA"),
    "no_finding": ("#16704A", "#E7F3ED"),
    "insufficient_evidence": ("#8A6A00", "#FBF4DE"),
    "not_applicable": ("#6B7C8F", "#F0F2F5"),
    "error": ("#54687C", "#EEF1F4"),
}

SQUAD_COLOUR = {
    "T0": "#54687C",
    "B": "#0E5FA8",
    "C": "#0E7C7B",
    "E": "#7A4CA0",
    "H": "#B4530A",
}

DECISION_COLOUR = {
    "pending": ("#6B7C8F", "#F0F2F5"),
    "accepted": ("#16704A", "#E7F3ED"),
    "amended": ("#8A6A00", "#FBF4DE"),
    "rejected": ("#54687C", "#EEF1F4"),
    "escalated": ("#7A4CA0", "#F2EBF8"),
}


CSS = f"""
<style>
  html, body, [class*="css"] {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Roboto,
                   "Helvetica Neue", Arial, sans-serif;
      -webkit-font-smoothing: antialiased;
  }}

  .stApp {{ background: {CANVAS}; }}
  .block-container {{ padding-top: 1.9rem; padding-bottom: 4rem; max-width: 1500px; }}

  h1, h2, h3, h4 {{ color: {INK}; letter-spacing: -0.011em; }}
  h1 {{ font-size: 1.72rem; font-weight: 660; }}
  h2 {{ font-size: 1.22rem; font-weight: 640; margin-top: 1.4rem; }}
  h3 {{ font-size: 1.02rem; font-weight: 620; }}

  /* ---------- page header ---------- */
  .adnic-eyebrow {{
      font-size: .70rem; font-weight: 680; letter-spacing: .12em;
      text-transform: uppercase; color: {ACCENT}; margin-bottom: .3rem;
  }}
  .adnic-title {{
      font-size: 1.66rem; font-weight: 660; color: {INK};
      letter-spacing: -0.015em; line-height: 1.2; margin: 0;
  }}
  .adnic-sub {{
      color: {MUTED}; font-size: .93rem; margin-top: .42rem;
      max-width: 76ch; line-height: 1.55;
  }}
  .adnic-rule {{
      height: 3px; width: 54px; background: {ACCENT};
      border-radius: 2px; margin: .95rem 0 1.15rem 0;
  }}

  /* ---------- cards ---------- */
  .adnic-card {{
      background: {SURFACE}; border: 1px solid {LINE}; border-radius: 10px;
      padding: 1.05rem 1.2rem; margin-bottom: .85rem;
      box-shadow: 0 1px 2px rgba(15,44,76,.04);
  }}
  .adnic-card h4 {{ margin: 0 0 .45rem 0; font-size: .96rem; }}
  .adnic-card p {{ margin: 0; color: {INK_SOFT}; font-size: .89rem; line-height: 1.6; }}

  .adnic-panel {{
      background: {SURFACE}; border: 1px solid {LINE}; border-radius: 10px;
      padding: 0; margin-bottom: .9rem; overflow: hidden;
  }}
  .adnic-panel-head {{
      background: #FAFBFC; border-bottom: 1px solid {LINE};
      padding: .62rem .95rem; font-size: .72rem; font-weight: 680;
      letter-spacing: .09em; text-transform: uppercase; color: {INK_SOFT};
  }}
  .adnic-panel-body {{ padding: .9rem 1.05rem; }}

  /* ---------- metric tiles ---------- */
  .adnic-tiles {{ display: flex; gap: .7rem; flex-wrap: wrap; margin-bottom: 1rem; }}
  .adnic-tile {{
      flex: 1 1 150px; background: {SURFACE}; border: 1px solid {LINE};
      border-radius: 10px; padding: .8rem .95rem; min-width: 138px;
      border-top: 3px solid {ACCENT};
  }}
  .adnic-tile .lbl {{
      font-size: .68rem; font-weight: 660; letter-spacing: .085em;
      text-transform: uppercase; color: {MUTED};
  }}
  .adnic-tile .val {{
      font-size: 1.5rem; font-weight: 660; color: {INK};
      line-height: 1.15; margin-top: .28rem; font-variant-numeric: tabular-nums;
  }}
  .adnic-tile .hint {{ font-size: .755rem; color: {MUTED}; margin-top: .22rem; }}

  /* ---------- pills ---------- */
  .pill {{
      display: inline-block; padding: .14rem .52rem; border-radius: 999px;
      font-size: .695rem; font-weight: 660; letter-spacing: .045em;
      text-transform: uppercase; white-space: nowrap; line-height: 1.5;
  }}
  .pill + .pill {{ margin-left: .3rem; }}
  .tag {{
      display: inline-block; padding: .1rem .44rem; border-radius: 4px;
      font-size: .70rem; font-weight: 620; background: #EEF1F4; color: {INK_SOFT};
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  }}

  /* ---------- finding row ---------- */
  .finding {{
      background: {SURFACE}; border: 1px solid {LINE}; border-left: 4px solid {MUTED};
      border-radius: 8px; padding: .78rem .95rem; margin-bottom: .55rem;
  }}
  .finding .head {{
      display: flex; align-items: center; gap: .45rem; flex-wrap: wrap;
      margin-bottom: .38rem;
  }}
  .finding .who {{ font-size: .76rem; color: {MUTED}; font-weight: 600; }}
  .finding .stmt {{
      font-size: .90rem; color: {INK}; font-weight: 560; line-height: 1.5;
  }}
  .finding .rat {{
      font-size: .845rem; color: {INK_SOFT}; line-height: 1.62; margin-top: .4rem;
  }}

  /* ---------- citations ---------- */
  .cite {{
      border-left: 3px solid {ACCENT}; background: #F4F9F9;
      padding: .55rem .75rem; border-radius: 0 6px 6px 0;
      margin-top: .45rem; font-size: .82rem; color: {INK_SOFT}; line-height: 1.6;
  }}
  .cite.unverified {{ border-left-color: #B4530A; background: #FDF6EE; }}
  .cite .src {{
      font-size: .70rem; font-weight: 680; letter-spacing: .06em;
      text-transform: uppercase; color: {ACCENT}; display: block; margin-bottom: .22rem;
  }}
  .cite.unverified .src {{ color: #B4530A; }}
  .cite .txt {{ font-style: italic; }}

  /* ---------- claim context ---------- */
  .kv {{ display: flex; gap: .55rem; padding: .2rem 0; font-size: .84rem; }}
  .kv .k {{ color: {MUTED}; min-width: 132px; flex-shrink: 0; }}
  .kv .v {{ color: {INK}; font-weight: 540; }}

  .lines table {{ width: 100%; border-collapse: collapse; font-size: .82rem; }}
  .lines th {{
      text-align: left; color: {MUTED}; font-weight: 640; font-size: .70rem;
      letter-spacing: .07em; text-transform: uppercase; padding: .35rem .5rem;
      border-bottom: 1px solid {LINE};
  }}
  .lines td {{
      padding: .4rem .5rem; border-bottom: 1px solid #F0F3F6; color: {INK};
      vertical-align: top;
  }}
  .lines td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .lines tr:last-child td {{ border-bottom: none; }}
  .mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }}

  /* ---------- notice ---------- */
  .notice {{
      border: 1px solid #E6D9BE; background: #FDFAF2; border-radius: 8px;
      padding: .7rem .9rem; font-size: .85rem; color: #6B5A2E; line-height: 1.6;
      margin-bottom: .9rem;
  }}
  .notice strong {{ color: #4E4120; }}
  .notice.info {{ border-color: #CFE0EC; background: #F4F9FC; color: #2C4C63; }}
  .notice.info strong {{ color: {INK}; }}

  /* ---------- streamlit chrome ---------- */
  section[data-testid="stSidebar"] {{
      background: {INK}; border-right: none;
  }}
  section[data-testid="stSidebar"] * {{ color: #E3EAF1; }}
  section[data-testid="stSidebar"] h1,
  section[data-testid="stSidebar"] h2,
  section[data-testid="stSidebar"] h3 {{ color: #FFFFFF; }}
  section[data-testid="stSidebar"] .stRadio label p {{ font-size: .90rem; }}
  section[data-testid="stSidebar"] hr {{ border-color: rgba(255,255,255,.14); }}
  section[data-testid="stSidebar"] input,
  section[data-testid="stSidebar"] textarea,
  section[data-testid="stSidebar"] div[data-baseweb="select"] > div {{
      background: rgba(255,255,255,.08) !important;
      border-color: rgba(255,255,255,.18) !important;
      color: #FFFFFF !important;
  }}
  .sidebar-brand {{
      font-size: 1.05rem; font-weight: 680; color: #FFFFFF; letter-spacing: -.01em;
      line-height: 1.25;
  }}
  .sidebar-brand span {{
      display: block; font-size: .68rem; font-weight: 600; letter-spacing: .11em;
      text-transform: uppercase; color: {ACCENT}; margin-top: .2rem;
  }}

  .stButton > button {{
      border-radius: 7px; font-weight: 600; font-size: .875rem;
      border: 1px solid {LINE}; padding: .34rem .85rem;
  }}
  .stButton > button[kind="primary"] {{
      background: {INK}; border-color: {INK};
  }}
  .stButton > button[kind="primary"]:hover {{ background: #16406C; border-color: #16406C; }}
  .stDownloadButton > button {{ border-radius: 7px; font-weight: 600; font-size: .875rem; }}

  .stTabs [data-baseweb="tab-list"] {{ gap: .1rem; border-bottom: 1px solid {LINE}; }}
  .stTabs [data-baseweb="tab"] {{
      height: 38px; padding: 0 .95rem; font-size: .875rem; font-weight: 600;
      color: {MUTED};
  }}
  .stTabs [aria-selected="true"] {{ color: {INK}; }}

  div[data-testid="stExpander"] {{
      border: 1px solid {LINE}; border-radius: 9px; background: {SURFACE};
  }}
  div[data-testid="stExpander"] summary {{ font-size: .875rem; font-weight: 600; }}

  div[data-testid="stMetricValue"] {{ font-size: 1.35rem; color: {INK}; }}
  div[data-testid="stMetricLabel"] {{ font-size: .78rem; color: {MUTED}; }}

  hr {{ margin: 1.2rem 0; border-color: {LINE}; }}
  code {{ font-size: .84em; background: #EEF1F4; color: {INK}; padding: .08em .32em;
          border-radius: 3px; }}

  .stProgress > div > div > div > div {{ background-color: {ACCENT}; }}
  #MainMenu, footer {{ visibility: hidden; }}
</style>
"""


def inject() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


# --------------------------------------------------------------------------
# Components
# --------------------------------------------------------------------------


def esc(text) -> str:
    return html.escape(str(text or ""))


def page_header(eyebrow: str, title: str, subtitle: str = "") -> None:
    sub = f'<div class="adnic-sub">{esc(subtitle)}</div>' if subtitle else ""
    st.markdown(
        f'<div class="adnic-eyebrow">{esc(eyebrow)}</div>'
        f'<div class="adnic-title">{esc(title)}</div>'
        f"{sub}"
        f'<div class="adnic-rule"></div>',
        unsafe_allow_html=True,
    )


def tiles(items: list[tuple[str, str, str]], accent: str = ACCENT) -> None:
    """items: (label, value, hint)"""
    cells = "".join(
        f'<div class="adnic-tile" style="border-top-color:{accent}">'
        f'<div class="lbl">{esc(lbl)}</div>'
        f'<div class="val">{esc(val)}</div>'
        f'<div class="hint">{esc(hint)}</div></div>'
        for lbl, val, hint in items
    )
    st.markdown(f'<div class="adnic-tiles">{cells}</div>', unsafe_allow_html=True)


def pill(text: str, fg: str, bg: str) -> str:
    return f'<span class="pill" style="color:{fg};background:{bg}">{esc(text)}</span>'


def severity_pill(sev: str) -> str:
    fg, bg = SEVERITY_COLOUR.get(sev, SEVERITY_COLOUR["minor"])
    return pill(sev, fg, bg)


def result_pill(result: str) -> str:
    fg, bg = RESULT_COLOUR.get(result, RESULT_COLOUR["error"])
    return pill(result.replace("_", " "), fg, bg)


def decision_pill(decision: str) -> str:
    fg, bg = DECISION_COLOUR.get(decision, DECISION_COLOUR["pending"])
    return pill(decision, fg, bg)


def squad_tag(squad: str, agent_id: str) -> str:
    colour = SQUAD_COLOUR.get(squad, MUTED)
    return (
        f'<span class="tag" style="background:{colour}14;color:{colour}">'
        f"{esc(agent_id)}</span>"
    )


def notice(text: str, kind: str = "warn") -> None:
    cls = "notice info" if kind == "info" else "notice"
    st.markdown(f'<div class="{cls}">{text}</div>', unsafe_allow_html=True)


def card(title: str, body: str) -> None:
    st.markdown(
        f'<div class="adnic-card"><h4>{esc(title)}</h4><p>{body}</p></div>',
        unsafe_allow_html=True,
    )


def panel_open(title: str) -> None:
    st.markdown(
        f'<div class="adnic-panel"><div class="adnic-panel-head">{esc(title)}</div>'
        f'<div class="adnic-panel-body">',
        unsafe_allow_html=True,
    )


def panel_close() -> None:
    st.markdown("</div></div>", unsafe_allow_html=True)


def kv_rows(pairs: list[tuple[str, str]]) -> str:
    return "".join(
        f'<div class="kv"><div class="k">{esc(k)}</div>'
        f'<div class="v">{esc(v)}</div></div>'
        for k, v in pairs
    )


def money(v: float) -> str:
    return f"AED {v:,.2f}"


def money_short(v: float) -> str:
    if abs(v) >= 1_000_000:
        return f"AED {v/1_000_000:.2f}M"
    if abs(v) >= 1_000:
        return f"AED {v/1_000:,.1f}k"
    return f"AED {v:,.0f}"
