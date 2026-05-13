import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

from rdflib import Graph
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool
from langchain.agents import create_tool_calling_agent, AgentExecutor

PROJECT_ROOT = Path(__file__).parent.parent.parent
DEFAULT_QUESTIONS = PROJECT_ROOT / "evaluation" / "questions" / "Question category general question.txt"
DEFAULT_ONTOLOGY = PROJECT_ROOT / "ontology" / "AMD_final_clean.owl"
DEFAULT_OUTPUT = PROJECT_ROOT / "evaluation" / "sparql" / "results.json"

GRAPH: Graph = Graph()
LAST_QUERY: str = ""
LAST_RAW_RESULTS: list = []

PREFIXES = """
PREFIX : <http://example.org/amd#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX owl: <http://www.w3.org/2002/07/owl#>
"""


def schema_summary(g: Graph) -> str:
    from rdflib import OWL, RDF, RDFS
    classes = sorted({str(s).split("#")[-1] for s in g.subjects(RDF.type, OWL.Class)})
    props = sorted({str(s).split("#")[-1] for s in g.subjects(RDF.type, OWL.ObjectProperty)})
    individuals = sorted({str(s).split("#")[-1] for s in g.subjects(RDF.type, OWL.NamedIndividual)})

    return (
        f"Classes ({len(classes)}): {', '.join(classes)}\n\n"
        f"Object Properties ({len(props)}): {', '.join(props)}\n\n"
        f"Individuals ({len(individuals)}): {', '.join(individuals)}"
    )


@tool
def run_sparql(query: str) -> str:
    """Execute a SPARQL SELECT query against the AMD ontology. Standard prefixes (:, rdf, rdfs, owl) are added automatically. Returns matching rows or an error message."""
    global LAST_QUERY, LAST_RAW_RESULTS
    LAST_QUERY = query

    full_query = PREFIXES + "\n" + query
    try:
        results = list(GRAPH.query(full_query))
    except Exception as e:
        LAST_RAW_RESULTS = []
        return f"SPARQL_ERROR: {e}"

    rows_clean = []
    for row in results:
        rows_clean.append([
            str(v).split("#")[-1] if v else None for v in row
        ])
    LAST_RAW_RESULTS = rows_clean

    if not results:
        return "EMPTY_RESULT (no rows matched)"

    rows = []
    for row in results[:30]:
        rows.append(" | ".join(
            str(v).split("#")[-1] if v else "(null)" for v in row
        ))
    summary = "\n".join(rows)
    if len(results) > 30:
        summary += f"\n... ({len(results) - 30} more rows)"
    return f"{len(results)} row(s):\n{summary}"


def parse_questions(path: Path) -> list[dict]:
    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines()

    questions = []
    current_category = "uncategorized"
    buf: list[str] = []
    current_id: int | None = None

    def flush():
        nonlocal buf, current_id
        if current_id is not None and buf:
            text = " ".join(s.strip() for s in buf).strip()
            questions.append({
                "id": current_id,
                "category": current_category,
                "question": text,
            })
        buf = []
        current_id = None

    for line in lines:
        line = line.rstrip()
        if not line:
            continue
        cat_match = re.match(r"Question category[:\s]+(.+?):\s*$", line, re.IGNORECASE)
        if cat_match:
            flush()
            current_category = cat_match.group(1).strip().lower()
            continue
        num_match = re.match(r"^(\d+)\.\s+(.*)$", line)
        if num_match:
            flush()
            current_id = int(num_match.group(1))
            buf = [num_match.group(2)]
            continue
        if re.match(r"^Diagnostics\s+\d+", line):
            continue
        if current_id is not None:
            buf.append(line)
    flush()
    return questions


SYSTEM_TEMPLATE = """You convert natural-language questions about Age-Related Macular Degeneration into SPARQL queries against an OWL ontology.

The ontology uses prefix `:` for all entities (e.g., `:AMD`, `:Ranibizumab`, `:treats`).
Standard prefixes (rdf, rdfs, owl) are auto-added — do NOT include PREFIX declarations.

ONTOLOGY SCHEMA:
{schema}

INSTRUCTIONS:
1. Read the question and identify ALL medical concepts mentioned (diseases, treatments, biomarkers, diagnostic methods, risk factors, symptoms, genes).
2. ALWAYS attempt at least ONE SPARQL query before considering OUT_OF_SCOPE — even partial answers are valuable.
3. For each medical concept, query the ontology:
   - "What treats X?" → `?t :treats :X`
   - "What causes/risks for X?" → `?rf :causesOrIncreases :X`
   - "How diagnose X?" → `:X :diagnosedBy ?dm`
   - "What symptoms?" → `:X :hasSymptom ?o`
   - "What inhibits X?" → `?t :inhibits :X`
   - "What's associated with X?" → `?b :associatedWith :X`
   - "What is X?" → `:X rdfs:comment ?c` OR `:X rdf:type ?t`
4. If first query returns empty, REFINE: try alternate predicates, broader concepts, or UNION queries. Max 4 attempts.
5. Return verdict:
   - "ANSWERED" if SPARQL returned medical facts relevant to the question (even if partial).
   - "PARTIAL" if SPARQL returned data but it doesn't fully answer the question.
   - "OUT_OF_SCOPE" only if the question is purely conversational/lifestyle/quantitative (e.g., "should I worry", "% risk", "how often", appointment frequency, costs) AND no SPARQL angle works.
6. Be aggressive — favor ANSWERED/PARTIAL over OUT_OF_SCOPE when ANY SPARQL data is relevant.

NOTES:
- Mapping common medical terms to ontology entities:
  - "wet AMD" / "neovascular AMD" / "nAMD" → :WetAMD
  - "dry AMD" / "GA" / "geographic atrophy" → :DryAMD or :GeographicAtrophy
  - "anti-VEGF" → :AntiVEGFTherapy
  - "AREDS supplement" / "lutein" / "zeaxanthin" → instances of :Treatment or :Biomarker
- Use UNION when patient mentions a generic concept that maps to multiple ontology entities.
- For "what is X", query rdfs:comment if it exists, else type info.
- For "what treats X", `?t :treats :X` then return ?t.
- For "what causes X", `?rf :causesOrIncreases :X` then return ?rf.

When you finish, format your final response as:
VERDICT: ANSWERED | PARTIAL | OUT_OF_SCOPE
SPARQL: <query you ran, or "N/A">
ANSWER: <2-3 sentence summary>
"""


