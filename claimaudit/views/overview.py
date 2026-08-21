"""Overview — what the platform is, and how a claim moves through it."""

from __future__ import annotations

import streamlit as st

from .. import branding, theme
from ..catalogue import SQUADS


def render(corpus, goto) -> None:
    fleet = st.session_state.fleet
    claims = st.session_state.claims

    theme.page_header(
        branding.eyebrow(),
        "A fleet of specialist agents, and a human who decides",
        "The platform decomposes the medical audit function into twenty-eight specialist "
        "agents across four squads — coding integrity, clinical appropriateness, policy "
        "adjudication, and the synthesis that turns their findings into one reviewable "
        "decision. Nothing here reaches a payment decision without a person.",
    )

    theme.tiles(
        [
            ("Agents in the fleet", str(len(fleet)), "one question each"),
            ("Squads", "4", "B, C, E and H"),
            ("Deterministic checks", "13", "Tier 0, no model calls"),
            ("Policy clauses indexed", str(len(corpus.chunks)) if corpus else "0",
             "retrievable by Squad E"),
            ("Sample claims", str(len(claims)), "synthetic, one clean control"),
        ]
    )

    st.markdown("## How a claim moves through the platform")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        theme.card(
            "1 · Tier 0 — deterministic",
            "Thirteen arithmetic, sequencing, format and duplicate checks run on every "
            "claim in ordinary Python. No key, no cost, no model. <em>Deterministic "
            "before probabilistic</em> is a design principle, not an optimisation: a "
            "language model should not be asked to do arithmetic it will do worse.",
        )
    with c2:
        theme.card(
            "2 · Risk gate",
            "Deterministic hits, claim value, setting, authorisation state and place of "
            "treatment combine into a risk score. Full agentic review is expensive; the "
            "gate decides which claims earn it — and a sampling quota pulls low-risk "
            "claims through anyway, so the blind spots are measured rather than assumed.",
        )
    with c3:
        theme.card(
            "3 · The audit squads",
            "Squads B, C and E run concurrently — one call per agent per claim, each "
            "answering one narrow question and returning the same JSON contract. Narrow "
            "scope is what makes an answer verifiable in an auditor's minute.",
        )
    with c4:
        theme.card(
            "4 · Synthesis, then a human",
            "Squad H deduplicates, surfaces disagreement rather than hiding it, "
            "recommends a disposition with the arithmetic shown, and drafts the "
            "provider letter. The auditor accepts, amends or rejects every finding. "
            "Nothing has effect until they do.",
        )

    st.markdown("## The four squads")

    for code in ("B", "C", "E", "H"):
        meta = SQUADS[code]
        agents = [a for a in fleet if a.squad == code]
        knowledge = {
            "model_memory": "Model memory — citations shown as UNVERIFIED",
            "rag_policy": "In-app RAG over the policy corpus — citations grounded",
            "upstream": "Consumes the audit squads' findings",
        }[meta["knowledge"]]
        colour = theme.SQUAD_COLOUR[code]

        st.markdown(
            f'<div class="ca-panel">'
            f'<div class="ca-panel-head" style="border-left:4px solid {colour}">'
            f"Squad {code} — {theme.esc(meta['name'])} · {len(agents)} agents</div>"
            f'<div class="ca-panel-body">'
            f'<p style="margin:0 0 .55rem 0;color:{theme.INK_SOFT};font-size:.89rem;">'
            f"{theme.esc(meta['blurb'])} &nbsp;·&nbsp; "
            f"<strong>Knowledge:</strong> {theme.esc(knowledge)} &nbsp;·&nbsp; "
            f"<strong>Primary consumer:</strong> {theme.esc(meta['consumer'])}</p>"
            + '<div style="display:flex;flex-wrap:wrap;gap:.4rem">'
            + "".join(
                f'<div style="display:inline-flex;align-items:center;gap:.35rem;'
                f"border:1px solid {theme.LINE};border-radius:6px;"
                f'padding:.22rem .5rem;background:#FAFBFC">'
                f"{theme.squad_tag(code, a.agent_id)}"
                f'<span style="font-size:.82rem;color:{theme.INK}">{theme.esc(a.name)}</span>'
                f"</div>"
                for a in agents
            )
            + "</div></div></div>",
            unsafe_allow_html=True,
        )

    st.markdown("## The two knowledge modes, side by side")
    k1, k2 = st.columns(2)
    with k1:
        st.markdown(
            f'<div class="ca-card" style="border-top:3px solid #B4530A">'
            f"<h4>Squads B and C — model memory</h4>"
            f"<p>The ICD-10, CPT and HCPCS code sets are licensed products, so these agents "
            f"reason from the model's own knowledge of coding and clinical practice. "
            f"Anything they cite "
            f"is shown to the auditor marked "
            f'<span class="pill" style="color:#B4530A;background:#FDF0E4">unverified</span>, '
            f"so it is always visible which assertions rest on a retrieved rule and which "
            f"rest on the model's own knowledge. Point these agents at a licensed corpus and "
            f"the same contract carries grounded citations instead.</p></div>",
            unsafe_allow_html=True,
        )
    with k2:
        st.markdown(
            f'<div class="ca-card" style="border-top:3px solid {theme.ACCENT}">'
            f"<h4>Squad E — grounded retrieval</h4>"
            f"<p>One full policy wording is loaded, chunked on clause boundaries and indexed "
            f"with BM25 in-process. No external vector database. Each agent retrieves the "
            f"clauses relevant to its question, must cite the clause locator, and the "
            f"application resolves that locator back to the real passage — so a citation the "
            f"auditor sees is the clause text itself, "
            f'<span class="pill" style="color:{theme.ACCENT};background:#E6F2F2">grounded</span>, '
            f"not the model's paraphrase of it.</p></div>",
            unsafe_allow_html=True,
        )

    st.markdown("## Start here")
    b1, b2, b3 = st.columns(3)
    with b1:
        if st.button("Review the claims", use_container_width=True):
            goto("Claims")
    with b2:
        if st.button("Inspect the agent fleet", use_container_width=True):
            goto("Agent fleet")
    with b3:
        if st.button("Run an audit", type="primary", use_container_width=True):
            goto("Run audit")

    st.markdown("---")
    st.caption(
        "The bundled claims, members, providers and policy wording are synthetic. "
        "Bring your own API key; keys are held in memory for the browser session only. "
        "Decision-support and screening — not a substitute for professional medical, coding "
        "or compliance review."
    )
