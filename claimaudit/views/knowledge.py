"""Knowledge base — the policy corpus, the chunking, and a live retrieval tester."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from .. import theme
from ..retrieval import tokenise


def render(corpus) -> None:
    theme.page_header(
        "Knowledge base",
        "The difference between a finding and an opinion is a citation",
        "Squad E does not remember the insurer's policy terms — it retrieves them. One full policy "
        "wording is loaded, chunked on clause boundaries and indexed with BM25 inside the "
        "application process. No external vector database, no embedding service, no network "
        "call for retrieval.",
    )

    if corpus is None:
        st.error("The policy corpus is not loaded.")
        return

    words = len(corpus.raw.split())
    theme.tiles(
        [
            ("Documents", "1", "the loaded policy wording"),
            ("Clauses indexed", str(len(corpus.chunks)), "one chunk per numbered clause"),
            ("Sections", str(len(corpus.sections)), "definitions through termination"),
            ("Words", f"{words:,}", "full wording, not a summary"),
            ("Version", corpus.version, f"effective {corpus.effective_from}"),
        ]
    )

    tab_search, tab_browse, tab_design, tab_source = st.tabs(
        ["Retrieval tester", "Clause browser", "How retrieval works", "Full document"]
    )

    # ======================================================================
    with tab_search:
        st.markdown("### Ask the corpus what an agent would ask it")
        st.markdown(
            "The same index, tokeniser and scoring the Squad E agents use at run time. If a "
            "clause does not surface here, the agent does not see it either — which is "
            "precisely the transparency a lexical index buys you over an embedding you "
            "cannot inspect."
        )

        presets = {
            "— type your own —": "",
            "Is a rhinoplasty covered?": "cosmetic reconstructive rhinoplasty septoplasty "
                                         "functional impairment exclusion",
            "Dental waiting period": "dental waiting period six months inception crown accident",
            "Does this need pre-authorisation?": "pre-authorisation required threshold MRI "
                                                 "surgery inpatient validity emergency",
            "Optical sub-limit and frames": "optical sub-limit frames lenses sunglasses "
                                            "refractive policy year",
            "Elective surgery abroad": "territorial scope elective treatment outside United "
                                       "Arab Emirates emergency worldwide prior approval",
            "Pre-existing condition": "pre-existing condition chronic definition waiting "
                                      "period continuous transfer waiver",
            "Splitting a claim across dates": "splitting episode of care multiple claims "
                                              "threshold sub-limit pre-authorisation",
        }
        preset = st.selectbox("Try one of the questions the agents face", list(presets))
        query = st.text_input(
            "Query", value=presets[preset], placeholder="e.g. crown following an accident"
        )
        s1, s2 = st.columns([1, 2])
        with s1:
            top_k = st.slider("Lexical hits", 1, 12, 6)
        with s2:
            expand = st.toggle(
                "Agent mode — follow cross-references and pull section siblings",
                value=True,
                help="Off: raw BM25 only. On: the full three-pass retrieval the Squad E "
                     "agents actually run. Each result shows why it was retrieved.",
            )

        if query.strip():
            hits = (
                corpus.retrieve_for_agent("", query, top_k=top_k)
                if expand
                else corpus.search(query, top_k=top_k)
            )
            terms = sorted(set(tokenise(query)))
            inherited = len([h for h in hits if h.why != "lexical match"])
            st.caption(
                f"{len(hits)} clause(s) — {len(hits) - inherited} matched lexically, "
                f"{inherited} inherited by reference or section. "
                f"Query terms after stop-word removal and synonym folding: "
                + ", ".join(f"`{t}`" for t in terms)
            )
            if not hits:
                theme.notice(
                    "Nothing matched. At run time an agent in this position returns "
                    "<code>insufficient_evidence</code> and names the clause it would need — "
                    "it does not fall back to reasoning from memory."
                )
            for h in hits:
                c = h.chunk
                why_pill = (
                    theme.pill("matched", theme.ACCENT, "#E6F2F2")
                    if h.why == "lexical match"
                    else theme.pill(h.why, "#7A4CA0", "#F2EBF8")
                )
                st.markdown(
                    f'<div class="ca-panel">'
                    f'<div class="ca-panel-head">'
                    f"{theme.esc(c.locator)} &nbsp;·&nbsp; {theme.esc(c.heading)} "
                    f'&nbsp;<span class="tag">score {h.score}</span> {why_pill}</div>'
                    f'<div class="ca-panel-body">'
                    f'<div style="font-size:.74rem;color:{theme.MUTED};margin-bottom:.4rem">'
                    f"{theme.esc(c.section)}</div>"
                    f'<div style="font-size:.87rem;color:{theme.INK_SOFT};line-height:1.65;'
                    f'white-space:pre-wrap">{theme.esc(c.text)}</div>'
                    f"</div></div>",
                    unsafe_allow_html=True,
                )

    # ======================================================================
    with tab_browse:
        st.markdown("### Every clause in the index")
        section = st.selectbox("Section", ["All"] + corpus.sections)
        chunks = (
            corpus.chunks
            if section == "All"
            else [c for c in corpus.chunks if c.section == section]
        )
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Locator": c.locator,
                        "Heading": c.heading,
                        "Section": c.section,
                        "Words": len(c.text.split()),
                        "Text": c.text[:180] + ("…" if len(c.text) > 180 else ""),
                    }
                    for c in chunks
                ]
            ),
            use_container_width=True,
            hide_index=True,
            height=520,
        )

    # ======================================================================
    with tab_design:
        st.markdown("### Why BM25, in-process")
        c1, c2 = st.columns(2)
        with c1:
            theme.card(
                "A policy wording is a lexical document",
                "The clause that decides a case almost always contains the words the case is "
                "about — <em>waiting period</em>, <em>sub-limit</em>, <em>cosmetic</em>, "
                "<em>territorial</em>. Lexical retrieval is strong here, and it is "
                "inspectable: an auditor can see exactly why a clause surfaced. An embedding "
                "match cannot be explained to a provider disputing a deduction.",
            )
            theme.card(
                "Chunk on the clause, not on a token count",
                "Chunks are cut on clause boundaries (§x.y), so a retrieved passage is a "
                "complete, citable legal unit with a locator that means something. Fixed-size "
                "windows would split a sub-limit away from the schedule that qualifies it.",
            )
        with c2:
            theme.card(
                "Query construction",
                "Each Squad E agent carries a <em>retrieval hint</em> — the vocabulary of its "
                "own question. The query is the hint, weighted twice, plus the claim text, so "
                "the pre-authorisation agent still pulls pre-authorisation clauses on a claim "
                "whose text is dominated by clinical language.",
            )
            theme.card(
                "The locator round-trip",
                "The agent cites a locator. The application resolves that locator back to the "
                "clause in the index and shows the auditor <strong>the real passage</strong>, "
                "not the model's paraphrase. A locator that does not resolve is downgraded to "
                "an unverified citation — the model cannot invent a clause number into "
                "existence.",
            )

        theme.notice(
            "<strong>The corpus is not fixed at one wording.</strong> Every document indexed "
            "here is chunked on clause boundaries and addressed by locator, so adding a "
            "second product wording — or a rules manual, or a drug list — adds clauses the "
            "same agents retrieve and cite the same way. The agent contract does not change.",
            kind="info",
        )

    # ======================================================================
    with tab_source:
        st.markdown(f"### {corpus.source_name}")
        st.caption(
            f"Source ID `{corpus.source_id}` · version {corpus.version} · "
            f"effective {corpus.effective_from} · {words:,} words"
        )
        theme.notice(
            "<strong>Synthetic document.</strong> This wording was authored for this "
            "platform. It is structurally realistic — UAE market conventions, DoH-style "
            "benefit structure, numbered clauses — but it is not a real insurance contract "
            "and must not be relied on for any adjudication decision."
        )
        st.markdown(corpus.raw)
