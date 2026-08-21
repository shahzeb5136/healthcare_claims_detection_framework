"""Agent fleet — the catalogue, and a cut-down Agent Studio."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from .. import theme
from ..catalogue import SQUADS, default_fleet
from ..orchestrator import build_audit_prompt, build_synthesis_prompt
from ..schema import SEVERITIES

_MODE_LABEL = {
    "model_memory": "Model memory · unverified citations",
    "rag_policy": "In-app RAG · grounded citations",
    "upstream": "Consumes upstream findings",
}


def render() -> None:
    theme.page_header(
        "Agent fleet",
        "One agent, one question",
        "An agent that must weigh coding, necessity and pricing at once produces reasoning "
        "that is harder to verify and harder to improve. Narrow scope is what makes the "
        "output auditable — and what lets each agent be evaluated, versioned and rolled back "
        "on its own.",
    )

    fleet = st.session_state.fleet
    enabled = [a for a in fleet if a.enabled]

    theme.tiles(
        [
            ("Agents in fleet", str(len(fleet)), "across four squads"),
            ("Enabled", str(len(enabled)), "will run on the next audit"),
            ("Grounded agents", str(len([a for a in fleet if a.knowledge_mode == 'rag_policy'])),
             "Squad E, retrieval-backed"),
            ("Calls per claim", str(len(enabled)),
             "one per agent, run concurrently"),
        ]
    )

    tab_cat, tab_studio, tab_prompt = st.tabs(
        ["Catalogue", "Agent Studio", "Prompt inspector"]
    )

    with tab_cat:
        _catalogue(fleet)
    with tab_studio:
        _studio(fleet)
    with tab_prompt:
        _prompt_inspector(fleet)


# --------------------------------------------------------------------------


def _catalogue(fleet) -> None:
    df = pd.DataFrame(
        [
            {
                "": "on" if a.enabled else "off",
                "ID": a.agent_id,
                "Agent": a.name,
                "Squad": f"{a.squad} — {a.squad_name}",
                "Question it answers": a.scope,
                "Knowledge": _MODE_LABEL[a.knowledge_mode],
                "Max severity": a.max_severity,
                "PACS domain": a.pacs_domain.replace("_", " "),
                "Tier": a.tier,
                "Version": a.version,
            }
            for a in fleet
        ]
    )
    squads = ["All"] + [f"{k} — {v['name']}" for k, v in SQUADS.items()]
    pick = st.selectbox("Filter by squad", squads, key="fleet_filter")
    view = df if pick == "All" else df[df["Squad"] == pick]

    st.dataframe(view, use_container_width=True, hide_index=True, height=560)

    st.caption(
        "Severity is a ceiling, not a verdict: the severity of any individual finding is "
        "decided at run time from the evidence and the monetary exposure, then clamped to "
        "the agent's maximum. Tier is the execution tier from the triage model — Tier 0 is "
        "deterministic, Tier 3 is deep investigation."
    )


# --------------------------------------------------------------------------


def _studio(fleet) -> None:
    st.markdown("### Author, scope and version")
    theme.notice(
        "Edits take effect on the next audit run and are held for this browser session. The "
        "fleet defaults are never overwritten, so <strong>Reset fleet to default</strong> "
        "always returns every agent to a known state. Version any agent you change — the "
        "version string travels with each finding it raises, so any line in the findings "
        "register can be traced back to the exact instruction that produced it.",
        kind="info",
    )

    # Bulk actions run as callbacks and must clear or set the per-agent widget
    # keys as well as the objects, or the stored widget values revert the change
    # on the next run.
    def _set_enabled(agent_ids: list[str], value: bool) -> None:
        for a in fleet:
            if a.agent_id in agent_ids:
                a.enabled = value
                st.session_state[f"en_{a.agent_id}"] = value

    def _reset_fleet() -> None:
        for key in [
            k
            for k in st.session_state
            if k.split("_", 1)[0] in ("en", "sev", "scope", "inst", "hint")
        ]:
            del st.session_state[key]
        st.session_state.fleet = default_fleet()

    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        squad_codes = list(SQUADS)
        chosen_squads = st.multiselect(
            "Squads", squad_codes, default=squad_codes,
            format_func=lambda k: f"{k} — {SQUADS[k]['name']}",
        )
    with c2:
        st.button("Enable all", use_container_width=True,
                  on_click=_set_enabled, args=([a.agent_id for a in fleet], True))
    with c3:
        st.button("Reset fleet to default", use_container_width=True,
                  on_click=_reset_fleet)

    for code in chosen_squads:
        meta = SQUADS[code]
        agents = [a for a in fleet if a.squad == code]
        colour = theme.SQUAD_COLOUR[code]

        st.markdown(
            f'<div style="margin:1.1rem 0 .5rem 0;padding-left:.7rem;'
            f'border-left:4px solid {colour}">'
            f'<div style="font-size:1.02rem;font-weight:640;color:{theme.INK}">'
            f"Squad {code} — {theme.esc(meta['name'])}</div>"
            f'<div style="font-size:.83rem;color:{theme.MUTED}">'
            f"{theme.esc(meta['blurb'])}</div></div>",
            unsafe_allow_html=True,
        )

        # Bulk toggle for the squad
        sc1, sc2 = st.columns([1, 6])
        with sc1:
            all_on = all(a.enabled for a in agents)
            st.button(
                "Disable squad" if all_on else "Enable squad",
                key=f"squad_toggle_{code}",
                use_container_width=True,
                on_click=_set_enabled,
                args=([a.agent_id for a in agents], not all_on),
            )

        for agent in agents:
            with st.expander(
                f"{agent.agent_id} · {agent.name}"
                + ("" if agent.enabled else "   (disabled)"),
                expanded=False,
            ):
                r1, r2, r3 = st.columns([1, 1, 2])
                with r1:
                    agent.enabled = st.checkbox(
                        "Enabled", value=agent.enabled, key=f"en_{agent.agent_id}"
                    )
                with r2:
                    agent.max_severity = st.selectbox(
                        "Severity ceiling",
                        SEVERITIES,
                        index=SEVERITIES.index(agent.max_severity),
                        key=f"sev_{agent.agent_id}",
                    )
                with r3:
                    st.text_input(
                        "Knowledge source (production)",
                        value=agent.knowledge_sources,
                        disabled=True,
                        key=f"ks_{agent.agent_id}",
                    )

                agent.scope = st.text_input(
                    "The one question this agent answers",
                    value=agent.scope,
                    key=f"scope_{agent.agent_id}",
                )
                agent.instruction = st.text_area(
                    "Instruction — this goes into the system prompt above the shared contract",
                    value=agent.instruction,
                    height=190,
                    key=f"inst_{agent.agent_id}",
                )
                if agent.knowledge_mode == "rag_policy":
                    agent.retrieval_hint = st.text_input(
                        "Retrieval hint — weighted terms used to build this agent's BM25 query",
                        value=agent.retrieval_hint,
                        key=f"hint_{agent.agent_id}",
                    )
                st.caption(
                    f"Version {agent.version} · Tier {agent.tier} · "
                    f"PACS domain {agent.pacs_domain.replace('_', ' ')} · "
                    f"{_MODE_LABEL[agent.knowledge_mode]}"
                )


# --------------------------------------------------------------------------


def _prompt_inspector(fleet) -> None:
    st.markdown("### Exactly what an agent is sent")
    st.markdown(
        "Nothing is hidden. Pick an agent and a claim to see the assembled system prompt, "
        "the de-identified claim block, and — for Squad E — the policy clauses BM25 actually "
        "retrieved for that pairing."
    )

    claims = st.session_state.claims
    if not claims:
        st.info("Load a book of claims first.")
        return

    c1, c2 = st.columns(2)
    with c1:
        agent_id = st.selectbox(
            "Agent",
            [a.agent_id for a in fleet],
            format_func=lambda i: f"{i} · {next(a for a in fleet if a.agent_id == i).name}",
            key="pi_agent",
        )
    with c2:
        claim_id = st.selectbox(
            "Claim", [c.claim_id for c in claims], key="pi_claim"
        )

    agent = next(a for a in fleet if a.agent_id == agent_id)
    claim = next(c for c in claims if c.claim_id == claim_id)

    if agent.squad == "H":
        results = st.session_state.results.get(claim_id)
        material = (
            [f for f in results.findings if f.result in ("finding", "insufficient_evidence")]
            if results else []
        )
        system, user = build_synthesis_prompt(agent, claim, material)
        if not material:
            theme.notice(
                "This claim has not been audited yet, so the synthesis agent would receive an "
                "empty findings list. Run the audit to see the real payload."
            )
        grounded = []
    else:
        system, user, grounded = build_audit_prompt(
            agent, claim, st.session_state.get("_corpus")
        )
        if agent.knowledge_mode == "rag_policy" and not grounded:
            theme.notice(
                "No clauses were retrieved for this pairing. Either the policy corpus failed "
                "to load, or the agent's retrieval hint does not overlap this claim's "
                "vocabulary — in which case the agent will correctly return "
                "insufficient_evidence rather than reasoning from memory."
            )

    if grounded:
        st.markdown("#### Clauses retrieved for this agent on this claim")
        for c in grounded:
            st.markdown(
                f'<div class="cite"><span class="src">{theme.esc(c.locator)} · '
                f"{theme.esc(c.source_name)} {theme.esc(c.version)}</span>"
                f'<span class="txt">{theme.esc(c.passage[:400])}'
                f'{"…" if len(c.passage) > 400 else ""}</span></div>',
                unsafe_allow_html=True,
            )

    st.markdown("#### System prompt")
    st.code(system, language="text")

    st.markdown("#### User message")
    st.code(user, language="text")
