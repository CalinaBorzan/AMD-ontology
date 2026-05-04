"""
Leaf-demotion pass for the AMD ontology.

Finds every "leaf class" — a class with no subclasses and no instances —
and proposes demoting it to an INSTANCE of its parent class. This is a
deterministic Python pass (no LLM) that fixes the class-over-granularity
problem where the agentic extraction created a subclass for every specific
named thing (Lutein, Zeaxanthin, OpticalCoherenceTomography, etc.) instead
of keeping them as instances of their parent.

What a "leaf class" is:
  * Has no `subclasses` entries
  * Has no `instances` entries of its own
  * Is listed as a subclass of exactly one parent class
  * Is NOT one of the protected canonical roots

When demoting:
  * The class is removed from SCHEMA["classes"]
  * It is added to its parent's `instances` list
  * Its `_pending_parent` marker (if any) is cleared
  * Triples referencing it (subject or object) are left unchanged — they
    still work because instance names are strings.

Usage:
    python run_demote_leaves.py                    # interactive HITL
    python run_demote_leaves.py --all              # auto-accept everything
    python run_demote_leaves.py --dry-run          # show what would happen, don't apply
    python run_demote_leaves.py --input OTHER.json # custom input file
"""

import argparse
import json
import shutil
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent.parent
DEFAULT_INPUT = PROJECT_ROOT / "results" / "amd" / "final" / "amd_ontology_final.json"

# Classes that MUST stay as classes even if they look like leaves.
# These are the structural scaffolding of the ontology — removing any of
# them would break the hierarchy.
PROTECTED = {
    "Disease", "Treatment", "Biomarker", "DiagnosticMethod",
    "RiskFactor", "ClinicalOutcome",
    # AMD intermediate tree — preserve these even if they have no direct
    # instances/subclasses right now
    "AMD", "DryAMD", "WetAMD", "AgeRelatedMaculopathy",
    "IntermediateAMD", "AdvancedAMD",
    "GeographicAtrophy", "ChoroidalNeovascularization",
    # Important sub-categories
    "GeneticBiomarker", "MolecularTarget", "ImagingBiomarker",
    "StructuralBiomarker", "FunctionalBiomarker",
    "ImagingMethod", "FunctionalMethod",
    "AntiVEGFTherapy", "PhotodynamicTherapy", "Supplements",
    "LaserTherapy", "SubmacularSurgery", "CorticosteroidInjection",
}


def find_parents(schema: dict) -> dict[str, list[str]]:
    """For every class, list the classes that have it as a subclass."""
    parents = {}
    for parent_name, parent_data in schema.get("classes", {}).items():
        if not isinstance(parent_data, dict):
            continue
        for child in parent_data.get("subclasses", []):
            parents.setdefault(child, []).append(parent_name)
    return parents


def find_leaf_candidates(schema: dict) -> list[tuple[str, str]]:
    """Return a list of (class_name, parent_name) for every class that
    qualifies as a leaf to demote.

    Qualification:
      - No subclasses
      - No instances
      - Has exactly one parent (so we know where it goes)
      - Not in PROTECTED
      - Not a pending orphan (we can't demote orphans — they have no parent)
    """
    classes = schema.get("classes", {})
    parents = find_parents(schema)
    candidates = []

    for name, data in classes.items():
        if not isinstance(data, dict):
            continue
        if name in PROTECTED:
            continue
        if data.get("subclasses"):
            continue
        if data.get("instances"):
            continue
        if "_pending_parent" in data:
            # Can't demote — its parent never existed
            continue
        parent_list = parents.get(name, [])
        if len(parent_list) != 1:
            # 0 parents → it's a root; we don't touch roots
            # 2+ parents → ambiguous; we don't touch multi-parent classes
            continue
        candidates.append((name, parent_list[0]))

    return candidates


def apply_demotion(schema: dict, class_name: str, parent_name: str) -> bool:
    """Remove the class from `classes` and add it as an instance of its parent.
    Returns True if applied, False if something was off."""
    classes = schema.get("classes", {})
    if class_name not in classes:
        return False
    if parent_name not in classes:
        return False

    # Remove from parent's subclasses list
    parent_data = classes[parent_name]
    subs = parent_data.get("subclasses", [])
    if class_name in subs:
        parent_data["subclasses"] = [s for s in subs if s != class_name]

    # Add to parent's instances list (dedupe)
    insts = parent_data.get("instances", [])
    if class_name not in insts:
        insts.append(class_name)
    parent_data["instances"] = insts

    # Delete the class entry
    del classes[class_name]
    return True


