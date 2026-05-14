"""
AMD Ontology API — FastAPI backend.

Run from project root:
    uvicorn backend.api.main:app --reload --port 8000

Docs:
    http://localhost:8000/docs
"""
import json
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


PROJECT_ROOT = Path(__file__).parent.parent.parent
ONTOLOGY_PATH = PROJECT_ROOT / "results" / "amd" / "final" / "amd_ontology_final.json"

sys.path.insert(0, str(PROJECT_ROOT / "backend"))
from pipeline.run_schema_miner_agentic import (
    process_single_abstract,
    run_full_pipeline,
)
from pipeline.run_validate_ontology_agent import (
    collect_proposed_fixes,
    apply_single_fix,
    set_log_callback as set_val_log_callback,
)
from pipeline.run_literature_agent import discover_abstracts, set_log_callback as set_lit_log_callback
from pipeline.run_dllearner import list_experiments, run_experiment

from .jobs import manager, Job


app = FastAPI(
    title="AMD Ontology API",
    description="Backend for the AMD ontology engineering tool — extraction, validation, browsing.",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Schemas ──────────────────────────────────────────────────────────────────

class Entity(BaseModel):
    id: str
    label: str
    type: str


class Relation(BaseModel):
    subject: str
    predicate: str
    object: str


class ExtractRequest(BaseModel):
    abstract: str = Field(..., min_length=50)
    model: str = Field(default="qwen2.5:32b")
    provider: str = Field(default="ollama")


class ExtractResponse(BaseModel):
    entities: list[Entity]
    relations: list[Relation]
    rejected: list[str] = Field(default_factory=list,
                                  description="Reasons why the LLM-proposed entities/triples were filtered out")
    raw_llm_output: str | None = None


class RunRequest(BaseModel):
    model: str = Field(default="qwen2.5:32b")
    provider: str = Field(default="ollama")
    stages: list[int] = Field(default=[1, 2, 3])
    max_abstracts: int | None = Field(default=None,
                                       description="Cap per stage; null = no cap")
    use_current_ontology: bool = Field(default=False,
                                        description="If true, resume from current AMD_final ontology")


class RunResponse(BaseModel):
    job_id: str
    status: str


class ValidateRequest(BaseModel):
    model: str = Field(default="llama-3.3-70b-versatile")
    provider: str = Field(default="groq")
    max_passes: int = Field(default=3)


class FixDecision(BaseModel):
    action: str = Field(..., description="approve | reject")


class ManualEntity(BaseModel):
    name: str = Field(..., min_length=1)
    type: str = Field(..., description="Pipeline class, e.g. Treatment, Biomarker")


class ManualTriple(BaseModel):
    subject: str
    predicate: str
    object: str


class BatchAddRequest(BaseModel):
    instances: list[ManualEntity] = Field(default_factory=list)
    triples: list[ManualTriple] = Field(default_factory=list)


class BatchAddResponse(BaseModel):
    instances_added: list[str]
    instances_skipped: list[str]
    triples_added: list[str]
    triples_skipped: list[str]
    errors: list[str]


class LiteratureFetchRequest(BaseModel):
    days: int = Field(default=30, ge=1, le=3650)
    model: str = Field(default="llama-3.3-70b-versatile")
    provider: str = Field(default="groq")


class LiteratureApproveRequest(BaseModel):
    proposals: list[dict] = Field(...,
        description="full proposal list returned by /api/literature/{id}/result")
    pmids_to_keep: list[str] = Field(...,
        description="subset of PMIDs the user has ticked for processing")


class LiteratureProcessRequest(BaseModel):
    pmids: list[str] = Field(..., description="PMIDs to process through Stage 3")
    model: str = Field(default="llama-3.3-70b-versatile")
    provider: str = Field(default="groq")
    use_current_ontology: bool = Field(default=True)


class DLLearnerRunRequest(BaseModel):
    experiment: str = Field(..., description="experiment name (e.g. experiment6_vegf_inhibitors)")
    owl_path: str | None = Field(default=None,
                                   description="optional OWL path; defaults to ontology/AMD_final_clean.owl")


class ModelInfo(BaseModel):
    id: str
    name: str
    provider: str
    description: str


# ── Helpers ──────────────────────────────────────────────────────────────────

def _load_current_ontology() -> dict:
    if not ONTOLOGY_PATH.exists():
        return {"classes": {}, "properties": {}, "disjoint_groups": []}
    return json.loads(ONTOLOGY_PATH.read_text(encoding="utf-8"))


SNAPSHOTS_DIR = PROJECT_ROOT / "results" / "amd" / "snapshots"


def _ontology_stats(data: dict) -> dict:
    classes = data.get("classes", {})
    n_classes = len(classes)
    n_instances = sum(
        len(c.get("instances", []))
        for c in classes.values() if isinstance(c, dict)
    )
    n_triples = sum(
        len(p.get("examples", []))
        for p in data.get("properties", {}).values() if isinstance(p, dict)
    )
    return {"classes": n_classes, "instances": n_instances, "triples": n_triples}


def _snapshot_current_ontology(label: str = "") -> dict:
    from datetime import datetime
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    if not ONTOLOGY_PATH.exists():
        return {}
    current_text = ONTOLOGY_PATH.read_text(encoding="utf-8")
    existing = sorted(SNAPSHOTS_DIR.glob("snapshot_*.json"), reverse=True)
    if existing:
        try:
            if existing[0].read_text(encoding="utf-8") == current_text:
                s = existing[0]
                return {"name": s.name, "skipped": True}
        except Exception:
            pass
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    label_part = f"_{label.replace(' ', '-')}" if label else ""
    snap_name = f"snapshot_{ts}{label_part}.json"
    snap_path = SNAPSHOTS_DIR / snap_name
    data = json.loads(current_text)
    snap_path.write_text(json.dumps(data, indent=2, ensure_ascii=False),
                          encoding="utf-8")
    stats = _ontology_stats(data)
    return {
        "name": snap_name,
        "timestamp": ts,
        "label": label,
        "size_kb": round(snap_path.stat().st_size / 1024, 1),
        **stats,
    }


# ── Health / utility ─────────────────────────────────────────────────────────

@app.get("/api")
def api_root():
    return {"name": "AMD Ontology API", "version": app.version, "docs": "/docs"}


# ── Ontology snapshots ──────────────────────────────────────────────────────

class SnapshotRestoreRequest(BaseModel):
    name: str = Field(..., description="snapshot file name to restore")


@app.get("/api/ontology/snapshots")
def list_snapshots():
    """Return all saved ontology snapshots, newest first."""
    if not SNAPSHOTS_DIR.exists():
        return {"snapshots": []}
    snaps = []
    for p in sorted(SNAPSHOTS_DIR.glob("snapshot_*.json"), reverse=True):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            stats = _ontology_stats(data)
        except Exception:
            stats = {"classes": 0, "instances": 0, "triples": 0}
        snaps.append({
            "name": p.name,
            "timestamp": p.name.replace("snapshot_", "").replace(".json", ""),
            "size_kb": round(p.stat().st_size / 1024, 1),
            **stats,
        })
    return {"snapshots": snaps}


@app.post("/api/ontology/snapshots")
def create_snapshot(label: str = ""):
    """Manually create a snapshot of the current ontology."""
    return _snapshot_current_ontology(label=label)


@app.post("/api/ontology/snapshots/restore")
def restore_snapshot(req: SnapshotRestoreRequest):
    """Replace the current ontology with the given snapshot."""
    snap_path = SNAPSHOTS_DIR / req.name
    if not snap_path.exists():
        raise HTTPException(status_code=404,
                              detail=f"snapshot '{req.name}' not found")
    ONTOLOGY_PATH.parent.mkdir(parents=True, exist_ok=True)
    ONTOLOGY_PATH.write_text(snap_path.read_text(encoding="utf-8"),
                               encoding="utf-8")
    return {"restored": req.name, "to": str(ONTOLOGY_PATH)}


def _ollama_available() -> bool:
    try:
        import os, urllib.request
        base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        urllib.request.urlopen(f"{base}/api/tags", timeout=2)
        return True
    except Exception:
        return False


@app.get("/api/models", response_model=list[ModelInfo])
def list_models():
    models = [
        ModelInfo(id="llama-3.3-70b-versatile", name="Llama 3.3 70B", provider="groq",
                  description="Cloud (Groq) — highest quality, requires GROQ_API_KEY"),
        ModelInfo(id="meta-llama/llama-4-scout-17b-16e-instruct", name="Llama 4 Scout 17B",
                  provider="groq", description="Cloud (Groq) — experimental"),
    ]
    if _ollama_available():
        models += [
            ModelInfo(id="qwen2.5:32b", name="Qwen 2.5 32B", provider="ollama",
                      description="Local — best balance of quality and speed"),
            ModelInfo(id="llama3.1:8b", name="Llama 3.1 8B", provider="ollama",
                      description="Local — fastest, lower quality"),
        ]
    return models


@app.get("/api/ontology")
def get_ontology():
    if not ONTOLOGY_PATH.exists():
        raise HTTPException(status_code=404,
                              detail=f"Ontology not found at {ONTOLOGY_PATH}")
    return _load_current_ontology()


def _save_ontology(data: dict):
    ONTOLOGY_PATH.parent.mkdir(parents=True, exist_ok=True)
    ONTOLOGY_PATH.write_text(json.dumps(data, indent=4, ensure_ascii=False),
                               encoding="utf-8")


@app.post("/api/ontology/instances")
def add_instance(entity: ManualEntity):
    ont = _load_current_ontology()
    classes = ont.setdefault("classes", {})
    if entity.type not in classes:
        raise HTTPException(status_code=404,
                              detail=f"Class '{entity.type}' does not exist. "
                                     f"Available: {list(classes.keys())}")

    cls_info = classes[entity.type]
    if not isinstance(cls_info, dict):
        cls_info = {}
        classes[entity.type] = cls_info
    insts = cls_info.setdefault("instances", [])

    if entity.name in insts:
        return {"ok": True, "added": False,
                "message": f"'{entity.name}' already in '{entity.type}'"}

    for cls, info in classes.items():
        if isinstance(info, dict) and entity.name in info.get("instances", []):
            raise HTTPException(status_code=409,
                                  detail=f"'{entity.name}' already exists in class '{cls}'. "
                                         f"Move instead.")

    insts.append(entity.name)
    _save_ontology(ont)
    return {"ok": True, "added": True,
            "message": f"Added '{entity.name}' to '{entity.type}'"}


@app.post("/api/ontology/triples")
def add_triple(triple: ManualTriple):
    ont = _load_current_ontology()
    props = ont.setdefault("properties", {})

    if triple.predicate not in props:
        raise HTTPException(status_code=404,
                              detail=f"Predicate '{triple.predicate}' does not exist. "
                                     f"Allowed: {list(props.keys())}")

    p_info = props[triple.predicate]
    if not isinstance(p_info, dict):
        p_info = {}
        props[triple.predicate] = p_info
    examples = p_info.setdefault("examples", [])

    new_triple = [triple.subject, triple.predicate, triple.object]
    if any(list(e) == new_triple for e in examples):
        return {"ok": True, "added": False,
                "message": "Triple already exists"}

    examples.append(new_triple)
    _save_ontology(ont)
    return {"ok": True, "added": True,
            "message": f"Added triple ({triple.subject} {triple.predicate} {triple.object})"}


@app.post("/api/ontology/batch-add", response_model=BatchAddResponse)
def batch_add(req: BatchAddRequest):
    ont = _load_current_ontology()
    classes = ont.setdefault("classes", {})
    properties = ont.setdefault("properties", {})

    inst_added: list[str] = []
    inst_skipped: list[str] = []
    triple_added: list[str] = []
    triple_skipped: list[str] = []
    errors: list[str] = []

    for entity in req.instances:
        if entity.type not in classes:
            errors.append(f"class '{entity.type}' does not exist for '{entity.name}'")
            continue
        cls_info = classes[entity.type]
        if not isinstance(cls_info, dict):
            cls_info = {}
            classes[entity.type] = cls_info
        insts = cls_info.setdefault("instances", [])

        if entity.name in insts:
            inst_skipped.append(f"{entity.name} (already in {entity.type})")
            continue

        existing_class = None
        for c, info in classes.items():
            if isinstance(info, dict) and entity.name in info.get("instances", []):
                existing_class = c
                break
        if existing_class:
            inst_skipped.append(f"{entity.name} (exists in {existing_class})")
            continue

        insts.append(entity.name)
        inst_added.append(f"{entity.name} -> {entity.type}")

    for triple in req.triples:
        if triple.predicate not in properties:
            errors.append(f"predicate '{triple.predicate}' does not exist")
            continue
        p_info = properties[triple.predicate]
        if not isinstance(p_info, dict):
            p_info = {}
            properties[triple.predicate] = p_info
        examples = p_info.setdefault("examples", [])

        new_triple = [triple.subject, triple.predicate, triple.object]
        if any(list(e) == new_triple for e in examples):
            triple_skipped.append(f"{triple.subject} {triple.predicate} {triple.object}")
            continue

        examples.append(new_triple)
        triple_added.append(f"{triple.subject} {triple.predicate} {triple.object}")

    if inst_added or triple_added:
        _save_ontology(ont)

    return BatchAddResponse(
        instances_added=inst_added,
        instances_skipped=inst_skipped,
        triples_added=triple_added,
        triples_skipped=triple_skipped,
        errors=errors,
    )


@app.delete("/api/ontology/instances/{name}")
def delete_instance(name: str, cls: str | None = None):
    ont = _load_current_ontology()
    classes = ont.get("classes", {})
    removed_from = []
    for c, info in classes.items():
        if not isinstance(info, dict):
            continue
        if cls and c != cls:
            continue
        if name in info.get("instances", []):
            info["instances"] = [i for i in info["instances"] if i != name]
            removed_from.append(c)
    if not removed_from:
        raise HTTPException(status_code=404,
                              detail=f"Instance '{name}' not found")
    _save_ontology(ont)
    return {"ok": True, "removed_from": removed_from}


# ── Manual mode — extract from one abstract ──────────────────────────────────

@app.post("/api/extract/abstract", response_model=ExtractResponse)
def extract_abstract(req: ExtractRequest):
    """Run agentic extraction on a single abstract. Synchronous."""
    try:
        result = process_single_abstract(
            req.abstract,
            model=req.model,
            provider=req.provider,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Extraction failed: {e}")

    return ExtractResponse(
        entities=[Entity(**e) for e in result["entities"]],
        relations=[Relation(**r) for r in result["relations"]],
        rejected=result.get("rejected", []),
        raw_llm_output=result.get("raw_llm_output"),
    )


# ── Auto mode — full agentic pipeline (Stages 1-3) ───────────────────────────

@app.post("/api/runs", response_model=RunResponse)
def start_run(req: RunRequest):
    """Start the full agentic pipeline as a background job."""
    job = manager.create("pipeline", req.model_dump())

    def _target(j: Job):
        j.append_log(f"Starting pipeline: model={req.model} provider={req.provider} "
                      f"stages={req.stages} max_abstracts={req.max_abstracts}")

        def on_progress(stage: str, msg: str):
            j.stage = stage
            j.append_log(msg)
            stage_progress = {"stage1": 0.2, "stage2": 0.5, "stage3": 0.9}
            j.progress = stage_progress.get(stage, j.progress)

        resume = _load_current_ontology() if req.use_current_ontology else None
        result = run_full_pipeline(
            model=req.model,
            provider=req.provider,
            stages=req.stages,
            max_abstracts=req.max_abstracts,
            resume_from=resume,
            on_progress=on_progress,
        )
        j.append_log("Pipeline complete")
        return result

    manager.run(job, _target)
    return RunResponse(job_id=job.id, status=job.status)


@app.get("/api/runs/{job_id}")
def get_run_status(job_id: str):
    job = manager.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return job.to_dict()


@app.get("/api/runs/{job_id}/logs")
def get_run_logs(job_id: str, offset: int = 0):
    job = manager.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return {"lines": job.log[offset:], "next_offset": len(job.log)}


@app.get("/api/runs/{job_id}/result")
def get_run_result(job_id: str):
    job = manager.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    if job.status != "done":
        raise HTTPException(status_code=409,
                              detail=f"Job is {job.status}, no result yet")
    return {"ontology": job.result}


@app.get("/api/runs")
def list_runs():
    return [j.to_dict(include_log=False) for j in manager.list_jobs()]


# ── Validation agent — propose fixes ─────────────────────────────────────────

VALIDATION_FIXES: dict[str, list[dict]] = {}


@app.post("/api/validate", response_model=RunResponse)
def start_validation(req: ValidateRequest):
    """Run the validation agent in background. Result = list of proposed fixes."""
    ontology = _load_current_ontology()
    if not ontology.get("classes"):
        raise HTTPException(status_code=409,
                              detail="No ontology to validate. Run pipeline first.")

    job = manager.create("validation", req.model_dump())

    def _target(j: Job):
        j.append_log(f"Validation starting (model={req.model} provider={req.provider})")
        j.stage = "validation"
        set_val_log_callback(j.append_log)
        try:
            fixes = collect_proposed_fixes(
                model=req.model,
                ontology=ontology,
                provider=req.provider,
                max_passes=req.max_passes,
            )
        finally:
            set_val_log_callback(None)
        VALIDATION_FIXES[j.id] = fixes
        j.append_log(f"Found {len(fixes)} proposed fixes")
        return {"fix_count": len(fixes)}

    manager.run(job, _target)
    return RunResponse(job_id=job.id, status=job.status)


@app.get("/api/validate/{job_id}/fixes")
def get_validation_fixes(job_id: str):
    fixes = VALIDATION_FIXES.get(job_id)
    if fixes is None:
        raise HTTPException(status_code=404,
                              detail="No fixes for this job (still running, or job not found)")
    return {"fixes": fixes}


@app.post("/api/validate/{job_id}/fixes/{fix_id}/decide")
def decide_fix(job_id: str, fix_id: str, decision: FixDecision):
    fixes = VALIDATION_FIXES.get(job_id)
    if fixes is None:
        raise HTTPException(status_code=404, detail="Job not found")
    fix = next((f for f in fixes if f["id"] == fix_id), None)
    if fix is None:
        raise HTTPException(status_code=404, detail=f"Fix {fix_id} not found")

    if decision.action == "reject":
        fix["status"] = "rejected"
        return {"ok": True, "applied": False, "fix": fix}

    if decision.action == "approve":
        ontology = _load_current_ontology()
        new_ontology, ok, msg = apply_single_fix(ontology, fix)
        if not ok:
            raise HTTPException(status_code=400, detail=f"Apply failed: {msg}")
        ONTOLOGY_PATH.parent.mkdir(parents=True, exist_ok=True)
        ONTOLOGY_PATH.write_text(json.dumps(new_ontology, indent=2, ensure_ascii=False),
                                   encoding="utf-8")
        fix["status"] = "applied"
        return {"ok": True, "applied": True, "message": msg, "fix": fix}

    raise HTTPException(status_code=400,
                          detail=f"Unknown action '{decision.action}'. Use approve|reject.")


@app.post("/api/reasoner/hermit", response_model=RunResponse)
def run_hermit():
    if not ONTOLOGY_PATH.exists():
        raise HTTPException(status_code=409, detail="No ontology found.")
    job = manager.create("hermit", {})

    def _target(j: Job):
        import tempfile, os
        import owlready2
        from pipeline.convert_to_owl import json_to_owl

        j.append_log("Converting JSON ontology to OWL...")
        tmp_path = tempfile.mktemp(suffix=".owl")

        try:
            json_to_owl(str(ONTOLOGY_PATH), tmp_path)
            j.append_log("Running HermiT reasoner (owlready2)...")
            owlready2.onto_path.clear()
            onto = owlready2.get_ontology(f"file://{tmp_path}").load()
            with onto:
                owlready2.sync_reasoner_hermit(infer_property_values=True)

            inferred = []
            for cls in onto.classes():
                for parent in cls.is_a:
                    if isinstance(parent, owlready2.ThingClass) and parent is not owlready2.Thing:
                        inferred.append(f"{cls.name} subClassOf {parent.name}")

            unsatisfiable = [cls.name for cls in owlready2.default_world.inconsistent_classes()]
            j.append_log(f"HermiT done: {len(inferred)} inferred axioms, {len(unsatisfiable)} unsatisfiable")
            return {
                "consistent": len(unsatisfiable) == 0,
                "inferred_axioms": inferred,
                "unsatisfiable_classes": unsatisfiable,
            }
        except owlready2.base.OwlReadyInconsistentOntologyError:
            j.append_log("Ontology is INCONSISTENT")
            return {"consistent": False, "inferred_axioms": [], "unsatisfiable_classes": ["INCONSISTENT"]}
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

    manager.run(job, _target)
    return RunResponse(job_id=job.id, status=job.status)


@app.get("/api/reasoner/hermit/{job_id}/result")
def get_hermit_result(job_id: str):
    job = manager.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status not in ("done", "error"):
        raise HTTPException(status_code=409, detail=f"Job is {job.status}")
    return job.result or {}


@app.post("/api/literature/fetch", response_model=RunResponse)
def start_literature_fetch(req: LiteratureFetchRequest):
    job = manager.create("literature", req.model_dump())

    def _target(j: Job):
        j.append_log(f"Searching PubMed (last {req.days} days, model={req.model})")
        j.stage = "literature"
        set_lit_log_callback(j.append_log)
        try:
            result = discover_abstracts(
                model=req.model,
                provider=req.provider,
                days=req.days,
                auto_save=False,
            )
        finally:
            set_lit_log_callback(None)
        j.append_log(f"DONE — {len(result['proposals'])} proposals "
                      f"(saved to disk: {len(result['saved'])})")
        if result.get("error"):
            j.append_log(f"Agent error: {result['error']}")
        return result

    manager.run(job, _target)
    return RunResponse(job_id=job.id, status=job.status)


@app.get("/api/literature/{job_id}/result")
def get_literature_result(job_id: str):
    job = manager.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    if job.status != "done":
        raise HTTPException(status_code=409,
                              detail=f"Job is {job.status}, no result yet")
    return job.result


APPROVED_LIT_DIR = PROJECT_ROOT / "data" / "stage-3" / "AMD" / "approved-from-pubmed"
REJECTED_LIT_FILE = PROJECT_ROOT / "data" / "stage-2" / "AMD" / "rejected_literature.json"
PROCESSED_PMIDS_FILE = PROJECT_ROOT / "data" / "stage-2" / "AMD" / "processed_pmids.json"


def _load_rejected_literature() -> list[dict]:
    if REJECTED_LIT_FILE.exists():
        return json.loads(REJECTED_LIT_FILE.read_text(encoding="utf-8"))
    return []


def _save_rejected_literature(items: list[dict]) -> None:
    REJECTED_LIT_FILE.parent.mkdir(parents=True, exist_ok=True)
    REJECTED_LIT_FILE.write_text(json.dumps(items, indent=2, ensure_ascii=False),
                                   encoding="utf-8")


def _load_processed_pmids_set() -> set[str]:
    if PROCESSED_PMIDS_FILE.exists():
        return set(json.loads(PROCESSED_PMIDS_FILE.read_text(encoding="utf-8")))
    return set()


def _save_processed_pmids(pmids: set[str]) -> None:
    PROCESSED_PMIDS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROCESSED_PMIDS_FILE.write_text(json.dumps(sorted(pmids), indent=2),
                                      encoding="utf-8")


class LiteratureRestoreRequest(BaseModel):
    pmids: list[str] = Field(..., description="PMIDs to move from rejected back to approved")


from datetime import datetime, timezone


@app.post("/api/literature/approve")
def approve_literature(req: LiteratureApproveRequest):
    """Approve some PMIDs (saved to disk for processing) and reject the rest
    (kept in a separate rejected list for later review/restoration).
    Both approved and rejected PMIDs are added to processed_pmids so they
    don't reappear in future PubMed searches."""
    APPROVED_LIT_DIR.mkdir(parents=True, exist_ok=True)
    keep = set(req.pmids_to_keep)
    saved = []
    rejected = []
    skipped_missing_text = []
    now = datetime.now(timezone.utc).isoformat()

    existing_rejected = _load_rejected_literature()
    existing_rejected_pmids = {item.get("pmid") for item in existing_rejected}

    for prop in req.proposals:
        pmid = str(prop.get("pmid", "")).strip()
        if not pmid:
            continue
        text = prop.get("abstract_text")

        if pmid in keep:
            if not text:
                skipped_missing_text.append(pmid)
                continue
            (APPROVED_LIT_DIR / f"abstract_PMID{pmid}.txt").write_text(text, encoding="utf-8")
            saved.append(pmid)
        else:
            if pmid in existing_rejected_pmids:
                continue
            existing_rejected.append({
                "pmid": pmid,
                "title": prop.get("title", ""),
                "abstract_text": text or "",
                "relevance": prop.get("relevance", ""),
                "reason": prop.get("reason", ""),
                "rejected_at": now,
            })
            rejected.append(pmid)

    _save_rejected_literature(existing_rejected)

    processed = _load_processed_pmids_set()
    processed.update(saved)
    processed.update(rejected)
    _save_processed_pmids(processed)

    return {
        "saved": saved,
        "rejected": rejected,
        "skipped_missing_text": skipped_missing_text,
        "saved_to": str(APPROVED_LIT_DIR),
        "rejected_count_total": len(existing_rejected),
    }


@app.get("/api/literature/rejected")
def list_rejected_literature():
    """Return all PMIDs the user has previously rejected.
    Each entry has pmid, title, abstract_text, relevance, reason, rejected_at."""
    return {"rejected": _load_rejected_literature()}


@app.post("/api/literature/rejected/restore")
def restore_rejected_literature(req: LiteratureRestoreRequest):
    """Move PMIDs from the rejected list back to the approved directory.
    The abstract_text already lives in the rejected list, so no re-fetch
    is needed. The PMID stays in processed_pmids so PubMed will not
    re-propose it on the next search."""
    APPROVED_LIT_DIR.mkdir(parents=True, exist_ok=True)
    rejected = _load_rejected_literature()
    target = set(req.pmids)
    restored = []
    remaining = []
    for item in rejected:
        pmid = item.get("pmid")
        if pmid in target and item.get("abstract_text"):
            (APPROVED_LIT_DIR / f"abstract_PMID{pmid}.txt").write_text(
                item["abstract_text"], encoding="utf-8")
            restored.append(pmid)
        else:
            remaining.append(item)
    _save_rejected_literature(remaining)
    return {
        "restored": restored,
        "still_rejected": [item.get("pmid") for item in remaining],
        "saved_to": str(APPROVED_LIT_DIR),
    }


@app.post("/api/literature/process", response_model=RunResponse)
def process_approved_literature(req: LiteratureProcessRequest):
    """Run Stage 3 on the user-approved subset only (not the full corpus)."""
    job = manager.create("pipeline", req.model_dump())

    def _target(j: Job):
        snap = _snapshot_current_ontology(label="pre-mining")
        if snap:
            j.append_log(f"Snapshot saved: {snap['name']} "
                          f"({snap['classes']}c / {snap['instances']}i / "
                          f"{snap['triples']}t)")
        j.append_log(f"Processing {len(req.pmids)} user-approved abstracts "
                      f"from {APPROVED_LIT_DIR.name}")
        j.stage = "stage3"
        resume = _load_current_ontology() if req.use_current_ontology else None
        result = run_full_pipeline(
            model=req.model,
            provider=req.provider,
            stages=[3],
            max_abstracts=None,
            resume_from=resume,
            on_progress=lambda s, m: j.append_log(m),
            stage3_dir_override=APPROVED_LIT_DIR,
        )
        j.append_log("Stage 3 complete on approved subset")
        return result

    manager.run(job, _target)
    return RunResponse(job_id=job.id, status=job.status)


@app.get("/api/dllearner/experiments")
def list_dllearner_experiments():
    return list_experiments()


@app.post("/api/dllearner/run", response_model=RunResponse)
def start_dllearner_run(req: DLLearnerRunRequest):
    job = manager.create("dllearner", req.model_dump())

    def _target(j: Job):
        j.append_log(f"Running DL-Learner experiment '{req.experiment}'")
        j.stage = "dllearner"
        result = run_experiment(
            experiment_name=req.experiment,
            owl_path=req.owl_path or "ontology/AMD_final_clean.owl",
        )
        if result.get("error") and not result.get("solutions"):
            j.append_log(f"Error: {result['error']}")
        else:
            top = result["solutions"][0] if result.get("solutions") else None
            if top:
                j.append_log(f"Top: {top['expression']} ({top.get('pred_acc')} / {top.get('f_measure')})")
        return result

    manager.run(job, _target)
    return RunResponse(job_id=job.id, status=job.status)


@app.get("/api/dllearner/{job_id}/result")
def get_dllearner_result(job_id: str):
    job = manager.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    if job.status != "done":
        raise HTTPException(status_code=409,
                              detail=f"Job is {job.status}, no result yet")
    return job.result


# ── Serve built Vue frontend (production / Docker) ───────────────────────────
# Registered LAST so API routes above take precedence over the SPA catch-all.

_FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"
if _FRONTEND_DIST.exists():
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse

    _ASSETS_DIR = _FRONTEND_DIST / "assets"
    if _ASSETS_DIR.exists():
        app.mount("/assets", StaticFiles(directory=_ASSETS_DIR), name="assets")

    @app.get("/", include_in_schema=False)
    def _serve_index():
        return FileResponse(_FRONTEND_DIST / "index.html")

    @app.get("/{path:path}", include_in_schema=False)
    def _serve_spa(path: str):
        if path.startswith("api/") or path == "openapi.json" or path.startswith("docs"):
            raise HTTPException(status_code=404, detail="Not Found")
        candidate = _FRONTEND_DIST / path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_FRONTEND_DIST / "index.html")
