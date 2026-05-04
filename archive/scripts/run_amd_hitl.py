"""
SCHEMA-MINERpro AMD Pipeline — Human-in-the-Loop (HITL) Version
================================================================
Thesis requirement: Human domain expert can intervene at every stage.

Pipeline flow:
  Stage 1: domain spec → initial ontology schema
        ↓  [HUMAN PAUSE: review, edit JSON, or give NL correction]
  Stage 2: iterative refinement with curated abstracts (one at a time)
        ↓  [HUMAN PAUSE after all Stage-2 abstracts]
  Stage 3: validation with full corpus abstracts
        ↓  [HUMAN PAUSE after all Stage-3 abstracts]
  Final schema saved.

At each pause point the expert can:
  [ENTER]         — accept schema as-is
  [e + ENTER]     — open schema in system editor (notepad/nano), save, then ENTER
  [typed text]    — enter a natural language correction; the LLM applies it before continuing
"""

import json
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from schema_miner.config.envConfig import EnvConfig
from schema_miner.config.processConfig import ProcessConfig
from schema_miner.schema_extractor.extract_schema import (
    extract_schema_stage1,
    extract_schema_stage2,
    extract_schema_stage3,
)
from schema_miner.services.LLM_Inference.inference_runner import llm_inference
from schema_miner.config.llmRegistry import LLMRegistry
from schema_miner.utils.file_utils import load_json_input, save_json_file

# ── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("amd_pipeline.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────────────
LLM_MODEL = "llama3.1:8b"          # Change to your available model (ollama pull <name>)
DOMAIN_SPEC_PATH = "./data/stage-1/AMD/amd_domain_spec.txt"
STAGE2_ABSTRACTS_DIR = "./data/stage-2/AMD/abstracts"
STAGE3_ABSTRACTS_DIR = "./data/stage-3/AMD/abstracts"
RESULTS_DIR = "./results/amd"

# 15 abstracts total: 5 for Stage 2 (curated refinement) + 10 for Stage 3 (validation)
STAGE2_MAX_ABSTRACTS = 5
STAGE3_MAX_ABSTRACTS = 10


# ═══════════════════════════════════════════════════════════════════════════
# HUMAN-IN-THE-LOOP UTILITIES
# ═══════════════════════════════════════════════════════════════════════════

def _show_schema_diff(prev: dict, curr: dict) -> None:
    """Print a human-readable diff of classes and properties between two schemas."""
    print("\n  --- SCHEMA DIFF (what changed) ---")

    prev_classes = set(prev.get("classes", {}).keys())
    curr_classes = set(curr.get("classes", {}).keys())
    added_cls = curr_classes - prev_classes
    removed_cls = prev_classes - curr_classes
    if added_cls:
        print(f"  + Classes ADDED   : {', '.join(sorted(added_cls))}")
    if removed_cls:
        print(f"  - Classes REMOVED : {', '.join(sorted(removed_cls))}")
    if not added_cls and not removed_cls:
        print("  (no class additions or removals)")

    prev_props = set(prev.get("properties", {}).keys())
    curr_props = set(curr.get("properties", {}).keys())
    added_props = curr_props - prev_props
    removed_props = prev_props - curr_props
    if added_props:
        print(f"  + Properties ADDED   : {', '.join(sorted(added_props))}")
    if removed_props:
        print(f"  - Properties REMOVED : {', '.join(sorted(removed_props))}")
    if not added_props and not removed_props:
        print("  (no property additions or removals)")

    prev_inds = {k: set(v) for k, v in prev.get("individuals", {}).items()}
    curr_inds = {k: set(v) for k, v in curr.get("individuals", {}).items()}
    for cat in set(list(prev_inds.keys()) + list(curr_inds.keys())):
        added_i = curr_inds.get(cat, set()) - prev_inds.get(cat, set())
        if added_i:
            print(f"  + Individuals [{cat}] ADDED: {', '.join(sorted(added_i))}")

    print("  ----------------------------------\n")


