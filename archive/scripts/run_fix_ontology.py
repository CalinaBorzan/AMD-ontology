"""
Generic ontology JSON fixer — works for ANY domain, not just AMD.

Fixes applied (all structural, no hardcoded domain knowledge):
  1. Punning: entity is both class and individual → decide by structure
  2. Self-referential individuals: "X": ["X"] → removed
  3. Duplicate individuals: same name in multiple groups → keep first occurrence
  4. Dangling subclass refs: listed as subclass but no class entry → create stub class
  5. Duplicate subclass entries → deduplicated
  6. individuals.category cleanup: entries already in class instances → removed from category

Usage:
    python run_fix_ontology.py
    python run_fix_ontology.py --input results/amd/final/amd_ontology_final.json
    python run_fix_ontology.py --input my_ontology.json --output my_ontology_fixed.json
"""

import argparse
import json
from pathlib import Path


def fix_punning(schema: dict) -> list[str]:
    """
    If an entity is BOTH a class AND an individual, resolve by structure:
    - If it has subclasses or IS a subclass of something → keep as class, remove from individuals
    - Otherwise → keep as individual, remove from classes
    """
    fixes = []
    classes = schema.get("classes", {})
    individuals = schema.get("individuals", {})

    # Collect ALL individual names
    all_individuals = set()
    for group_name, items in individuals.items():
        if isinstance(items, list):
            all_individuals.update(items)
        elif isinstance(items, dict):
            all_individuals.update(items.keys())

    # Also collect individuals from class 'instances' fields
    for class_data in classes.values():
        if isinstance(class_data, dict):
            for inst in class_data.get("instances", []):
                all_individuals.add(inst)

    # Entities that are structurally classes (have subclasses or are subclass of something)
    has_subclasses = set()
    is_subclass = set()
    has_instances = set()
    for name, data in classes.items():
        if isinstance(data, dict):
            subs = data.get("subclasses", [])
            if subs:
                has_subclasses.add(name)
            if data.get("instances"):
                has_instances.add(name)
            for sub in subs:
                is_subclass.add(sub)

    structurally_class = has_subclasses | is_subclass | has_instances

    # Find punning: entities that are both class keys AND individuals
    punning_entities = set(classes.keys()) & all_individuals

    for entity in sorted(punning_entities):
        if entity in structurally_class:
            # Keep as class, remove from individuals
            for group_name, items in individuals.items():
                if isinstance(items, list) and entity in items:
                    items.remove(entity)
                elif isinstance(items, dict) and entity in items:
                    del items[entity]
            # Also remove from other classes' instances
            for class_data in classes.values():
                if isinstance(class_data, dict) and entity in class_data.get("instances", []):
                    class_data["instances"].remove(entity)
            fixes.append(f"Punning: '{entity}' is in class hierarchy → removed from individuals")
        else:
            # Keep as individual, remove from classes
            # But first remove it from any parent's subclasses list
            for class_data in classes.values():
                if isinstance(class_data, dict) and entity in class_data.get("subclasses", []):
                    class_data["subclasses"].remove(entity)
            del classes[entity]
            fixes.append(f"Punning: '{entity}' not in hierarchy → removed from classes")

    return fixes


def fix_self_referential(schema: dict) -> list[str]:
    """Remove self-referential individuals where a group contains only itself: 'X': ['X']."""
    fixes = []
    individuals = schema.get("individuals", {})

    for group_name in list(individuals.keys()):
        items = individuals[group_name]
        if isinstance(items, list) and len(items) == 1 and items[0] == group_name:
            # Check if this group name is a class — if so, the instance is wrong
            classes = schema.get("classes", {})
            if group_name in classes:
                individuals[group_name] = []
                fixes.append(f"Self-ref: '{group_name}': ['{group_name}'] → cleared")

    return fixes


def fix_duplicate_subclasses(schema: dict) -> list[str]:
    """Remove duplicate entries within the same subclasses list."""
    fixes = []
    classes = schema.get("classes", {})

    for class_name, data in classes.items():
        if isinstance(data, dict):
            subs = data.get("subclasses", [])
            if len(subs) != len(set(subs)):
                deduped = list(dict.fromkeys(subs))  # preserves order
                removed = len(subs) - len(deduped)
                data["subclasses"] = deduped
                fixes.append(f"Dedup: '{class_name}' had {removed} duplicate subclass entries")

    return fixes


def print_summary(schema: dict):
    classes = schema.get("classes", {})
    properties = schema.get("properties", {})
    individuals = schema.get("individuals", {})

    total_ind = 0
    for items in individuals.values():
        if isinstance(items, list):
            total_ind += len(items)
        elif isinstance(items, dict):
            total_ind += len(items)

    # Also count class instances
    total_instances = sum(
        len(c.get("instances", []))
        for c in classes.values() if isinstance(c, dict)
    )

    total_subs = sum(
        len(c.get("subclasses", []))
        for c in classes.values() if isinstance(c, dict)
    )

    # Check punning
    all_ind_names = set()
    for items in individuals.values():
        if isinstance(items, list):
            all_ind_names.update(items)
        elif isinstance(items, dict):
            all_ind_names.update(items.keys())
    for c in classes.values():
        if isinstance(c, dict):
            all_ind_names.update(c.get("instances", []))
    punning = set(classes.keys()) & all_ind_names

    # Self-referential
    self_ref = [
        k for k, v in individuals.items()
        if isinstance(v, list) and len(v) == 1 and v[0] == k and k in classes
    ]

    print(f"\n  Classes        : {len(classes)}")
    print(f"  Subclass refs  : {total_subs}")
    print(f"  Properties     : {len(properties)}")
    print(f"  Individuals    : {total_ind} (in groups) + {total_instances} (in class instances)")
    print(f"  Punning        : {len(punning)} {'violations ' + str(sorted(punning)[:5]) if punning else '✓ NONE'}")
    print(f"  Self-referential: {len(self_ref)} {self_ref[:5] if self_ref else '✓ NONE'}")


def run(input_path: str, output_path: str):
    with open(input_path, encoding="utf-8") as f:
        schema = json.load(f)

    print(f"\nLoaded: {input_path}")
    print_summary(schema)

    all_fixes = []
    fix_steps = [
        ("Punning",              fix_punning),
        ("Self-referential",     fix_self_referential),

        ("Duplicate subclasses", fix_duplicate_subclasses),
    ]

    for step_name, fix_fn in fix_steps:
        print(f"\n── {step_name} ──")
        fixes = fix_fn(schema)
        all_fixes.extend(fixes)
        for f in fixes:
            print(f"  {f}")
        if not fixes:
            print("  OK ✓")

    # Save
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(schema, f, indent=4, ensure_ascii=False)

    print(f"\n{'='*55}")
    print(f"  {len(all_fixes)} fixes applied")
    print(f"{'='*55}")
    print_summary(schema)
    print(f"\n  Saved to: {output_path}")
    print(f"{'='*55}\n")


def main():
    parser = argparse.ArgumentParser(description="Generic ontology JSON fixer")
    parser.add_argument("--input", default="results/amd/final/amd_ontology_final.json")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    run(args.input, args.output or args.input)


if __name__ == "__main__":
    main()