def build_executor(provider: str, model: str, schema: str):
    if provider == "groq":
        from langchain_groq import ChatGroq
        from dotenv import load_dotenv
        load_dotenv()
        llm = ChatGroq(model=model, api_key=os.getenv("GROQ_API_KEY"),
                        temperature=0)
    else:
        from langchain_ollama import ChatOllama
        llm = ChatOllama(model=model, temperature=0,
                          base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))

    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_TEMPLATE.format(schema=schema)),
        ("human", "Question: {question}"),
        ("placeholder", "{agent_scratchpad}"),
    ])
    agent = create_tool_calling_agent(llm, [run_sparql], prompt)
    return AgentExecutor(agent=agent, tools=[run_sparql], verbose=False,
                          handle_parsing_errors=True, max_iterations=4,
                          max_execution_time=120)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--questions", default=str(DEFAULT_QUESTIONS))
    p.add_argument("--ontology", default=str(DEFAULT_ONTOLOGY))
    p.add_argument("--output", default=str(DEFAULT_OUTPUT))
    p.add_argument("--provider", default="groq",
                    choices=["groq", "ollama"])
    p.add_argument("--model", default="llama-3.3-70b-versatile")
    p.add_argument("--limit", type=int, default=None,
                    help="Process only first N questions (for testing)")
    p.add_argument("--sleep", type=float, default=2.0,
                    help="Sleep between agent calls (Groq rate limits)")
    args = p.parse_args()

    print(f"Loading ontology from {args.ontology}")
    GRAPH.parse(args.ontology, format="xml")
    schema = schema_summary(GRAPH)
    print(f"Schema: {schema[:200]}...")

    questions = parse_questions(Path(args.questions))
    print(f"Parsed {len(questions)} questions")
    if args.limit:
        questions = questions[:args.limit]
        print(f"Limited to first {args.limit}")

    executor = build_executor(args.provider, args.model, schema)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    results = []

    for i, q in enumerate(questions, 1):
        print(f"\n[{i}/{len(questions)}] Q{q['id']} ({q['category']})")
        print(f"  Q: {q['question'][:120]}...")
        global LAST_QUERY, LAST_RAW_RESULTS
        LAST_QUERY = ""
        LAST_RAW_RESULTS = []
        try:
            r = executor.invoke({"question": q["question"]})
            output = r.get("output", "")
        except Exception as e:
            output = f"AGENT_ERROR: {e}"

        if "AGENT_ERROR" in output:
            verdict = "AGENT_ERROR"
        elif LAST_RAW_RESULTS:
            verdict = "ANSWERED"
        else:
            verdict = "OUT_OF_SCOPE"

        results.append({
            "id":          q["id"],
            "category":    q["category"],
            "question":    q["question"],
            "verdict":     verdict,
            "sparql":      LAST_QUERY,
            "raw_results": LAST_RAW_RESULTS,
            "output":      output[:1500],
        })
        print(f"  → {verdict}")
        if args.sleep:
            time.sleep(args.sleep)

        if i % 10 == 0:
            out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False),
                                 encoding="utf-8")
            print(f"  [saved checkpoint to {out_path}]")

    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False),
                         encoding="utf-8")

    answered = sum(1 for r in results if r["verdict"] == "ANSWERED")
    out_of_scope = sum(1 for r in results if r["verdict"] == "OUT_OF_SCOPE")
    errors = sum(1 for r in results if r["verdict"] == "AGENT_ERROR")
    print(f"\n=== SUMMARY ===")
    print(f"  Total:        {len(results)}")
    print(f"  Answered:     {answered} ({answered / len(results):.0%})  — SPARQL returned data from ontology")
    print(f"  Out of scope: {out_of_scope} ({out_of_scope / len(results):.0%}) — SPARQL returned nothing")
    print(f"  Errors:       {errors}")
    print(f"  Saved to:     {out_path}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
