"""Claim review workbench — the surface an auditor spends the day on."""

from __future__ import annotations

from datetime import datetime

import streamlit as st

from .. import theme
from ..schema import SEVERITY_RANK

SQUAD_ORDER = {"T0": 0, "B": 1, "C": 2, "E": 3, "H": 4}
SQUAD_TITLE = {
    "T0": "Tier 0 — deterministic checks",
    "B": "Squad B — coding integrity",
    "C": "Squad C — clinical appropriateness",
    "E": "Squad E — policy, benefit and contract",
}

DECISIONS = ["pending", "accepted", "amended", "rejected", "escalated"]

AUTHORITY = [
    (10_000, "Auditor"),
    (50_000, "Audit manager"),
    (float("inf"), "Medical Director"),
]


def _authority(amount: float) -> str:
    for ceiling, who in AUTHORITY:
        if amount <= ceiling:
            return who
    return "Medical Director"


def render(goto) -> None:
    results = st.session_state.results
    claims = {c.claim_id: c for c in st.session_state.claims}

    if not results:
        theme.page_header("Claim review workbench", "Nothing to review yet")
        st.info("Run the fleet first — or run the deterministic checks, which need no key.")
        if st.button("Go to Run audit", type="primary"):
            goto("Run audit")
        return

    available = [cid for cid in results if cid in claims]
    if not available:
        st.warning("The audited claims are no longer in the loaded book.")
        return

    current = st.session_state.get("selected_claim")
    if current not in available:
        current = available[0]

    # No `key` on the selectbox: prev/next drive `selected_claim`, and a stored
    # widget value would override the `index` we pass and pin the selection.
    top = st.columns([3, 1, 1])
    with top[0]:
        current = st.selectbox(
            "Claim under review", available, index=available.index(current)
        )
        st.session_state.selected_claim = current
    idx = available.index(current)
    with top[1]:
        st.write("")
        if st.button("← Previous", disabled=idx == 0, use_container_width=True):
            st.session_state.selected_claim = available[idx - 1]
            st.rerun()
    with top[2]:
        st.write("")
        if st.button("Next →", disabled=idx >= len(available) - 1, use_container_width=True):
            st.session_state.selected_claim = available[idx + 1]
            st.rerun()

    claim = claims[current]
    res = results[current]

    _header(claim, res)

    left, mid, right = st.columns([1.05, 2.25, 1.15], gap="medium")

    with left:
        _pane_context(claim, res)
    with mid:
        _pane_findings(claim, res)
    with right:
        _pane_decision(claim, res)

    st.markdown("---")
    _synthesis_tabs(res)


# ==========================================================================


def _header(claim, res) -> None:
    open_f = res.open_findings()
    live = [f for f in open_f if f.human_decision != "rejected"]
    sev = res.max_severity or "clean"
    risk = res.consolidation.get("risk", {})

    theme.page_header(
        f"{claim.clinician_specialty} · {claim.facility_name}",
        claim.claim_id,
        f"{claim.encounter_type.title()} encounter, {claim.encounter_start}. "
        f"{len(res.findings)} agent result(s) on file, {len(open_f)} finding(s) raised, "
        f"{res.reviewed_count} decided.",
    )

    accent = theme.SEVERITY_COLOUR.get(sev, ("#16704A", "#E7F3ED"))[0]
    theme.tiles(
        [
            ("Gross billed", theme.money(claim.gross_amount), f"net {theme.money(claim.net_amount)}"),
            ("Exposure at risk", theme.money(res.total_exposure),
             f"{100 * res.total_exposure / claim.gross_amount:,.1f}% of gross"
             if claim.gross_amount else ""),
            ("Findings", str(len(live)),
             " · ".join(f"{n} {s}" for s, n in res.by_severity().items() if n) or "none open"),
            ("Max severity", sev, "clamped to each agent's ceiling"),
            ("Risk score", str(risk.get("score", "—")), f"band {risk.get('band', '—')}"),
            ("Reviewed", f"{res.reviewed_count}/{len(open_f)}",
             "complete" if res.review_complete else "outstanding"),
        ],
        accent=accent,
    )


# ==========================================================================


