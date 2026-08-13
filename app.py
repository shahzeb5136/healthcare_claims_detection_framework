"""
ADNIC — Agentic Medical Claims Audit Platform
Demonstrator

A 28-agent fleet audits medical claims across coding integrity, clinical
appropriateness and policy adjudication, then consolidates the findings into one
reviewable decision. Every finding goes to a human before it has any effect.

Run with:
    streamlit run app.py

This is a demonstrator, not the production platform. See the Scope page for what
is built, what is deliberately not built, and why.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from adnic import theme
from adnic.catalogue import default_fleet
from adnic.demo_data import build_demo_claims
from adnic.llm import LLMConfig
from adnic.retrieval import PolicyCorpus

st.set_page_config(
    page_title="ADNIC · Agentic Claims Audit",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
)

theme.inject()

POLICY_PATH = Path(__file__).parent / "knowledge" / "ADNIC-COMP-GOLD-2026.md"


# --------------------------------------------------------------------------
# Session state
# --------------------------------------------------------------------------


@st.cache_resource(show_spinner=False)
def load_corpus(path: str) -> PolicyCorpus:
    return PolicyCorpus(path)


def init_state() -> None:
    ss = st.session_state
    if "fleet" not in ss:
        ss.fleet = default_fleet()
    if "claims" not in ss:
        ss.claims = build_demo_claims()
        ss.claims_source = "demo"
    if "results" not in ss:
        ss.results = {}
    if "run_stats" not in ss:
        ss.run_stats = None
    if "llm" not in ss:
        ss.llm = LLMConfig()
    if "conn_status" not in ss:
        ss.conn_status = None
    if "selected_claim" not in ss:
        ss.selected_claim = None
    if "nav" not in ss:
        ss.nav = "Scope and method"
    if "ingest_report" not in ss:
        ss.ingest_report = None


init_state()

try:
    CORPUS = load_corpus(str(POLICY_PATH))
    CORPUS_ERROR = ""
except Exception as exc:  # noqa: BLE001
    CORPUS = None
    CORPUS_ERROR = str(exc)

# Views reach for the corpus through session state rather than taking it as an
# argument everywhere; it is a cached resource, so this is a reference, not a copy.
st.session_state["_corpus"] = CORPUS


PAGES = [
    "Scope and method",
    "Claims",
    "Agent fleet",
    "Knowledge base",
    "Run audit",
    "Audit cockpit",
    "Claim review workbench",
    "Export",
]


def goto(page: str) -> None:
    """Navigate from anywhere in a page body.

    `nav` is the sidebar radio's widget key, and Streamlit forbids assigning to a
    widget's key once that widget has been instantiated in the current run — which
    the sidebar always has by the time a page body draws a button. So a navigation
    request is parked here and applied at the top of the next run, before the radio
    is created. That keeps `goto()` callable imperatively, including after a long
    operation such as an audit finishing.
    """
    st.session_state._nav_request = page
    st.rerun()


# Apply any parked navigation request. This must run BEFORE the sidebar radio.
_pending = st.session_state.pop("_nav_request", None)
if _pending in PAGES:
    st.session_state.nav = _pending


# --------------------------------------------------------------------------
# Sidebar
# --------------------------------------------------------------------------

with st.sidebar:
    st.markdown(
        '<div class="sidebar-brand">ADNIC'
        "<span>Agentic Claims Audit · Demonstrator</span></div>",
        unsafe_allow_html=True,
    )
    st.markdown("---")

    st.radio("Navigate", PAGES, key="nav", label_visibility="collapsed")

    st.markdown("---")
    st.markdown("**Model access**")

    from adnic.llm import (
        ANTHROPIC_MODELS,
        OPENAI_MODELS,
        PROVIDERS,
        REASONING_MODES,
        check_credentials,
    )

    cfg: LLMConfig = st.session_state.llm

    cfg.provider = st.selectbox(
        "Provider", PROVIDERS, index=PROVIDERS.index(cfg.provider)
        if cfg.provider in PROVIDERS else 0,
    )

    if cfg.provider == "Anthropic":
        ids = [m[0] for m in ANTHROPIC_MODELS]
        cfg.model = st.selectbox(
            "Model", ids, index=ids.index(cfg.model) if cfg.model in ids else 0,
            help="\n\n".join(f"**{m}** — {d}" for m, d in ANTHROPIC_MODELS),
        )
        cfg.api_key = st.text_input(
            "Anthropic API key", value=cfg.api_key, type="password",
            help="Held in memory for this browser session only. Never written to "
                 "disk, never logged, never placed in a URL.",
        )
    elif cfg.provider == "OpenAI":
        ids = [m[0] for m in OPENAI_MODELS]
        cfg.model = st.selectbox(
            "Model", ids, index=ids.index(cfg.model) if cfg.model in ids else 0,
        )
        cfg.api_key = st.text_input(
            "OpenAI API key", value=cfg.api_key, type="password",
            help="Held in memory for this browser session only.",
        )
    else:
        cfg.model = st.text_input("Ollama model", value=cfg.model or "llama3.1")
        cfg.base_url = st.text_input("Ollama host", value=cfg.base_url)
        st.caption("Fully local. Nothing leaves the machine.")

    cfg.reasoning = st.selectbox(
        "Reasoning", list(REASONING_MODES),
        index=list(REASONING_MODES).index(cfg.reasoning)
        if cfg.reasoning in REASONING_MODES else 0,
        help="\n\n".join(f"**{k}** — {v}" for k, v in REASONING_MODES.items()),
    )

    if st.button("Test connection", use_container_width=True):
        with st.spinner("Checking…"):
            st.session_state.conn_status = check_credentials(cfg)

    status = st.session_state.conn_status
    if status is not None:
        (st.success if status[0] else st.error)(status[1])

    st.markdown("---")
    st.caption(
        f"**{len(st.session_state.claims)}** claim(s) loaded · "
        f"**{len([a for a in st.session_state.fleet if a.enabled])}** agent(s) enabled"
    )
    st.caption("Synthetic data only. Decision-support, not a substitute for "
               "professional medical, coding or compliance review.")


# --------------------------------------------------------------------------
# Router
# --------------------------------------------------------------------------

if CORPUS is None:
    st.error(
        f"Could not load the policy corpus at {POLICY_PATH}. Squad E cannot run "
        f"without it.\n\n{CORPUS_ERROR}"
    )

page = st.session_state.nav

if page == "Scope and method":
    from adnic.views import overview
    overview.render(CORPUS, goto)
elif page == "Claims":
    from adnic.views import claims as claims_view
    claims_view.render(goto)
elif page == "Agent fleet":
    from adnic.views import fleet as fleet_view
    fleet_view.render()
elif page == "Knowledge base":
    from adnic.views import knowledge
    knowledge.render(CORPUS)
elif page == "Run audit":
    from adnic.views import run as run_view
    run_view.render(CORPUS, goto)
elif page == "Audit cockpit":
    from adnic.views import cockpit
    cockpit.render(goto)
elif page == "Claim review workbench":
    from adnic.views import workbench
    workbench.render(goto)
elif page == "Export":
    from adnic.views import export as export_view
    export_view.render()
