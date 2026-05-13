"""
Agent 0 — Literature Discovery
Fetches new AMD abstracts from PubMed, validates them through two layers,
then saves only confirmed AMD-relevant papers to the new-literature folder.

Validation pipeline:
  Layer 1 — Keyword filter  : fast, rule-based, kills obvious non-AMD papers
  Layer 2 — LLM agent       : Google ADK agent backed by Ollama, classifies
                               RELEVANT / BORDERLINE / IRRELEVANT
  HITL pause                : you decide what to do with BORDERLINE papers

Usage:
    python agent0_literature.py                  # last 30 days, up to 50 results
    python agent0_literature.py --days 180       # last 180 days
    python agent0_literature.py --max 200        # up to 200 results
    python agent0_literature.py --query "..."    # custom PubMed query
    python agent0_literature.py --no-llm         # skip Layer 2 (faster, less accurate)
"""

import argparse
import asyncio
import json
import time
from datetime import datetime, timedelta
from pathlib import Path

from Bio import Entrez

# ── Config ────────────────────────────────────────────────────────────────────

Entrez.email = "calina.borzan18@yahoo.com"

PROJECT_ROOT  = Path(__file__).parent
ABSTRACTS_DIR = PROJECT_ROOT / "data" / "stage-2" / "AMD" / "new-literature"
PROCESSED_IDS = PROJECT_ROOT / "data" / "stage-2" / "AMD" / "processed_pmids.json"

OLLAMA_MODEL  = "ollama_chat/llama3.1:8b"   # LiteLLM format for Ollama
OLLAMA_URL    = "http://localhost:11434"

DEFAULT_QUERY = (
    "(age-related macular degeneration[MeSH] OR "
    "\"age-related macular degeneration\"[tiab]) "
    "AND hasabstract[text] "
    "NOT diabetic macular edema[MeSH] "
    "NOT diabetic retinopathy[MeSH]"
)

# ── Layer 1: Keyword Filter ───────────────────────────────────────────────────

AMD_KEYWORDS = [
    "age-related macular degeneration",
    "macular degeneration",
    "geographic atrophy",
    "choroidal neovascularization",
    "drusen",
    "retinal pigment epithelium",
    "neovascular amd",
    "anti-vegf",
    "aflibercept",
    "ranibizumab",
    "faricimab",
    "brolucizumab",
    "bevacizumab",
    "photodynamic therapy",
    "subretinal fluid",
    "bruch's membrane",
    "complement factor",
    "macula",
    "namd",
    "nvAMD",
    "wet amd",
    "dry amd",
]

# If any of these appear as the PRIMARY topic, it's likely off-topic
EXCLUSION_SIGNALS = [
    "acid mine drainage",
    "amiodarone",
    "anterior maxillary distraction",
    "anterior mandibular",
    "alveolar macrophage",
    "diabetic macular edema",
    "diabetic retinopathy",
    "retinal vein occlusion",
    "traumatic brain injury",
    "prostate cancer",
    "neonatal",
    "orthodonti",
]


def normalize_text(text: str) -> str:
    """Normalize Unicode hyphens/dashes to ASCII hyphen so keyword matching works."""
    for ch in "\u2010\u2011\u2012\u2013\u2014\u2015\u2212":  # ‐‑‒–—―−
        text = text.replace(ch, "-")
    return text


def keyword_filter(entry: dict) -> tuple[bool, str]:
    """
    Layer 1: fast keyword check.
    Returns (passes: bool, reason: str).
    """
    text = normalize_text(
        (entry["title"] + " " + entry["abstract"] + " " + entry.get("keywords", "")).lower()
    )

    for excl in EXCLUSION_SIGNALS:
        if excl in text and "age-related macular degeneration" not in text:
            return False, f"exclusion signal matched: '{excl}'"

    for kw in AMD_KEYWORDS:
        if kw in text:
            return True, f"keyword matched: '{kw}'"

    return False, "no AMD keywords found"


# ── Layer 2: LLM Validation Agent (Google ADK + Ollama) ──────────────────────

