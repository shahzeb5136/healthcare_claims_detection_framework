"""Run audit — configure the pass, watch it execute, see what it cost."""

from __future__ import annotations

import streamlit as st

from .. import theme
from ..llm import (
    CORE42,
    CORE42_NOTE,
    PRICING,
    ProviderError,
    build_client,
    estimate_cost,
)
from ..orchestrator import RunOptions, run_book, run_tier0_only


def render(corpus, goto) -> None:
    theme.page_header(
        "Run audit",
        "Deterministic first, then only what earns it",
        "Every claim gets the deterministic checks. The risk gate decides which claims are "
        "worth the cost of full agentic review — and a sampling quota pulls low-risk claims "
        "through anyway, because a triage design that only ever examines what it already "
        "thinks is risky cannot detect the risk it has learned to ignore.",
    )

    claims = st.session_state.claims
    fleet = st.session_state.fleet
    cfg = st.session_state.llm

    if not claims:
        st.warning("No claims loaded. Go to Claims to load the demonstration book or upload your own.")
        return

    enabled = [a for a in fleet if a.enabled]
    audit_agents = [a for a in enabled if a.squad in ("B", "C", "E")]
    synth_agents = [a for a in enabled if a.squad == "H"]

    # ----------------------------------------------------------------- scope
    st.markdown("### 1 · Scope")

    ids = [c.claim_id for c in claims]

    # Seed the selection once. Streamlit forbids assigning to a widget's key after
    # the widget has been instantiated in the same run, so the bulk-select buttons
    # below do it from an on_click callback, which runs before the rerun.
    if "run_selection" not in st.session_state:
        st.session_state.run_selection = ids[:3] if len(ids) > 3 else list(ids)
    st.session_state.run_selection = [
        cid for cid in st.session_state.run_selection if cid in ids
    ]

    def _set_selection(value: list[str]) -> None:
        st.session_state.run_selection = value

    c1, c2 = st.columns([3, 2])
    with c1:
        labels = {
            c.claim_id: f"{c.claim_id} · {c.clinician_specialty} · "
                        f"{theme.money_short(c.gross_amount)}"
            for c in claims
        }
        chosen = st.multiselect(
            "Claims to audit",
            ids,
            format_func=lambda i: labels[i],
            key="run_selection",
        )
        b1, b2, b3 = st.columns(3)
        with b1:
            st.button("Select all", use_container_width=True,
                      on_click=_set_selection, args=(list(ids),))
        with b2:
            st.button("First three", use_container_width=True,
                      on_click=_set_selection, args=(ids[:3],))
        with b3:
            st.button("Clear", use_container_width=True,
                      on_click=_set_selection, args=([],))

    with c2:
        st.markdown("**Execution**")
        use_gate = st.toggle(
            "Apply the risk gate",
            value=False,
            help="Off: every selected claim gets the full fleet — clearest for a "
                 "walkthrough. On: only claims at or above the threshold get agentic "
                 "review, plus a sampled slice of the rest.",
        )
        threshold = st.slider("Gate threshold (risk score)", 0, 100, 30, disabled=not use_gate)
        run_synth = st.toggle(
            "Run Squad H synthesis", value=True,
            help="Consolidation, conflict resolution, disposition and the provider letter.",
        )
        concurrency = st.slider(
            "Concurrent agent calls", 1, 16, 6,
            help="Higher is faster until the provider rate-limits you. Drop to 2–4 if you "
                 "see rate-limit errors.",
        )

    selected = [c for c in claims if c.claim_id in chosen]

    # ------------------------------------------------------------------ cost
    st.markdown("### 2 · What this will cost")

    n_audit = len(selected) * len(audit_agents)
    n_synth = len(selected) * len(synth_agents) if run_synth else 0
    n_calls = n_audit + n_synth

    # ~2,600 input / ~330 output tokens per audit call is typical for these prompts;
    # the synthesis agents read the findings payload so they run heavier.
    est_in = n_audit * 2600 + n_synth * 3400
    est_out = n_audit * 330 + n_synth * 700
    est_cost = estimate_cost(cfg.model, est_in, est_out)

    theme.tiles(
        [
            ("Claims selected", str(len(selected)), f"of {len(claims)} in the book"),
            ("Agents enabled", str(len(enabled)), f"{len(audit_agents)} audit + {len(synth_agents)} synthesis"),
            ("Model calls", f"{n_calls:,}", "one per agent per claim"),
            ("Estimated tokens", f"{(est_in + est_out) / 1000:,.0f}k", "input + output"),
            ("Estimated cost",
             f"${est_cost:,.2f}" if cfg.model in PRICING else "—",
             f"at {cfg.model} list rates" if cfg.model in PRICING else "no published rate"),
        ]
    )

    if n_calls > 200:
        theme.notice(
            f"<strong>{n_calls:,} model calls.</strong> That is a real bill and a real wait. "
            "For a walkthrough, three or four claims show every squad. Turn the risk gate on "
            "to see how the production economics work at volume."
        )

    st.caption(
        "This is an estimate from typical prompt sizes, not a quote. Actual usage is "
        "reported after the run. At a hundred thousand claims a month, running sixty-two "
        "reasoning agents against every claim would be over six million invocations — which "
        "is why the production design triages rather than brute-forces."
    )

    # ------------------------------------------------------------------- run
    st.markdown("### 3 · Run")

    ready = True
    problems = []
    if not selected:
        problems.append("Select at least one claim.")
        ready = False
    if not enabled:
        problems.append("Enable at least one agent in the Agent Studio.")
        ready = False
    if cfg.provider == CORE42:
        theme.notice(
            f"<strong>Core42 selected — in-country inference.</strong> {CORE42_NOTE}",
            kind="info",
        )
        problems.append(
            "Core42 is illustrative in this demonstrator and makes no calls. Switch "
            "provider to run the fleet, or use the deterministic checks below."
        )
        ready = False
    elif cfg.provider in ("Anthropic", "OpenAI") and not cfg.api_key:
        problems.append(f"Add your {cfg.provider} API key in the sidebar.")
        ready = False
    if corpus is None and any(a.knowledge_mode == "rag_policy" for a in enabled):
        problems.append("The policy corpus failed to load; Squad E cannot run.")
        ready = False

    for p in problems:
        st.warning(p)

    r1, r2 = st.columns([1, 3])
    with r1:
        go = st.button("Run the fleet", type="primary", disabled=not ready, use_container_width=True)
    with r2:
        t0_only = st.button(
            "Deterministic checks only (no key needed)",
            disabled=not selected,
            use_container_width=True,
            help="Runs the thirteen Tier 0 checks and the risk gate in-process. No model "
                 "calls, no cost — useful for showing the surface before anyone hands over "
                 "a key.",
        )

    # The outcome of a run — and the buttons that follow it — must not live inside
    # `if <button was clicked>`. On the next rerun that block is not entered, so the
    # buttons would not exist and the click would be lost. The outcome is parked in
    # session state and rendered below, outside both branches.
    if t0_only and selected:
        with st.spinner("Running deterministic checks…"):
            results = run_tier0_only(selected)
        merged = dict(st.session_state.results)
        merged.update(results)
        st.session_state.results = merged
        st.session_state.run_stats = None
        hits = sum(len(r.open_findings()) for r in results.values())
        st.session_state.last_run = {
            "kind": "tier0",
            "first_claim": selected[0].claim_id,
            "message": (
                f"Tier 0 complete on {len(selected)} claim(s): {hits} deterministic "
                "finding(s), zero model calls."
            ),
            "warning": "",
        }

    if go and selected:
        try:
            client = build_client(cfg)
        except ProviderError as exc:
            st.error(str(exc))
            return

        options = RunOptions(
            use_risk_gate=use_gate,
            gate_threshold=threshold,
            run_synthesis=run_synth,
            concurrency=concurrency,
        )

        bar = st.progress(0.0, text="Starting…")
        line = st.empty()

        def progress(done: int, total: int, label: str) -> None:
            frac = min(done / total, 1.0) if total else 1.0
            bar.progress(frac, text=f"{done} of {total} agent calls")
            line.caption(f"Completed: {label}")

        with st.spinner("Auditing…"):
            results, stats = run_book(
                selected, fleet, client, cfg, corpus, options, progress
            )

        bar.progress(1.0, text="Complete")
        line.empty()

        merged = dict(st.session_state.results)
        merged.update(results)
        st.session_state.results = merged
        st.session_state.run_stats = stats

        total_findings = sum(len(r.open_findings()) for r in results.values())
        exposure = sum(r.total_exposure for r in results.values())

        st.session_state.last_run = {
            "kind": "full",
            "first_claim": selected[0].claim_id,
            "message": (
                f"Audit complete. {stats.calls:,} model call(s) across "
                f"{len(selected)} claim(s) in {stats.wall_ms / 1000:,.1f}s. "
                f"{total_findings} finding(s) raised, {theme.money(exposure)} of "
                "exposure to review."
            ),
            "warning": (
                f"{stats.errors} agent call(s) did not return a usable result. They are "
                "recorded as agent errors in the workbench rather than dropped — an agent "
                "that fails silently is worse than one that fails loudly."
                if stats.errors else ""
            ),
        }

    # ------------------------------------------------------------ run outcome
    last = st.session_state.get("last_run")
    if last:
        st.success(last["message"])
        if last["warning"]:
            st.warning(last["warning"])

        b1, b2, b3 = st.columns([1, 1, 1])
        with b1:
            if st.button("Open the audit cockpit", type="primary", use_container_width=True):
                goto("Audit cockpit")
        with b2:
            if st.button("Go straight to the workbench", use_container_width=True):
                st.session_state.selected_claim = last["first_claim"]
                goto("Claim review workbench")
        with b3:
            if st.button("Dismiss", use_container_width=True):
                st.session_state.pop("last_run", None)
                st.rerun()

    # --------------------------------------------------------------- last run
    stats = st.session_state.run_stats
    if stats is not None:
        st.markdown("### Last run")
        cost = estimate_cost(st.session_state.llm.model, stats.input_tokens, stats.output_tokens)
        theme.tiles(
            [
                ("Model calls", f"{stats.calls:,}", f"{stats.errors} error(s)"),
                ("Wall clock", f"{stats.wall_ms / 1000:,.1f}s",
                 f"{stats.calls / max(stats.wall_ms / 1000, 0.001):,.1f} calls/sec"),
                ("Input tokens", f"{stats.input_tokens:,}", "prompt + retrieved clauses"),
                ("Output tokens", f"{stats.output_tokens:,}", "findings and synthesis"),
                ("Actual cost", f"${cost:,.4f}" if cost else "—", "at list rates"),
            ]
        )
        if stats.gated_out or stats.sampled_in:
            st.caption(
                f"Risk gate: {stats.gated_out} claim(s) held at Tier 0, "
                f"{stats.sampled_in} low-risk claim(s) pulled through by the sampling quota."
            )
