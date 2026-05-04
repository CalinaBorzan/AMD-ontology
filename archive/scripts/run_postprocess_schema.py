"""
Post-processing validation script for AMD ontology schema.

Fixes structural OWL problems:
  1. Punning — entity in both subclasses AND individuals → keep as subclass, remove from individuals
  2. Self-referential individuals — "Aspirin": ["Aspirin"] → remove
  3. Hierarchy — ensures Disease → AMD → subtypes chain exists
  4. Empty individuals section — remove the entire section (abstracts are the real individuals)

Run after Stage 3, before OWL conversion:
    python run_postprocess_schema.py
"""

import argparse
import json
from pathlib import Path


def fix_punning(schema: dict) -> tuple[dict, list[str]]:
    """
    Fix punning: if an entity appears as BOTH a subclass AND an individual,
    keep it as an INDIVIDUAL and remove from subclasses.
    Specific named things (drugs, genes, devices) are individuals.
    Categories (WetAMD, AntiVEGFTherapy) are subclasses.
    """
    fixes = []
    classes = schema.get("classes", {})
    individuals = schema.get("individuals", {})

    for parent_class in list(individuals.keys()):
        if parent_class not in classes:
            continue
        subclasses = classes[parent_class].get("subclasses", [])
        if not subclasses:
            continue

        ind_list = individuals[parent_class]
        overlap = set(subclasses) & set(ind_list)
        if overlap:
            # Remove from subclasses — keep as individual
            classes[parent_class]["subclasses"] = [s for s in subclasses if s not in overlap]
            for entity in overlap:
                # Also remove the standalone class entry if it has no subclasses of its own
                if entity in classes and not classes[entity].get("subclasses"):
                    del classes[entity]
                fixes.append(f"  Punning fixed: '{entity}' removed from subclasses (kept as individual of {parent_class})")

    return schema, fixes


def keep_individuals_section(schema: dict) -> tuple[dict, list[str]]:
    """
    Keep the individuals section — these are specific named entities (drugs, genes, devices).
    The research abstracts are ADDITIONAL individuals added by convert_to_owl.py.
    """
    fixes = []
    individuals = schema.get("individuals", {})
    total = sum(len(v) for v in individuals.values()) if individuals else 0
    if total > 0:
        fixes.append(f"  Keeping {total} individuals across {len(individuals)} parent classes ✓")
    else:
        fixes.append("  Warning: no individuals found — specific drugs/genes/devices should be here")
    return schema, fixes


def fix_self_referential(schema: dict) -> tuple[dict, list[str]]:
    """Remove self-referential individuals where individual name == class name."""
    fixes = []
    individuals = schema.get("individuals", {})
    to_remove = []
    for class_name, ind_list in individuals.items():
        if len(ind_list) == 1 and ind_list[0] == class_name:
            to_remove.append(class_name)
            fixes.append(f"  Self-ref removed: '{class_name}': [\"{class_name}\"]")
    for key in to_remove:
        del individuals[key]
    return schema, fixes


def fix_hierarchy(schema: dict) -> tuple[dict, list[str]]:
    """Ensure Disease → AMD → subtypes chain exists."""
    fixes = []
    classes = schema.get("classes", {})

    if "Disease" not in classes:
        classes["Disease"] = {"description": "Top-level disease category", "subclasses": ["AMD"]}
        fixes.append("  Added missing 'Disease' class")

    disease = classes.get("Disease", {})
    disease_subs = disease.get("subclasses", [])
    if "AMD" not in disease_subs:
        disease_subs.append("AMD")
        disease["subclasses"] = disease_subs
        fixes.append("  Added 'AMD' as subclass of Disease")

    if "AMD" not in classes:
        classes["AMD"] = {"description": "Age-related macular degeneration", "subclasses": []}
        fixes.append("  Added missing 'AMD' class")

    # Move AMD subtypes from Disease to AMD
    amd_subtypes = {"WetAMD", "DryAMD", "GeographicAtrophy", "EarlyAMD",
                    "IntermediateAMD", "LateAMD", "NeovascularAMD",
                    "NonExsudativeAMD", "ExudativeAMD", "NonExudativeAMD",
                    "EarlyARM", "LateARM"}
    disease_subs = disease.get("subclasses", [])
    amd_subs = classes.get("AMD", {}).get("subclasses", [])
    moved = []
    for subtype in list(disease_subs):
        if subtype in amd_subtypes and subtype != "AMD":
            disease_subs.remove(subtype)
            if subtype not in amd_subs:
                amd_subs.append(subtype)
            moved.append(subtype)
    if moved:
        disease["subclasses"] = disease_subs
        classes["AMD"]["subclasses"] = amd_subs
        fixes.append(f"  Moved AMD subtypes from Disease to AMD: {moved}")

    return schema, fixes


