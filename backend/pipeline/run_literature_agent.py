import argparse
import json
import os
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import requests
from dotenv import load_dotenv
from langchain_ollama import ChatOllama
from langchain_groq import ChatGroq
from langchain_core.tools import tool
from langchain.agents import create_react_agent, AgentExecutor

from pipeline.prompts.literature import PROMPT as AGENT_PROMPT
from schema_miner.config.envConfig import EnvConfig

PROJECT_ROOT = Path(__file__).parent.parent.parent
ABSTRACTS_DIR = PROJECT_ROOT / "data" / "stage-2" / "AMD" / "new-literature"
PROCESSED_FILE = PROJECT_ROOT / "data" / "stage-2" / "AMD" / "processed_pmids.json"


NCBI_ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
NCBI_EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

load_dotenv(PROJECT_ROOT / ".env")
NCBI_EMAIL = os.getenv("NCBI_EMAIL", "your.email@example.com")

PROPOSED_ABSTRACTS = []
SEARCH_DAYS: int = 0

ABSTRACT_CACHE: dict[str, dict[str, str]] = {}


def _load_processed_pmids() -> set[str]:
    """PMIDs already saved in earlier runs (used to skip duplicates at search time)."""
    if PROCESSED_FILE.exists():
        return set(json.loads(PROCESSED_FILE.read_text()))
    return set()


def _all_seen_pmids() -> set[str]:
    """All PMIDs the agent should skip: persisted-on-disk + already-fetched
    in this session + already-proposed in this session."""
    return (
        _load_processed_pmids()
        | set(ABSTRACT_CACHE.keys())
        | {p["pmid"] for p in PROPOSED_ABSTRACTS}
    )


@tool
def search_pubmed(query: str) -> str:
    """Search PubMed with a plain keyword query. """
    try:
        resp = requests.get(
            NCBI_ESEARCH,
            params={
                "db": "pubmed",
                "term": query,
                "reldate": SEARCH_DAYS,
                "datetype": "pdat",
                "retmode": "json",
                "retmax": 10,
                "email": NCBI_EMAIL,
            },
            timeout=15,
        )
        resp.raise_for_status()
        result = resp.json().get("esearchresult", {})
        ids = result.get("idlist", [])
        count = result.get("count", "0")

        if not ids:
            return f"No results found for: {query}"

        seen = _all_seen_pmids()
        new_ids = [p for p in ids if p not in seen]
        skipped = len(ids) - len(new_ids)

        if not new_ids:
            return f"No new results for '{query}': all {len(ids)} top PMIDs were already processed."

        msg = f"{count} total results, {len(new_ids)} new: {', '.join(new_ids)}"
        if skipped:
            msg += f" ({skipped} already processed)"
        return msg

    except Exception as e:
        return f"PubMed search error: {e}"


@tool
def fetch_abstract(pmid: str) -> str:
    """Fetch the full abstract text for a PubMed ID (PMID)."""
    pmid = pmid.strip()
    try:
        resp = requests.get(
            NCBI_EFETCH,
            params={
                "db": "pubmed",
                "id": pmid,
                "rettype": "xml",
                "retmode": "xml",
                "email": NCBI_EMAIL,
            },
            timeout=15,
        )
        resp.raise_for_status()

        root = ET.fromstring(resp.text)
        article = root.find(".//PubmedArticle")
        if article is None:
            return f"PMID {pmid}: Article not found"

        title_el = article.find(".//ArticleTitle")
        title = title_el.text if title_el is not None and title_el.text else "No title"

        abstract_parts = []
        for abs_text in article.findall(".//AbstractText"):
            label = abs_text.get("Label", "")
            text = abs_text.text or ""
            if label:
                abstract_parts.append(f"{label}: {text}")
            else:
                abstract_parts.append(text)

        abstract = " ".join(abstract_parts) if abstract_parts else "No abstract available"

        ABSTRACT_CACHE[pmid] = {"title": title, "text": abstract}

        return f"PMID: {pmid}\nTitle: {title}\nAbstract: {abstract[:1500]}"

    except Exception as e:
        return f"Fetch error for PMID {pmid}: {e}"



@tool
def propose_abstract(proposal_json: str) -> str:
    """Propose an abstract for human review."""
    try:
        proposal = json.loads(proposal_json)
    except json.JSONDecodeError:
        return ("REJECTED: proposal must be valid JSON with pmid, relevance, "
                "reason. Title and abstract_text are added automatically — "
                "do not include them.")

    pmid = str(proposal.get("pmid", "")).strip()
    if not pmid:
        return "REJECTED: missing pmid."
    if pmid not in ABSTRACT_CACHE:
        return (f"REJECTED: PMID {pmid} not in cache. Call fetch_abstract "
                f"for this PMID before proposing it.")

    cached = ABSTRACT_CACHE[pmid]
    record = {
        "pmid": pmid,
        "title": cached["title"],
        "abstract_text": cached["text"],
        "relevance": str(proposal.get("relevance", "unknown")).strip().upper(),
        "reason": str(proposal.get("reason", "")).strip(),
    }
    PROPOSED_ABSTRACTS.append(record)
    return f"Abstract PMID {pmid} recorded for human review."