def _apply_nl_correction(correction_text: str, schema: dict, llm_model: str) -> dict:
    """
    Apply a natural language correction to the schema using the LLM.
    The expert types something like: "remove ultrasound from diagnostics; add intravitreal injection"
    """
    print("\n  Applying your correction via LLM, please wait...")

    # Build a minimal one-shot prompt module inline
    class _CorrectionPrompt:
        system_prompt = (
            "You are an ontology editor. You will receive an AMD ontology schema in JSON "
            "and a correction instruction from a domain expert. Apply the correction exactly "
            "as instructed. Return ONLY the corrected complete JSON schema in ```json fenced code block."
        )
        user_prompt = (
            "Current AMD ontology schema:\n{current_schema}\n\n"
            "Expert correction instruction:\n{correction}\n\n"
            "Return the COMPLETE corrected schema."
        )

    try:
        llm_cls = LLMRegistry.get_llm_Inference_cls(llm_model)
        # Write schema to temp file so we can pass it through the normal pipeline
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as tf:
            json.dump(schema, tf, indent=2)
            tmp_path = tf.name

        var_dict = {
            "current_schema": json.dumps(schema, indent=2),
            "correction": correction_text,
        }
        corrected = llm_inference(llm_cls, llm_model, _CorrectionPrompt, var_dict, tempfile.gettempdir())
        os.unlink(tmp_path)

        if corrected:
            print("  Correction applied successfully.")
            return corrected
        else:
            print("  Warning: LLM could not apply correction. Keeping original schema.")
            return schema
    except Exception as e:
        print(f"  Warning: Error applying correction: {e}. Keeping original schema.")
        return schema


def human_pause(stage_label: str, schema_path: Path, llm_model: str, prev_schema: dict = None) -> dict:
    """
    Pause the pipeline for human expert review.

    The expert can:
      - Press ENTER to accept the current schema
      - Type 'e' to open the schema file in a text editor
      - Type a natural language correction to be applied by the LLM

    Returns the (possibly modified) schema as a dict.
    """
    # Load current schema from disk
    current_schema = load_json_input(schema_path)
    if current_schema is None:
        print(f"  Warning: could not load schema from {schema_path}. Continuing with empty schema.")
        return {}

    print("\n" + "═" * 70)
    print(f"  HUMAN EXPERT REVIEW — {stage_label}")
    print("═" * 70)
    print(f"\n  Schema file : {schema_path.resolve()}")
    print(f"  Schema size : {len(json.dumps(current_schema))} characters")
    print(f"  Classes     : {list(current_schema.get('classes', {}).keys())}")
    print(f"  Properties  : {list(current_schema.get('properties', {}).keys())}")

    if prev_schema:
        _show_schema_diff(prev_schema, current_schema)

    print("\n  OPTIONS:")
    print("  [ENTER]       Accept schema as-is and continue to next stage")
    print("  [e]           Open schema in text editor (edit, save, then press ENTER here)")
    print("  [text]        Type a natural language correction for the LLM to apply")
    print("                Example: 'remove ultrasound from diagnostics; add intravitreal injection as treatment'")

    while True:
        try:
            choice = input("\n  Your choice: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  Interrupted. Accepting schema as-is.")
            break

        if choice == "":
            print("  Accepted. Continuing...")
            break

        elif choice.lower() == "e":
            # Open schema in system text editor
            editor = os.environ.get("EDITOR", "notepad" if os.name == "nt" else "nano")
            print(f"  Opening {schema_path} in {editor}...")
            try:
                subprocess.run([editor, str(schema_path.resolve())])
            except Exception as ex:
                print(f"  Could not open editor: {ex}")
                print(f"  Please manually edit: {schema_path.resolve()}")
            input("  Press ENTER when you have finished editing and saved the file...")
            # Reload from disk
            current_schema = load_json_input(schema_path)
            if current_schema is None:
                print("  Warning: could not reload schema after edit. Using previous version.")
            else:
                print("  Schema reloaded after edit.")
            break

        else:
            # Natural language correction — apply via LLM
            print(f"  Applying correction: '{choice}'")
            corrected = _apply_nl_correction(choice, current_schema, llm_model)
            # Save corrected schema back to the same file
            save_json_file(str(schema_path.parent), schema_path.name, corrected)
            current_schema = corrected
            print("  Corrected schema saved.")

            # Ask if they want another correction or are done
            more = input("  Apply another correction? [ENTER to continue / type another correction]: ").strip()
            if more == "":
                print("  Continuing...")
                break
            else:
                choice = more  # loop again with new correction
                corrected = _apply_nl_correction(choice, current_schema, llm_model)
                save_json_file(str(schema_path.parent), schema_path.name, corrected)
                current_schema = corrected
                print("  Correction applied.")
                break

    print("═" * 70 + "\n")
    return current_schema