def summarize_candidates(candidates: list[tuple[str, str]]) -> None:
    """Group candidates by parent and print a readable list."""
    by_parent = {}
    for name, parent in candidates:
        by_parent.setdefault(parent, []).append(name)

    print(f"\n{'=' * 60}")
    print(f"  Leaf-demotion candidates: {len(candidates)}")
    print(f"{'=' * 60}\n")

    for parent in sorted(by_parent):
        names = sorted(by_parent[parent])
        print(f"  {parent} ({len(names)} leaves):")
        for n in names:
            print(f"    - {n}")
        print()


def run(input_path: Path, output_path: Path, auto_accept: bool, dry_run: bool):
    if not input_path.exists():
        print(f"ERROR: input file not found: {input_path}")
        return

    schema = json.loads(input_path.read_text(encoding="utf-8"))
    classes_before = len(schema.get("classes", {}))
    instances_before = sum(
        len(v.get("instances", []))
        for v in schema.get("classes", {}).values()
        if isinstance(v, dict)
    )

    print(f"\nLoaded: {input_path}")
    print(f"  Classes before   : {classes_before}")
    print(f"  Instances before : {instances_before}")

    candidates = find_leaf_candidates(schema)

    if not candidates:
        print("\n  No leaf candidates found. Nothing to demote.")
        return

    summarize_candidates(candidates)

    if dry_run:
        print(f"\n  DRY RUN — no changes written. Would have demoted {len(candidates)} classes.")
        return

    # Get human approval
    if auto_accept:
        choice = "a"
    else:
        print(f"  Choose:")
        print(f"    [a] accept all {len(candidates)} demotions")
        print(f"    [s] select each one individually")
        print(f"    [q] quit without changes")
        choice = input("\n  Your choice [a/s/q]: ").strip().lower()

    to_apply: list[tuple[str, str]] = []

    if choice == "a":
        to_apply = candidates
    elif choice == "s":
        for i, (name, parent) in enumerate(candidates, 1):
            print(f"\n  [{i}/{len(candidates)}] Demote {name!r} → instance of {parent!r}? [y/n/skip/all]: ", end="")
            ans = input().strip().lower()
            if ans == "y":
                to_apply.append((name, parent))
            elif ans == "all":
                to_apply.append((name, parent))
                to_apply.extend(candidates[i:])
                break
            # 'n' or 'skip' → don't add
    else:
        print("  Cancelled. No changes made.")
        return

    if not to_apply:
        print("\n  Nothing accepted. No changes made.")
        return

    # Back up the input first
    backup = input_path.with_name(
        f"{input_path.stem}.pre_demote_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    shutil.copy(input_path, backup)
    print(f"\n  Backed up original to {backup}")

    # Apply
    applied = 0
    failed = 0
    for name, parent in to_apply:
        if apply_demotion(schema, name, parent):
            applied += 1
        else:
            failed += 1
            print(f"  FAILED: {name} → {parent}")

    # Save
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(schema, f, indent=4, ensure_ascii=False)

    classes_after = len(schema.get("classes", {}))
    instances_after = sum(
        len(v.get("instances", []))
        for v in schema.get("classes", {}).values()
        if isinstance(v, dict)
    )

    print(f"\n{'=' * 60}")
    print(f"  DEMOTION COMPLETE")
    print(f"{'=' * 60}")
    print(f"  Applied           : {applied}")
    if failed:
        print(f"  Failed            : {failed}")
    print(f"  Classes    : {classes_before} → {classes_after}  (Δ {classes_after - classes_before:+d})")
    print(f"  Instances  : {instances_before} → {instances_after}  (Δ {instances_after - instances_before:+d})")
    print(f"  Saved to   : {output_path}")
    print(f"  Backup at  : {backup}\n")


def main():
    parser = argparse.ArgumentParser(description="Demote leaf classes to instances of their parent")
    parser.add_argument("--input", default=str(DEFAULT_INPUT),
                        help="Input ontology JSON (default: results/amd/final/amd_ontology_final.json)")
    parser.add_argument("--output", default=None,
                        help="Output path (default: overwrite input)")
    parser.add_argument("--all", action="store_true",
                        help="Auto-accept all demotions without prompting")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be demoted without applying anything")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output) if args.output else input_path
    run(input_path, output_path, auto_accept=args.all, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