def _pane_context(claim, res) -> None:
    theme.panel_open("Claim context")
    band_lo = (claim.member_age // 5) * 5
    st.markdown(
        theme.kv_rows(
            [
                ("Setting", claim.encounter_type),
                ("Period", f"{claim.encounter_start} → {claim.encounter_end}"),
                ("Length of stay", f"{claim.length_of_stay_days} day(s)"),
                ("Place", f"{claim.place_of_treatment}"),
                ("Facility", claim.facility_name),
                ("Network tier", claim.network_tier),
                ("Clinician", claim.clinician_name),
                ("Member", claim.member_sk),
                ("Age band / gender",
                 f"{band_lo}-{band_lo + 4} · {claim.member_gender}"
                 if claim.member_age < 90 else f"90+ · {claim.member_gender}"),
                ("Plan", claim.plan_code),
                ("Scheme inception", claim.scheme_inception),
                ("Pre-authorisation", claim.prior_auth_status.replace("_", " ")),
            ]
        ),
        unsafe_allow_html=True,
    )
    theme.panel_close()

    if claim.diagnoses:
        rows = "".join(
            f"<tr><td class='num'>{d.sequence}</td>"
            f"<td class='mono'>{theme.esc(d.diagnosis_code)}</td>"
            f"<td>{theme.esc(d.description)}</td></tr>"
            for d in sorted(claim.diagnoses, key=lambda x: x.sequence)
        )
        st.markdown(
            f'<div class="ca-panel"><div class="ca-panel-head">Diagnoses</div>'
            f'<div class="ca-panel-body lines"><table>{rows}</table></div></div>',
            unsafe_allow_html=True,
        )

    if claim.activities:
        flagged = {f.line_ref for f in res.open_findings() if f.line_ref}
        rows = ""
        for a in claim.activities:
            mark = (
                f' <span class="pill" style="color:#B3261E;background:#FDECEA">flagged</span>'
                if a.line_ref in flagged else ""
            )
            rows += (
                f"<tr><td class='mono'>{theme.esc(a.line_ref)}{mark}</td>"
                f"<td class='mono'>{theme.esc(a.activity_code)}</td>"
                f"<td>{theme.esc(a.description)}</td>"
                f"<td class='num'>{a.gross_amount:,.2f}</td></tr>"
            )
        st.markdown(
            f'<div class="ca-panel"><div class="ca-panel-head">Billed lines</div>'
            f'<div class="ca-panel-body lines"><table>{rows}</table></div></div>',
            unsafe_allow_html=True,
        )

    if claim.clinical_notes:
        with st.expander("Clinical record extract", expanded=False):
            st.text(claim.clinical_notes)
    if claim.attachments:
        with st.expander("Attachments", expanded=False):
            for doc in claim.attachments:
                st.markdown(f"- {doc}")
    if claim.demo_note:
        with st.expander("Demonstration note — what this claim tests", expanded=False):
            st.caption(claim.demo_note)
            st.caption(
                "This note is never sent to an agent. It exists so you can check the fleet "
                "against what the claim was built to contain."
            )


# ==========================================================================


def _pane_findings(claim, res) -> None:
    st.markdown("#### Agent findings")

    findings = res.open_findings()
    other = [f for f in res.findings if not f.is_finding]

    if not findings:
        st.markdown(
            f'<div class="ca-card" style="border-top:3px solid #16704A">'
            f"<h4>No findings raised</h4>"
            f"<p>Every agent that applies to this claim returned <code>no_finding</code> or "
            f"<code>not_applicable</code>. That is a result, not an absence of one — "
            f"specificity is what makes the fleet usable at volume.</p></div>",
            unsafe_allow_html=True,
        )
    else:
        # Bulk actions run as callbacks: they must set the per-finding radio's
        # session-state key as well as the finding itself, or the widget's stored
        # value silently reverts the change on the next run.
        def _bulk(decision: str, only_pending: bool = True) -> None:
            stamp = datetime.now().isoformat(timespec="seconds")
            for f in findings:
                if only_pending and f.human_decision != "pending":
                    continue
                f.human_decision = decision
                st.session_state[f"dec_{f.key}"] = decision
                if decision == "pending":
                    f.decided_by, f.decided_ts = "", ""
                    f.amended_exposure_aed = None
                    f.reviewer_note = ""
                    st.session_state[f"note_{f.key}"] = ""
                else:
                    f.decided_by = "demo.auditor"
                    f.decided_ts = stamp

        b1, b2, b3 = st.columns(3)
        with b1:
            st.button("Accept all open", use_container_width=True,
                      on_click=_bulk, args=("accepted",))
        with b2:
            st.button("Reject all open", use_container_width=True,
                      on_click=_bulk, args=("rejected",))
        with b3:
            st.button("Reset decisions", use_container_width=True,
                      on_click=_bulk, args=("pending", False))

        ordered = sorted(
            findings,
            key=lambda f: (
                SQUAD_ORDER.get(f.squad, 9),
                -SEVERITY_RANK.get(f.severity, 0),
                -f.exposure_aed,
            ),
        )

        last_squad = None
        for f in ordered:
            if f.squad != last_squad:
                st.markdown(
                    f'<div style="margin:.9rem 0 .35rem 0;font-size:.72rem;font-weight:680;'
                    f"letter-spacing:.09em;text-transform:uppercase;"
                    f'color:{theme.SQUAD_COLOUR.get(f.squad, theme.MUTED)}">'
                    f"{theme.esc(SQUAD_TITLE.get(f.squad, f.squad))}</div>",
                    unsafe_allow_html=True,
                )
                last_squad = f.squad
            _finding_card(f)

    if other:
        with st.expander(
            f"Agents that returned nothing to act on ({len(other)})", expanded=False
        ):
            st.caption(
                "Shown in full because an agent that abstains is telling you something. "
                "insufficient_evidence names the document that would settle the question; "
                "an error means the agent did not answer at all and must not be read as a "
                "clean result."
            )
            for f in sorted(other, key=lambda x: (SQUAD_ORDER.get(x.squad, 9), x.agent_id)):
                st.markdown(
                    f"{theme.squad_tag(f.squad, f.agent_id)} "
                    f"{theme.result_pill(f.result)} "
                    f"**{theme.esc(f.agent_name)}** — "
                    f"{theme.esc(f.statement or f.rationale or 'no comment returned')}",
                    unsafe_allow_html=True,
                )
                if f.result in ("insufficient_evidence", "error") and f.rationale:
                    st.caption(f.rationale[:400])


def _finding_card(f) -> None:
    colour = theme.SEVERITY_COLOUR.get(f.severity, theme.SEVERITY_COLOUR["minor"])[0]

    head = (
        theme.squad_tag(f.squad, f.agent_id)
        + " "
        + theme.severity_pill(f.severity)
        + " "
        + theme.decision_pill(f.human_decision)
        + (
            f'<span class="pill" style="color:#54687C;background:#EEF1F4">'
            f"{f.line_ref}</span>" if f.line_ref else ""
        )
    )

    grounded = any(c.grounded for c in f.citations)
    ground_pill = (
        theme.pill("grounded", theme.ACCENT, "#E6F2F2")
        if grounded
        else (theme.pill("unverified citation", "#B4530A", "#FDF0E4") if f.citations else "")
    )

    st.markdown(
        f'<div class="finding" style="border-left-color:{colour}">'
        f'<div class="head">{head}{ground_pill}</div>'
        f'<div class="who">{theme.esc(f.agent_name)} · confidence '
        f"{f.confidence:.2f} · exposure {theme.money(f.exposure_aed)} · "
        f"recommends {theme.esc(f.recommended_action.replace('_', ' '))}</div>"
        f'<div class="stmt">{theme.esc(f.statement)}</div>'
        f'<div class="rat">{theme.esc(f.rationale)}</div>'
        f"</div>",
        unsafe_allow_html=True,
    )

    if f.citations or f.evidence_refs:
        with st.expander("Evidence and citations", expanded=False):
            for c in f.citations:
                cls = "cite" if c.grounded else "cite unverified"
                label = (
                    f"{c.locator} · {c.source_name} {c.version}"
                    if c.grounded
                    else f"UNVERIFIED · {c.source_name}"
                    + (f" · {c.locator}" if c.locator else "")
                )
                body = c.passage or "(the agent did not quote the source text)"
                st.markdown(
                    f'<div class="{cls}"><span class="src">{theme.esc(label)}</span>'
                    f'<span class="txt">{theme.esc(body)}</span></div>',
                    unsafe_allow_html=True,
                )
            if f.evidence_refs:
                st.caption("Relied on: " + " · ".join(f.evidence_refs))
            st.caption(
                f"Agent {f.agent_id} v{f.agent_version} · model {f.model_ref} · "
                f"trace {f.trace_id} · {f.latency_ms}ms"
            )

    c1, c2, c3 = st.columns([2.2, 1, 2])
    with c1:
        choice = st.radio(
            "Decision",
            DECISIONS,
            index=DECISIONS.index(f.human_decision),
            key=f"dec_{f.key}",
            horizontal=True,
            label_visibility="collapsed",
        )
    with c2:
        amended = st.number_input(
            "Amended AED",
            min_value=0.0,
            value=float(f.amended_exposure_aed if f.amended_exposure_aed is not None else f.exposure_aed),
            step=50.0,
            key=f"amt_{f.key}",
            label_visibility="collapsed",
            disabled=choice != "amended",
        )
    with c3:
        note = st.text_input(
            "Reviewer note",
            value=f.reviewer_note,
            key=f"note_{f.key}",
            placeholder="Reviewer note (recorded against the finding)",
            label_visibility="collapsed",
        )

    changed = choice != f.human_decision
    f.human_decision = choice
    f.reviewer_note = note
    f.amended_exposure_aed = amended if choice == "amended" else None
    if choice != "pending" and (changed or not f.decided_ts):
        f.decided_by = "demo.auditor"
        f.decided_ts = datetime.now().isoformat(timespec="seconds")
    if choice == "pending":
        f.decided_by = ""
        f.decided_ts = ""


# ==========================================================================


def _pane_decision(claim, res) -> None:
    h3 = res.consolidation.get("H03") or {}

    st.markdown("#### Decision")

    if h3.get("error"):
        theme.notice(f"H03 did not return a usable result: {theme.esc(h3['error'])}")
    elif h3:
        disposition = str(h3.get("disposition", "—")).replace("_", " ")
        st.markdown(
            f'<div class="ca-card" style="border-top:3px solid {theme.ACCENT}">'
            f'<div style="font-size:.68rem;font-weight:660;letter-spacing:.09em;'
            f'text-transform:uppercase;color:{theme.MUTED}">H03 recommends</div>'
            f'<div style="font-size:1.18rem;font-weight:660;color:{theme.INK};'
            f'margin:.25rem 0 .45rem 0">{theme.esc(disposition)}</div>'
            f'<p>{theme.esc(h3.get("rationale", ""))}</p></div>',
            unsafe_allow_html=True,
        )
        if h3.get("authority_required"):
            st.caption(f"Agent-stated authority: {h3['authority_required']}")
        if h3.get("denial_code"):
            st.caption(f"Denial code: `{h3['denial_code']}`")
    else:
        theme.notice(
            "Squad H did not run for this claim, so there is no recommended disposition. "
            "The settlement below is computed from your own decisions.",
            kind="info",
        )

    # ---- settlement arithmetic from the human decisions -------------------
    agreed_by_line: dict[str, float] = {}
    accepted = []
    for f in res.open_findings():
        if f.human_decision in ("accepted", "amended"):
            key = f.line_ref or "CLAIM"
            agreed_by_line[key] = max(agreed_by_line.get(key, 0.0), f.effective_exposure)
            accepted.append(f)

    deduction = round(sum(agreed_by_line.values()), 2)
    settlement = round(max(claim.gross_amount - deduction, 0.0), 2)

    rows = "".join(
        f"<tr><td>{theme.esc(f.agent_id)}</td>"
        f"<td class='mono'>{theme.esc(f.line_ref or '—')}</td>"
        f"<td>{theme.esc(f.statement[:58])}{'…' if len(f.statement) > 58 else ''}</td>"
        f"<td class='num'>{f.effective_exposure:,.2f}</td></tr>"
        for f in sorted(accepted, key=lambda x: -x.effective_exposure)
    ) or "<tr><td colspan='4' style='color:#6B7C8F'>No findings accepted yet.</td></tr>"

    escalated = [f for f in res.open_findings() if f.human_decision == "escalated"]
    pending = [f for f in res.open_findings() if f.human_decision == "pending"]

    st.markdown(
        f'<div class="ca-panel"><div class="ca-panel-head">Settlement arithmetic</div>'
        f'<div class="ca-panel-body lines">'
        f"<table><thead><tr><th>Agent</th><th>Line</th><th>Basis</th>"
        f"<th>Deduct</th></tr></thead><tbody>{rows}</tbody></table>"
        f'<div style="border-top:1px solid {theme.LINE};margin-top:.5rem;padding-top:.5rem">'
        + theme.kv_rows(
            [
                ("Gross billed", theme.money(claim.gross_amount)),
                ("Agreed deductions", theme.money(deduction)),
                ("Recommended settlement", theme.money(settlement)),
                ("Authority required", _authority(deduction)),
            ]
        )
        + "</div></div></div>",
        unsafe_allow_html=True,
    )

    st.caption(
        "Overlapping findings on the same line are counted once, at the larger amount — the "
        "consolidation rule that stops two agents describing one defect from being deducted "
        "twice."
    )

    if pending:
        theme.notice(
            f"<strong>{len(pending)} finding(s) still pending.</strong> Nothing has effect "
            "until every finding on the claim carries a human decision."
        )
    if escalated:
        theme.notice(
            f"{len(escalated)} finding(s) escalated. In production these route to the "
            "clinical queue or the special investigations unit with the clinical question "
            "stated and the evidence assembled.",
            kind="info",
        )
    if res.review_complete:
        st.success("Review complete. Every finding on this claim has a recorded decision.")

    st.markdown("##### Record the disposition")
    final = st.selectbox(
        "Final disposition",
        ["approve", "partial_approve", "deny", "request_information",
         "refer_clinical", "refer_siu"],
        index=(
            0 if deduction == 0
            else (2 if settlement <= 0 else 1)
        ),
        key=f"final_{claim.claim_id}",
        format_func=lambda s: s.replace("_", " "),
    )
    if st.button("Record decision", type="primary", use_container_width=True,
                 key=f"record_{claim.claim_id}"):
        res.consolidation["human_disposition"] = {
            "disposition": final,
            "deduction_aed": deduction,
            "settlement_aed": settlement,
            "authority": _authority(deduction),
            "decided_by": "demo.auditor",
            "decided_ts": datetime.now().isoformat(timespec="seconds"),
            "findings_accepted": len(accepted),
            "findings_rejected": len(
                [f for f in res.open_findings() if f.human_decision == "rejected"]
            ),
        }
        st.success(
            f"Recorded: {final.replace('_', ' ')} · settlement {theme.money(settlement)} · "
            f"{_authority(deduction)} authority."
        )

    recorded = res.consolidation.get("human_disposition")
    if recorded:
        st.caption(
            f"Last recorded: {recorded['disposition'].replace('_', ' ')} at "
            f"{recorded['decided_ts']} by {recorded['decided_by']}."
        )


# ==========================================================================


def _synthesis_tabs(res) -> None:
    st.markdown("### Squad H — synthesis")

    h01 = res.consolidation.get("H01")
    h02 = res.consolidation.get("H02")
    h03 = res.consolidation.get("H03")
    h04 = res.consolidation.get("H04")

    if not any([h01, h02, h03, h04]):
        theme.notice(
            "Squad H did not run for this claim. Enable synthesis on the Run audit page to "
            "see consolidation, conflict resolution, the disposition arithmetic and the "
            "bilingual provider letter.",
            kind="info",
        )
        return

    t1, t2, t3, t4 = st.tabs(
        ["H01 · Consolidation", "H02 · Disagreement", "H03 · Disposition", "H04 · Communication"]
    )

    with t1:
        if not h01:
            st.info("Not run.")
        elif h01.get("error"):
            st.error(h01["error"])
        else:
            st.markdown(f"**{theme.esc(h01.get('summary', ''))}**", unsafe_allow_html=True)
            st.caption(
                f"{h01.get('duplicates_merged', 0)} duplicate finding(s) merged · "
                f"total exposure {theme.money(float(h01.get('total_exposure_aed') or 0))}"
            )
            for d in h01.get("consolidated_defects", []) or []:
                st.markdown(
                    f'<div class="finding" style="border-left-color:'
                    f'{theme.SEVERITY_COLOUR.get(d.get("severity", "minor"), theme.SEVERITY_COLOUR["minor"])[0]}">'
                    f'<div class="head">{theme.severity_pill(d.get("severity", "minor"))}'
                    f'<span class="tag">{theme.esc(", ".join(d.get("contributing_agents", []) or []))}</span>'
                    f'<span class="tag">{theme.esc(", ".join(d.get("line_refs", []) or []) or "claim level")}</span>'
                    f"</div>"
                    f'<div class="stmt">{theme.esc(d.get("defect", ""))}</div>'
                    f'<div class="who">exposure '
                    f'{theme.money(float(d.get("exposure_aed") or 0))}</div></div>',
                    unsafe_allow_html=True,
                )

    with t2:
        if not h02:
            st.info("Not run.")
        elif h02.get("error"):
            st.error(h02["error"])
        else:
            st.markdown(f"**{theme.esc(h02.get('summary', ''))}**", unsafe_allow_html=True)
            conflicts = h02.get("conflicts", []) or []
            if not conflicts:
                st.caption(
                    "No material disagreement. Where agents do disagree, the platform shows "
                    "the disagreement rather than resolving it silently."
                )
            for c in conflicts:
                st.markdown(
                    f'<div class="ca-card"><h4>{theme.esc(c.get("question", ""))}</h4>'
                    f'<p><strong>A:</strong> {theme.esc(c.get("position_a", ""))}<br>'
                    f'<strong>B:</strong> {theme.esc(c.get("position_b", ""))}<br><br>'
                    f'<strong>Better supported:</strong> {theme.esc(c.get("better_supported", ""))} '
                    f'— {theme.esc(c.get("why", ""))}<br>'
                    f'<strong>What would settle it:</strong> '
                    f'{theme.esc(c.get("what_would_settle_it", ""))}</p></div>',
                    unsafe_allow_html=True,
                )

    with t3:
        if not h03:
            st.info("Not run.")
        elif h03.get("error"):
            st.error(h03["error"])
        else:
            rows = "".join(
                f"<tr><td class='mono'>{theme.esc(d.get('line_ref', '—'))}</td>"
                f"<td>{theme.esc(d.get('reason', ''))}</td>"
                f"<td class='mono'>{theme.esc(d.get('agent_id', ''))}</td>"
                f"<td class='num'>{float(d.get('amount_aed') or 0):,.2f}</td></tr>"
                for d in (h03.get("deductions", []) or [])
            ) or "<tr><td colspan='4' style='color:#6B7C8F'>No deductions proposed.</td></tr>"
            st.markdown(
                f'<div class="ca-panel"><div class="ca-panel-head">'
                f'Proposed deductions</div><div class="ca-panel-body lines">'
                f"<table><thead><tr><th>Line</th><th>Reason</th><th>Agent</th>"
                f"<th>Amount</th></tr></thead><tbody>{rows}</tbody></table></div></div>",
                unsafe_allow_html=True,
            )
            st.markdown(
                theme.kv_rows(
                    [
                        ("Disposition", str(h03.get("disposition", "—")).replace("_", " ")),
                        ("Gross billed", theme.money(float(h03.get("gross_billed_aed") or 0))),
                        ("Total deduction", theme.money(float(h03.get("total_deduction_aed") or 0))),
                        ("Recommended settlement",
                         theme.money(float(h03.get("recommended_settlement_aed") or 0))),
                        ("Authority required", str(h03.get("authority_required", "—"))),
                        ("Denial code", str(h03.get("denial_code") or "—")),
                    ]
                ),
                unsafe_allow_html=True,
            )
            st.caption(
                "Advisory only. The recorded decision is the one made by the human in the "
                "decision panel above."
            )

    with t4:
        if not h04:
            st.info("Not run.")
        elif h04.get("error"):
            st.error(h04["error"])
        else:
            st.markdown("##### Internal audit rationale")
            st.markdown(
                f'<div class="ca-card"><p>{theme.esc(h04.get("internal_rationale", ""))}</p></div>',
                unsafe_allow_html=True,
            )
            p1, p2 = st.columns(2)
            with p1:
                st.markdown("##### Provider communication — English")
                st.markdown(
                    f'<div class="ca-card"><p>{theme.esc(h04.get("provider_letter_en", ""))}</p></div>',
                    unsafe_allow_html=True,
                )
            with p2:
                st.markdown("##### Provider communication — Arabic")
                st.markdown(
                    f'<div class="ca-card" dir="rtl" lang="ar">'
                    f'<p style="text-align:right">{theme.esc(h04.get("provider_letter_ar", ""))}</p>'
                    f"</div>",
                    unsafe_allow_html=True,
                )
            if h04.get("tone_check"):
                st.caption(f"Disclosure check: {h04['tone_check']}")
            st.caption(
                "The provider-facing text must state the finding, the rule and the evidence "
                "without disclosing internal risk scoring, agent identifiers or confidence "
                "values. In production this is enforced by a guard agent, not by prompt "
                "instruction alone."
            )