def build_validation_agent():
    """Build the Google ADK LLM agent backed by Ollama via LiteLLM."""
    import litellm
    from google.adk.agents import LlmAgent

    litellm.api_base = OLLAMA_URL

    agent = LlmAgent(
        name="amd_literature_validator",
        model=OLLAMA_MODEL,
        instruction="""You are a medical literature validation expert specializing in
Age-Related Macular Degeneration (AMD). Your job is to classify research abstracts.

Given a title and abstract, respond with EXACTLY one of these three labels followed
by a single sentence explanation:

RELEVANT   — The abstract is primarily about AMD (age-related macular degeneration),
             its subtypes (neovascular AMD, dry AMD, geographic atrophy), treatments
             (anti-VEGF, PDT), biomarkers, genetics, imaging, or pathophysiology.

BORDERLINE — The abstract mentions AMD but is primarily about a different condition
             (e.g. diabetic macular edema, RVO, other retinal diseases), or AMD is
             only mentioned in passing in a broader review.

IRRELEVANT — The abstract is not about AMD. The term "AMD" refers to something else
             (a drug abbreviation, a statistical term, an engineering concept, etc.)
             or the paper has no meaningful AMD content.

Format your response exactly like this example:
RELEVANT: This study directly investigates anti-VEGF treatment outcomes in neovascular AMD patients.""",
    )
    return agent


async def llm_validate(agent, entry: dict, semaphore: asyncio.Semaphore) -> tuple[dict, str, str]:
    """
    Layer 2: ask the LLM agent to classify one abstract.
    Returns (entry, label, reason). Semaphore limits concurrent Ollama calls.
    """
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types

    prompt = f"Title: {entry['title']}\n\nAbstract: {entry['abstract'][:2000]}"

    async with semaphore:
        session_service = InMemorySessionService()
        await session_service.create_session(
            app_name="amd_validator", user_id="pipeline", session_id=entry["pmid"]
        )
        runner = Runner(
            agent=agent,
            app_name="amd_validator",
            session_service=session_service,
        )

        response_text = ""
        async for event in runner.run_async(
            user_id="pipeline",
            session_id=entry["pmid"],
            new_message=types.Content(role="user", parts=[types.Part(text=prompt)]),
        ):
            if event.is_final_response() and event.content and event.content.parts:
                response_text = event.content.parts[0].text.strip()
                break

    for label in ("RELEVANT", "BORDERLINE", "IRRELEVANT"):
        if response_text.upper().startswith(label):
            reason = response_text[len(label):].lstrip(": ").strip()
            return entry, label, reason

    return entry, "BORDERLINE", f"unexpected LLM response: {response_text[:100]}"


async def llm_validate_all(agent, entries: list[dict], concurrency: int = 3) -> list[tuple[dict, str, str]]:
    """Run LLM validation on all entries in parallel, limited to `concurrency` at a time."""
    semaphore = asyncio.Semaphore(concurrency)
    tasks = [llm_validate(agent, entry, semaphore) for entry in entries]
    results = []
    for i, coro in enumerate(asyncio.as_completed(tasks), 1):
        entry, label, reason = await coro
        symbol = {"RELEVANT": "✓", "BORDERLINE": "?", "IRRELEVANT": "✗"}.get(label, "?")
        print(f"  [{i}/{len(entries)}] {symbol} [{label}] {entry['title'][:55]}...")
        print(f"    {reason}")
        results.append((entry, label, reason))
    return results


# ── PubMed Helpers ────────────────────────────────────────────────────────────

def load_processed_ids() -> set:
    if PROCESSED_IDS.exists():
        with open(PROCESSED_IDS) as f:
            return set(json.load(f))
    return set()


def save_processed_ids(ids: set) -> None:
    PROCESSED_IDS.parent.mkdir(parents=True, exist_ok=True)
    with open(PROCESSED_IDS, "w") as f:
        json.dump(sorted(ids), f, indent=2)


def search_pubmed(query: str, retmax: int) -> list[str]:
    handle = Entrez.esearch(db="pubmed", term=query, retmax=retmax)
    record = Entrez.read(handle)
    handle.close()
    return record["IdList"]