def ensure_subclasses_have_class_entries(schema: dict) -> tuple[dict, list[str]]:
    """
    If an entity is listed as a subclass but doesn't have its own class entry,
    create one so it appears in the OWL hierarchy.
    """
    fixes = []
    classes = schema.get("classes", {})
    for class_name, class_data in list(classes.items()):
        for sub in class_data.get("subclasses", []):
            if sub not in classes:
                classes[sub] = {"description": f"{sub}", "subclasses": []}
                fixes.append(f"  Added missing class entry for subclass '{sub}' (under {class_name})")
    return schema, fixes


def print_summary(schema: dict):
    classes = schema.get("classes", {})
    properties = schema.get("properties", {})
    individuals = schema.get("individuals", {})
    total_individuals = sum(len(v) for v in individuals.values())
    total_subclasses = sum(len(c.get("subclasses", [])) for c in classes.values())

    print(f"\n  Classes      : {len(classes)}")
    print(f"  Subclasses   : {total_subclasses}")
    print(f"  Properties   : {len(properties)}")
    print(f"  Individuals  : {total_individuals}")

    # Check hierarchy
    disease_subs = classes.get("Disease", {}).get("subclasses", [])
    amd_subs = classes.get("AMD", {}).get("subclasses", [])
    if "AMD" in disease_subs and len(amd_subs) > 0:
        print("  Hierarchy    : Disease → AMD → subtypes ✓")
    else:
        print("  Hierarchy    : BROKEN ✗")

    # Check punning
    punning = 0
    for parent, ind_list in individuals.items():
        if parent in classes:
            subs = set(classes[parent].get("subclasses", []))
            punning += len(subs & set(ind_list))
    print(f"  Punning      : {'NONE ✓' if punning == 0 else f'{punning} violations ✗'}")


def run(input_path: str, output_path: str):
    with open(input_path, encoding="utf-8") as f:
        schema = json.load(f)

    print(f"\nLoaded schema from: {input_path}")
    all_fixes = []

    print("\n── Fix 1: Punning (keep as subclass, remove from individuals) ──")
    schema, fixes = fix_punning(schema)
    all_fixes.extend(fixes)
    for f in fixes: print(f)
    if not fixes: print("  No punning found ✓")

    print("\n── Fix 2: Self-referential individuals ──")
    schema, fixes = fix_self_referential(schema)
    all_fixes.extend(fixes)
    for f in fixes: print(f)
    if not fixes: print("  No self-referential individuals ✓")

    print("\n── Fix 3: Verify individuals section ──")
    schema, fixes = keep_individuals_section(schema)
    all_fixes.extend(fixes)
    for f in fixes: print(f)

    print("\n── Fix 4: Disease → AMD hierarchy ──")
    schema, fixes = fix_hierarchy(schema)
    all_fixes.extend(fixes)
    for f in fixes: print(f)
    if not fixes: print("  Hierarchy is correct ✓")

    print("\n── Fix 5: Ensure all subclasses have class entries ──")
    schema, fixes = ensure_subclasses_have_class_entries(schema)
    all_fixes.extend(fixes)
    for f in fixes: print(f)
    if not fixes: print("  All subclasses have entries ✓")

    # Save
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(schema, f, indent=4, ensure_ascii=False)

    print(f"\n{'='*55}")
    print(f"  SUMMARY — {len(all_fixes)} fixes applied")
    print(f"{'='*55}")
    print_summary(schema)
    print(f"\n  Saved to: {output_path}")
    print(f"{'='*55}\n")


def main():
    parser = argparse.ArgumentParser(description="Post-process AMD ontology schema")
    parser.add_argument("--input", default="results/amd/final/amd_ontology_final.json")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    output = args.output or args.input
    run(args.input, output)


if __name__ == "__main__":
    main()
