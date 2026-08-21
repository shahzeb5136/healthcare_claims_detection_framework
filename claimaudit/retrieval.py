"""
In-app retrieval over the policy corpus.

No external vector database. The corpus is chunked on clause boundaries (§x.y),
indexed with BM25 in pure Python, and queried at run time by the Squad E agents.
Retrieved passages are injected into the agent prompt and the agent must cite the
clause locator it relied on — which is what makes a Squad E citation *grounded*
rather than remembered.

Why BM25 and not embeddings: a policy wording is a lexical document. The clause
that decides a case usually contains the words the case is about ("waiting
period", "sub-limit", "cosmetic"). Lexical retrieval is transparent — the
auditor can see exactly why a clause surfaced — and needs no model call, no key
and no service.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


# --------------------------------------------------------------------------
# Tokenisation
# --------------------------------------------------------------------------

_TOKEN = re.compile(r"[a-z0-9]+")

# Small, domain-aware stop list. Kept short on purpose: over-aggressive stopping
# hurts on legal text where "not", "other than" and "only" carry the meaning.
_STOP = {
    "the", "a", "an", "and", "or", "of", "to", "in", "for", "on", "at", "by",
    "is", "are", "be", "been", "was", "were", "as", "that", "this", "these",
    "those", "it", "its", "any", "all", "which", "shall", "may", "will",
    "with", "from", "under", "such", "s",
}

_SYNONYMS = {
    "preauth": "authorisation",
    "preauthorisation": "authorisation",
    "preauthorization": "authorisation",
    "authorization": "authorisation",
    "authorized": "authorised",
    "sublimit": "limit",
    "sublimits": "limit",
    "copay": "co",
    "copayment": "co",
    "coinsurance": "co",
    "waitingperiod": "waiting",
    "preexisting": "pre",
    "mri": "imaging",
    "ct": "imaging",
}


def tokenise(text: str) -> list[str]:
    out = []
    for t in _TOKEN.findall(text.lower()):
        if t in _STOP:
            continue
        out.append(_SYNONYMS.get(t, t))
    return out


# --------------------------------------------------------------------------
# Chunking
# --------------------------------------------------------------------------


@dataclass
class Chunk:
    chunk_id: str
    source_id: str
    source_name: str
    version: str
    effective_from: str
    section: str        # e.g. "§6 Pre-Authorisation"
    locator: str        # e.g. "§6.1"
    heading: str        # e.g. "Services always requiring pre-authorisation"
    text: str

    @property
    def display(self) -> str:
        return f"{self.locator} {self.heading}".strip()


_CLAUSE_RE = re.compile(r"^\*\*(§[\d.]+)\s+([^.*]+?)[.]?\*\*\s*(.*)$", re.S)
_H2_RE = re.compile(r"^##\s+(.*)$")
# Cross-references inside clause text: "as defined in §1.10", "under §6.1(i)".
_XREF = re.compile(r"§\s*(\d+(?:\.\d+)*)")


def _frontmatter(text: str) -> dict[str, str]:
    meta: dict[str, str] = {}
    for line in text.splitlines()[:30]:
        m = re.match(r"^\*\*(.+?):\*\*\s+(.+)$", line.strip())
        if m:
            meta[m.group(1).strip().lower()] = m.group(2).strip()
    return meta


def chunk_policy(path: str | Path) -> list[Chunk]:
    """Split the policy markdown into one chunk per numbered clause."""
    raw = Path(path).read_text(encoding="utf-8")
    meta = _frontmatter(raw)
    source_id = meta.get("source id", "POLICY")
    source_name = meta.get("document title", Path(path).stem)
    version = meta.get("version", "V1")
    effective = meta.get("effective from", "")

    chunks: list[Chunk] = []
    section = ""
    buffer: list[str] = []
    current: tuple[str, str] | None = None  # (locator, heading)

    def flush() -> None:
        nonlocal buffer, current
        if current and buffer:
            body = "\n".join(buffer).strip()
            if body:
                chunks.append(
                    Chunk(
                        chunk_id=f"{source_id}:{current[0]}",
                        source_id=source_id,
                        source_name=source_name,
                        version=version,
                        effective_from=effective,
                        section=section,
                        locator=current[0],
                        heading=current[1],
                        text=body,
                    )
                )
        buffer = []

    for line in raw.splitlines():
        h2 = _H2_RE.match(line.strip())
        if h2:
            flush()
            current = None
            section = h2.group(1).strip()
            continue

        clause = _CLAUSE_RE.match(line.strip())
        if clause:
            flush()
            current = (clause.group(1), clause.group(2).strip())
            rest = clause.group(3).strip()
            buffer = [rest] if rest else []
            continue

        if current is not None:
            buffer.append(line)

    flush()
    return chunks


# --------------------------------------------------------------------------
# BM25 index
# --------------------------------------------------------------------------


@dataclass
class Hit:
    chunk: Chunk
    score: float
    why: str = "lexical match"  # provenance, shown to the auditor


class BM25Index:
    """Okapi BM25. Small corpus, so everything stays in memory."""

    k1 = 1.4
    b = 0.72

    def __init__(self, chunks: list[Chunk]) -> None:
        self.chunks = chunks
        # The heading and locator carry a lot of signal in a legal document, so
        # they are indexed alongside the body rather than dropped.
        self.docs = [tokenise(f"{c.section} {c.heading} {c.text}") for c in chunks]
        self.tf = [Counter(d) for d in self.docs]
        self.lens = [len(d) for d in self.docs]
        self.avg_len = (sum(self.lens) / len(self.lens)) if self.lens else 0.0

        df: Counter = Counter()
        for d in self.docs:
            df.update(set(d))
        n = len(self.docs)
        self.idf = {
            term: math.log(1 + (n - c + 0.5) / (c + 0.5)) for term, c in df.items()
        }

    def score_all(self, query: str) -> dict[str, float]:
        """Raw BM25 score for every chunk, keyed by locator."""
        q = tokenise(query)
        out: dict[str, float] = {}
        if not q:
            return out
        for i, tf in enumerate(self.tf):
            dl = self.lens[i] or 1
            s = 0.0
            for term in q:
                f = tf.get(term)
                if not f:
                    continue
                idf = self.idf.get(term, 0.0)
                s += idf * (f * (self.k1 + 1)) / (
                    f + self.k1 * (1 - self.b + self.b * dl / (self.avg_len or 1))
                )
            out[self.chunks[i].locator] = round(s, 3)
        return out

    def search(self, query: str, top_k: int = 6, min_score: float = 0.5) -> list[Hit]:
        scores = self.score_all(query)
        by_locator = {c.locator: c for c in self.chunks}
        scored = [
            Hit(by_locator[loc], s) for loc, s in scores.items() if s > min_score
        ]
        scored.sort(key=lambda h: h.score, reverse=True)
        return scored[:top_k]


# --------------------------------------------------------------------------
# Corpus wrapper used by the app
# --------------------------------------------------------------------------


class PolicyCorpus:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.chunks = chunk_policy(self.path)
        self.index = BM25Index(self.chunks)
        self.raw = self.path.read_text(encoding="utf-8")

    # -- properties surfaced in the Knowledge Base page ---------------------

    @property
    def source_id(self) -> str:
        return self.chunks[0].source_id if self.chunks else "n/a"

    @property
    def source_name(self) -> str:
        return self.chunks[0].source_name if self.chunks else self.path.stem

    @property
    def version(self) -> str:
        return self.chunks[0].version if self.chunks else "n/a"

    @property
    def effective_from(self) -> str:
        return self.chunks[0].effective_from if self.chunks else ""

    @property
    def sections(self) -> list[str]:
        seen: list[str] = []
        for c in self.chunks:
            if c.section not in seen:
                seen.append(c.section)
        return seen

    def get(self, locator: str) -> Chunk | None:
        for c in self.chunks:
            if c.locator == locator:
                return c
        return None

    # -- retrieval ----------------------------------------------------------

    def search(self, query: str, top_k: int = 6) -> list[Hit]:
        return self.index.search(query, top_k=top_k)

    def retrieve_for_agent(
        self,
        claim_text: str,
        retrieval_hint: str,
        top_k: int = 6,
        max_total: int = 18,
    ) -> list[Hit]:
        """Retrieve the clauses an agent needs, the way a lawyer reads a policy.

        Three passes, because pure lexical top-k is not enough on a legal text:

        1. **Lexical.** The query is the agent's retrieval hint, weighted twice,
           plus the claim. The hint is what makes E04 pull pre-authorisation
           clauses on a claim whose text is dominated by clinical vocabulary.

        2. **Cross-references.** A retrieved clause that names another clause
           (`§1.10`, `§4.3`) pulls that clause in too. This is the pass that
           finds the definitions an exclusion depends on: §8.2 excludes cosmetic
           treatment *by reference to* §1.3 and §1.10, and an agent that never
           sees those definitions cannot make the argument.

        3. **Section siblings.** Clauses qualify each other within a section — a
           waiting period is meaningless without the waiver clause two lines
           below it, and a sub-limit is meaningless without its schedule. The
           best-scoring unretrieved siblings of the sections already represented
           are pulled in behind the primary hits.

        Every returned hit carries `why`, so the auditor can see whether a clause
        was matched or inherited.
        """
        query = f"{retrieval_hint} {retrieval_hint} {claim_text}"
        scores = self.index.score_all(query)
        primary = self.index.search(query, top_k=top_k)

        chosen: dict[str, Hit] = {h.chunk.locator: h for h in primary}

        # -- pass 2: follow cross-references out of the retrieved clauses
        for hit in primary:
            for ref in set(_XREF.findall(hit.chunk.text)):
                locator = f"§{ref}"
                if locator in chosen or locator == hit.chunk.locator:
                    continue
                chunk = self.get(locator)
                if chunk is None:
                    continue
                chosen[locator] = Hit(
                    chunk,
                    scores.get(locator, 0.0),
                    why=f"referenced by {hit.chunk.locator}",
                )

        # -- pass 3: unretrieved siblings of the sections already in play.
        # A sibling inherits credit from how strongly its section matched, not
        # just from its own wording. §2.3 ("elective treatment abroad needs prior
        # approval") barely mentions the words on an overseas claim, but it is
        # the clause that decides it — and it sits two lines from the clause that
        # did match.
        section_strength: dict[str, float] = {}
        for h in primary:
            section_strength[h.chunk.section] = max(
                section_strength.get(h.chunk.section, 0.0), h.score
            )

        siblings = [
            (
                max(scores.get(c.locator, 0.0), 0.35 * section_strength[c.section]),
                c,
            )
            for c in self.chunks
            if c.section in section_strength and c.locator not in chosen
        ]
        siblings.sort(key=lambda pair: pair[0], reverse=True)

        for weight, chunk in siblings:
            if len(chosen) >= max_total:
                break
            chosen[chunk.locator] = Hit(chunk, round(weight, 3), why="same section")

        out = list(chosen.values())
        # Primary lexical hits first, then inherited clauses by their weight.
        out.sort(key=lambda h: (h.why != "lexical match", -h.score))
        return out[:max_total]


def format_passages(hits: list[Hit]) -> str:
    """Render retrieved clauses for injection into the agent prompt."""
    if not hits:
        return "(no clauses retrieved — say so and return insufficient_evidence)"
    out = []
    for h in hits:
        c = h.chunk
        out.append(
            f"--- clause {c.locator} | {c.section} | {c.heading} "
            f"| score {h.score} | {h.why} ---\n{c.text.strip()}"
        )
    return "\n\n".join(out)