def fetch_abstracts_xml(pmids: list[str]) -> list[dict]:
    if not pmids:
        return []

    time.sleep(0.4)  # NCBI rate limit

    handle = Entrez.efetch(
        db="pubmed", id=",".join(pmids), rettype="xml", retmode="xml"
    )
    records = Entrez.read(handle)
    handle.close()

    results = []
    for article in records["PubmedArticle"]:
        medline = article["MedlineCitation"]
        pmid    = str(medline["PMID"])
        art     = medline["Article"]
        title   = str(art.get("ArticleTitle", "")).strip()

        abstract_obj   = art.get("Abstract", {})
        abstract_texts = abstract_obj.get("AbstractText", [])
        if isinstance(abstract_texts, list):
            parts = []
            for part in abstract_texts:
                label = getattr(part, "attributes", {}).get("Label", "")
                text  = str(part).strip()
                parts.append(f"{label}: {text}" if label else text)
            abstract = "\n".join(parts)
        else:
            abstract = str(abstract_texts).strip()

        author_list = art.get("AuthorList", [])
        authors = [
            f"{a.get('LastName', '')} {a.get('ForeName', '')}".strip()
            for a in author_list
        ]

        journal  = str(art["Journal"]["Title"])
        pub_date = art["Journal"]["JournalIssue"]["PubDate"]
        year     = str(pub_date.get("Year", pub_date.get("MedlineDate", "Unknown")))

        # Also grab PubMed keywords — used by keyword_filter, not saved to file
        keyword_list = medline.get("KeywordList", [])
        pubmed_keywords = " ".join(str(kw) for kw in keyword_list[0]) if keyword_list else ""

        results.append({
            "pmid": pmid, "title": title, "abstract": abstract,
            "authors": authors, "journal": journal, "year": year,
            "keywords": pubmed_keywords,
        })

    return results


def save_abstract(entry: dict) -> Path:
    ABSTRACTS_DIR.mkdir(parents=True, exist_ok=True)
    filename = ABSTRACTS_DIR / f"abstract_PMID{entry['pmid']}.txt"

    authors_str = ", ".join(entry["authors"][:5])
    if len(entry["authors"]) > 5:
        authors_str += " et al."

    content = (
        f"{entry['title']}\n\n"
        f"Authors: {authors_str}\n"
        f"Journal: {entry['journal']} ({entry['year']})\n"
        f"PMID: {entry['pmid']}\n\n"
        f"{entry['abstract']}\n"
    )
    filename.write_text(content, encoding="utf-8")
    return filename


# ── Main Pipeline ─────────────────────────────────────────────────────────────