def present_proposals_to_human(proposals: list[dict]):
    """Present proposed abstracts for human approval."""
    if not proposals:
        print("\n  No abstracts proposed.")
        return

    print(f"\n{'='*60}")
    print(f"  Agent proposed {len(proposals)} abstracts — review each:")
    print(f"{'='*60}")

    ABSTRACTS_DIR.mkdir(parents=True, exist_ok=True)
    processed = _load_processed_pmids()
    accepted = 0
    for i, prop in enumerate(proposals, 1):
        pmid = str(prop.get("pmid", "")).strip()
        print(f"\n── Abstract {i}/{len(proposals)} ──")
        print(f"  PMID      : {pmid or '?'}")
        print(f"  Title     : {prop.get('title', '?')[:100]}")
        print(f"  Relevance : {prop.get('relevance', '?')}")
        print(f"  Reason    : {prop.get('reason', '?')}")

        choice = input("  Accept for pipeline? [y/n/skip]: ").strip().lower()
        if choice != "y":
            print("  Skipped")
            continue

        text = prop.get("abstract_text")
        if not text or not pmid:
            print("  Cannot save — missing pmid or abstract_text in proposal.")
            continue
        filepath = ABSTRACTS_DIR / f"abstract_PMID{pmid}.txt"
        filepath.write_text(text, encoding="utf-8")
        processed.add(pmid)
        accepted += 1
        print(f"  Saved to {filepath.name}")

    PROCESSED_FILE.write_text(json.dumps(sorted(processed), indent=2))
    print(f"\n  {accepted}/{len(proposals)} abstracts saved to {ABSTRACTS_DIR}")


def run(model: str, provider: str, days: int):
    global SEARCH_DAYS, PROPOSED_ABSTRACTS
    SEARCH_DAYS = days
    PROPOSED_ABSTRACTS = []

    print(f"\nLiterature Discovery Agent")
    print(f"  Model    : {model}")
    print(f"  Provider : {provider}")
    print(f"  Period   : last {days} days")

    if provider == "groq":
        from dotenv import load_dotenv
        load_dotenv()
        llm = ChatGroq(model=model, api_key=os.getenv("GROQ_API_KEY"), temperature=0)
    else:
        llm = ChatOllama(model=model, base_url=EnvConfig.OLLAMA_base_url, temperature=0)

    tools = [
        search_pubmed,
        fetch_abstract,
        propose_abstract,
    ]

    agent = create_react_agent(llm, tools, AGENT_PROMPT)
    agent_executor = AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=True,
        handle_parsing_errors=True,
        max_iterations=60,
        max_execution_time=600,
    )

    if provider == "groq":
        from langchain.callbacks.base import BaseCallbackHandler

        class RateLimitHandler(BaseCallbackHandler):
            def on_agent_action(self, action, **kwargs):
                time.sleep(5)

        agent_executor.callbacks = [RateLimitHandler()]

    print(f"\n{'='*60}")
    print("  Starting Literature Discovery Agent")
    print(f"{'='*60}\n")

    try:
        result = agent_executor.invoke({
            "input": f"Run the workflow with a {days}-day search window."
        })

        print(f"\n{'='*60}")
        print("  Agent Summary:")
        print(f"{'='*60}")
        print(f"  {result.get('output', 'No output')}")
    except Exception as e:
        print(f"\n  Agent error: {e}")
        print("  Continuing with collected proposals...")

    print(f"\n{'='*60}")
    print("  Human Review (HITL)")
    print(f"{'='*60}")

    present_proposals_to_human(PROPOSED_ABSTRACTS)

    print(f"\n{'='*60}")
    print(f"  Literature discovery complete — {len(PROPOSED_ABSTRACTS)} abstracts proposed")
    print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description="Agentic Literature Discovery — LangChain ReAct Agent")
    parser.add_argument("--model", default="llama3.1:8b",
                        help="Model name (default: llama3.1:8b)")
    parser.add_argument("--provider", default="ollama", choices=["ollama", "groq"],
                        help="LLM provider: ollama (local) or groq (cloud)")
    parser.add_argument("--days", type=int, default=90,
                        help="Search period in days (default: 90)")
    args = parser.parse_args()
    run(args.model, args.provider, args.days)


if __name__ == "__main__":
    main()