# ═══════════════════════════════════════════════════════════════════════════
# STAGE RUNNERS
# ═══════════════════════════════════════════════════════════════════════════

def load_text_file(filepath: str) -> str:
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


def run_stage1(llm_model: str, domain_spec_path: str, results_dir: str):
    logger.info("=" * 60)
    logger.info("STAGE 1: Initial Schema Generation from Domain Specification")
    logger.info("=" * 60)

    results_path = Path(results_dir) / "stage-1" / "AMD"
    results_path.mkdir(parents=True, exist_ok=True)

    domain_spec = load_text_file(domain_spec_path)
    logger.info(f"Domain spec loaded: {len(domain_spec)} characters")

    schema = extract_schema_stage1(
        llm_model,
        domain_spec,
        str(results_path),
        save_schema=True,
    )

    safe_name = llm_model.replace(":", "-").replace("/", "-")
    schema_file = results_path / f"{safe_name}.json"
    logger.info(f"Stage 1 complete. Schema: {schema_file}")
    return schema, schema_file


def run_stage2_single(llm_model: str, current_schema_path: Path, abstract_text: str,
                      expert_feedback: str, results_path: Path, idx: int):
    """Run Stage 2 for one abstract and save the updated schema."""
    feedback_path = results_path / f"expert_feedback_stage2_{idx}.txt"
    feedback_path.write_text(expert_feedback, encoding="utf-8")

    schema = extract_schema_stage2(
        llm_model,
        current_schema_path,
        feedback_path,
        abstract_text,
        str(results_path),
        save_schema=True,
    )

    feedback_path.unlink(missing_ok=True)
    safe_name = llm_model.replace(":", "-").replace("/", "-")
    return schema, results_path / f"{safe_name}.json"


def run_stage3_single(llm_model: str, current_schema_path: Path, abstract_text: str,
                      expert_feedback: str, results_path: Path, idx: int):
    """Run Stage 3 for one abstract and save the updated schema."""
    feedback_path = results_path / f"expert_feedback_stage3_{idx}.txt"
    feedback_path.write_text(expert_feedback, encoding="utf-8")

    schema = extract_schema_stage3(
        llm_model,
        current_schema_path,
        feedback_path,
        abstract_text,
        str(results_path),
        save_schema=True,
    )

    feedback_path.unlink(missing_ok=True)
    safe_name = llm_model.replace(":", "-").replace("/", "-")
    return schema, results_path / f"{safe_name}.json"


# ═══════════════════════════════════════════════════════════════════════════
# MAIN PIPELINE
# ═══════════════════════════════════════════════════════════════════════════