async def run_async(days: int, retmax: int, query_override: str | None, use_llm: bool) -> list[Path]:
    # 1. Build query with date filter
    end_date   = datetime.now()
    start_date = end_date - timedelta(days=days)
    date_filter = (
        f"{start_date.strftime('%Y/%m/%d')}:"
        f"{end_date.strftime('%Y/%m/%d')}[pdat]"
    )
    base_query = query_override or DEFAULT_QUERY
    full_query = f"({base_query}) AND {date_filter}"

    print(f"\nQuery: {full_query}")
    print(f"Searching PubMed (max {retmax} results)...")

    # 2. Search + deduplicate
    all_ids   = search_pubmed(full_query, retmax)
    processed = load_processed_ids()
    new_ids   = [pid for pid in all_ids if pid not in processed]
    print(f"PubMed: {len(all_ids)} found | {len(new_ids)} new (not yet processed)")

    if not new_ids:
        print("Nothing to do — ontology is up to date for this time window.")
        return []

    # 3. HITL: confirm before downloading
    answer = input(f"\nDownload {len(new_ids)} abstract(s) for validation? [Y/n/q] ").strip().lower()
    if answer in ("n", "q"):
        print("Aborted.")
        return []

    # 4. Fetch full abstracts from PubMed
    print("\nFetching abstracts from PubMed...")
    entries = fetch_abstracts_xml(new_ids)

    # 5. Layer 1 — Keyword filter
    print("\n── Layer 1: Keyword Filter ──────────────────────────────")
    passed_kw, failed_kw = [], []
    for entry in entries:
        if not entry["abstract"]:
            failed_kw.append((entry, "no abstract text"))
            continue
        ok, reason = keyword_filter(entry)
        if ok:
            passed_kw.append(entry)
        else:
            failed_kw.append((entry, reason))
            print(f"  SKIP [{entry['pmid']}] {entry['title'][:60]}...")
            print(f"       Reason: {reason}")

    print(f"\nKeyword filter: {len(passed_kw)} passed, {len(failed_kw)} rejected")

    # 6. Layer 2 — LLM validation agent
    relevant, borderline, irrelevant = [], [], []

    if use_llm and passed_kw:
        print("\n── Layer 2: LLM Validation Agent (Ollama, 3 parallel) ───")
        print(f"  Validating {len(passed_kw)} abstract(s) with {OLLAMA_MODEL}...")
        print(f"  Estimated time: ~{len(passed_kw) * 12 // 3 // 60} min {len(passed_kw) * 12 // 3 % 60} sec\n")
        agent = build_validation_agent()

        results = await llm_validate_all(agent, passed_kw, concurrency=3)
        for entry, label, reason in results:
            if label == "RELEVANT":
                relevant.append(entry)
            elif label == "BORDERLINE":
                borderline.append((entry, reason))
            else:
                irrelevant.append((entry, reason))
    else:
        # No LLM — treat all keyword-passed as relevant
        relevant = passed_kw
        if not use_llm:
            print("\n(LLM validation skipped — use --no-llm to suppress this message)")

    # 7. HITL: resolve borderline papers
    approved_borderline = []
    if borderline:
        print(f"\n── HITL: {len(borderline)} BORDERLINE paper(s) need your review ──")
        for entry, reason in borderline:
            print(f"\n  PMID: {entry['pmid']}")
            print(f"  Title: {entry['title']}")
            print(f"  Journal: {entry['journal']} ({entry['year']})")
            print(f"  LLM reason: {reason}")
            print(f"  Abstract preview: {entry['abstract'][:300]}...")
            decision = input("\n  Keep this abstract? [y/N] ").strip().lower()
            if decision == "y":
                approved_borderline.append(entry)
                print("  → Kept.")
            else:
                print("  → Discarded.")

    # 8. Save confirmed abstracts
    to_save = relevant + approved_borderline
    print(f"\n── Saving {len(to_save)} abstract(s) ────────────────────────")
    saved = []
    for entry in to_save:
        path = save_abstract(entry)
        saved.append(path)
        print(f"  Saved: {path.name}")

    # 9. Mark all fetched IDs as processed
    processed.update(new_ids)
    save_processed_ids(processed)

    # 10. Summary
    print(f"""
── Summary ─────────────────────────────────────────────
  PubMed results   : {len(all_ids)}
  New (unprocessed): {len(new_ids)}
  Keyword rejected : {len(failed_kw)}
  LLM irrelevant   : {len(irrelevant)}
  LLM borderline   : {len(borderline)} ({len(approved_borderline)} kept)
  Saved to disk    : {len(saved)}
  Location         : {ABSTRACTS_DIR}
────────────────────────────────────────────────────────
You can now run run_schema_miner_amd.py.
""")
    return saved


def run(days: int, retmax: int, query_override: str | None, use_llm: bool) -> list[Path]:
    return asyncio.run(run_async(days, retmax, query_override, use_llm))


def main():
    parser = argparse.ArgumentParser(description="Agent 0 — AMD Literature Discovery")
    parser.add_argument("--days",   type=int, default=30,
                        help="Fetch abstracts published in the last N days (default: 30)")
    parser.add_argument("--max",    type=int, default=50,
                        help="Maximum number of PubMed results (default: 50)")
    parser.add_argument("--query",  type=str, default=None,
                        help="Override the default PubMed query")
    parser.add_argument("--no-llm", action="store_true",
                        help="Skip Layer 2 LLM validation (faster, less accurate)")
    args = parser.parse_args()

    run(
        days=args.days,
        retmax=args.max,
        query_override=args.query,
        use_llm=not args.no_llm,
    )


if __name__ == "__main__":
    main()