def main():
    print("\n" + "═" * 70)
    print("  SCHEMA-MINERpro — AMD Ontology Extraction  (HITL Mode)")
    print("═" * 70)
    print(f"\n  Model      : {LLM_MODEL}")
    print(f"  Stage 1    : 1 domain specification")
    print(f"  Stage 2    : {STAGE2_MAX_ABSTRACTS} curated abstracts  (abstracts 001-005)")
    print(f"  Stage 3    : {STAGE3_MAX_ABSTRACTS} validation abstracts  (abstracts 001-010)")
    print(f"  Total      : {STAGE2_MAX_ABSTRACTS + STAGE3_MAX_ABSTRACTS} abstracts")
    print(f"  Results    : {RESULTS_DIR}")
    print("\n  Requirements: Ollama must be running  →  ollama serve")
    print(f"  Model pull  : ollama pull {LLM_MODEL}\n")

    # Validate paths
    for path, label in [
        (DOMAIN_SPEC_PATH, "domain spec"),
        (STAGE2_ABSTRACTS_DIR, "Stage 2 abstracts dir"),
        (STAGE3_ABSTRACTS_DIR, "Stage 3 abstracts dir"),
    ]:
        if not Path(path).exists():
            print(f"  ERROR: {label} not found: {path}")
            sys.exit(1)

    input("  Press ENTER to start the pipeline...")

    # Configure Ollama URL
    EnvConfig.OLLAMA_base_url = "http://localhost:11434"

    safe_name = LLM_MODEL.replace(":", "-").replace("/", "-")

    # ──────────────────────────────────────────────
    # STAGE 1
    # ──────────────────────────────────────────────
    print("\n" + "─" * 70)
    print("  STAGE 1: Generating initial ontology from domain specification")
    print("─" * 70)

    schema_s1, schema_s1_path = run_stage1(LLM_MODEL, DOMAIN_SPEC_PATH, RESULTS_DIR)

    if schema_s1 is None or not schema_s1_path.exists():
        print("\n  STAGE 1 FAILED. Check amd_pipeline.log for details.")
        sys.exit(1)

    print(f"\n  Stage 1 schema: {schema_s1_path.resolve()}")

    # ── HUMAN PAUSE AFTER STAGE 1 ──────────────────
    schema_after_s1 = human_pause(
        stage_label="After Stage 1 — Review Initial Ontology Schema",
        schema_path=schema_s1_path,
        llm_model=LLM_MODEL,
        prev_schema=None,
    )
    # Save any expert edits back
    save_json_file(str(schema_s1_path.parent), schema_s1_path.name, schema_after_s1)

    # ──────────────────────────────────────────────
    # STAGE 2
    # ──────────────────────────────────────────────
    print("\n" + "─" * 70)
    print("  STAGE 2: Iterative refinement with curated AMD abstracts")
    print("─" * 70)

    s2_abstracts = sorted(Path(STAGE2_ABSTRACTS_DIR).glob("*.txt"))[:STAGE2_MAX_ABSTRACTS]
    if not s2_abstracts:
        print(f"  ERROR: No abstracts in {STAGE2_ABSTRACTS_DIR}")
        sys.exit(1)

    print(f"  Using {len(s2_abstracts)} curated abstracts for Stage 2\n")
    results_s2 = Path(RESULTS_DIR) / "stage-2" / "AMD"
    results_s2.mkdir(parents=True, exist_ok=True)

    current_s2_path = schema_s1_path
    schema_before_s2 = schema_after_s1

    # Default expert feedback for Stage 2 — expert can override at the HITL pause
    stage2_expert_feedback = (
        "Focus on AMD-specific medical knowledge. "
        "Extract all AMD disease subtypes, anti-VEGF treatments, genetic markers (CFH, ARMS2, HTRA1), "
        "imaging biomarkers (OCT findings, drusen, retinal thickness), risk factors (age, smoking, genetics), "
        "and clinical outcomes (visual acuity, lesion size). "
        "Do NOT remove properties because dosage or measurement values are absent — "
        "abstracts rarely contain this level of detail."
    )

    for i, abstract_file in enumerate(s2_abstracts):
        abstract_text = load_text_file(str(abstract_file))
        print(f"  [Stage 2 — {i+1}/{len(s2_abstracts)}] Processing: {abstract_file.name}")

        schema_s2, current_s2_path = run_stage2_single(
            LLM_MODEL, current_s2_path, abstract_text,
            stage2_expert_feedback, results_s2, i
        )

        if schema_s2 is None:
            print(f"  Warning: abstract {i+1} produced no schema update. Keeping previous.")
            current_s2_path = results_s2 / f"{safe_name}.json"

        print(f"  Updated schema: {current_s2_path}")

    # ── HUMAN PAUSE AFTER STAGE 2 ──────────────────
    schema_after_s2 = human_pause(
        stage_label="After Stage 2 — Review Refined Ontology Schema",
        schema_path=current_s2_path,
        llm_model=LLM_MODEL,
        prev_schema=schema_before_s2,
    )
    save_json_file(str(current_s2_path.parent), current_s2_path.name, schema_after_s2)

    # ──────────────────────────────────────────────
    # STAGE 3
    # ──────────────────────────────────────────────
    print("\n" + "─" * 70)
    print("  STAGE 3: Validation and extension with full abstract corpus")
    print("─" * 70)

    s3_all = sorted(Path(STAGE3_ABSTRACTS_DIR).glob("*.txt"))
    s3_abstracts = s3_all if STAGE3_MAX_ABSTRACTS is None else s3_all[:STAGE3_MAX_ABSTRACTS]
    if not s3_abstracts:
        print(f"  ERROR: No abstracts in {STAGE3_ABSTRACTS_DIR}")
        sys.exit(1)

    print(f"  Using {len(s3_abstracts)} abstracts for Stage 3 validation\n")
    results_s3 = Path(RESULTS_DIR) / "stage-3" / "AMD"
    results_s3.mkdir(parents=True, exist_ok=True)

    current_s3_path = current_s2_path
    schema_before_s3 = schema_after_s2

    # Default expert feedback for Stage 3
    stage3_expert_feedback = (
        "Validate the AMD ontology schema. Add any missing AMD entities or relationships found in this abstract. "
        "Keep all existing content — do not remove anything. "
        "A property should be retained even if the abstract lacks specific numeric values. "
        "Focus on adding: new genetic variants, new diagnostic methods, new treatment approaches, "
        "new outcome measures. Ensure anti-VEGF agents are correctly linked to Wet AMD."
    )

    for i, abstract_file in enumerate(s3_abstracts):
        abstract_text = load_text_file(str(abstract_file))
        print(f"  [Stage 3 — {i+1}/{len(s3_abstracts)}] Validating: {abstract_file.name}")

        schema_s3, current_s3_path = run_stage3_single(
            LLM_MODEL, current_s3_path, abstract_text,
            stage3_expert_feedback, results_s3, i
        )

        if schema_s3 is None:
            print(f"  Warning: abstract {i+1} produced no schema update. Keeping previous.")
            current_s3_path = results_s3 / f"{safe_name}.json"

        print(f"  Updated schema: {current_s3_path}")

    # ── HUMAN PAUSE AFTER STAGE 3 ──────────────────
    schema_final = human_pause(
        stage_label="After Stage 3 — Final Ontology Review Before Saving",
        schema_path=current_s3_path,
        llm_model=LLM_MODEL,
        prev_schema=schema_before_s3,
    )

    # Save final schema
    final_output_dir = Path(RESULTS_DIR) / "final"
    final_output_dir.mkdir(parents=True, exist_ok=True)
    save_json_file(str(final_output_dir), "amd_ontology_final.json", schema_final)

    # ──────────────────────────────────────────────
    # SUMMARY
    # ──────────────────────────────────────────────
    print("\n" + "═" * 70)
    print("  PIPELINE COMPLETE")
    print("═" * 70)
    print(f"\n  Stage 1 schema : {schema_s1_path}")
    print(f"  Stage 2 schema : {current_s2_path}")
    print(f"  Stage 3 schema : {current_s3_path}")
    print(f"  FINAL schema   : {final_output_dir / 'amd_ontology_final.json'}")
    print("\n  Next steps:")
    print("    1. Review final JSON schema")
    print("    2. Convert to OWL:  python convert_to_owl.py")
    print("    3. Run DL-Learner:  dllearner amd_config.conf")
    print("    4. Inspect inferred axioms in AMD.owl")
    print("═" * 70 + "\n")


if __name__ == "__main__":
    main()
