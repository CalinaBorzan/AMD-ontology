"""
Normalize schema JSON format — fixes format inconsistencies from different LLMs.

Converts:
  - subclasses as dicts {"AMD": {}} → lists ["AMD"]
  - individuals as dicts {"Ranibizumab": {}} → lists ["Ranibizumab"]
  - classes as lists ["Disease", "AMD"] → dicts with descriptions
  - extra fields in classes (features, riskFactorFor, etc.) → removed, kept only description + subclasses

Run before post-processing:
    python run_normalize_schema_format.py
    python run_normalize_schema_format.py --input results/amd/stage-3/AMD/llama3.3-70b.json --output results/amd/final/amd_ontology_final.json
"""

import argparse
import json
from pathlib import Path


def normalize_classes(schema: dict) -> tuple[dict, list[str]]:
    """Normalize classes to the expected format: dict with description + subclasses list."""
    fixes = []
    classes = schema.get("classes", {})

    # Case 1: classes is a flat list ["Disease", "AMD", ...]
    if isinstance(classes, list):
        new_classes = {}
        for name in classes:
            if isinstance(name, str):
                new_classes[name] = {"description": name, "subclasses": []}
            elif isinstance(name, dict) and "name" in name:
                n = name["name"]
                new_classes[n] = {
                    "description": name.get("description", n),
                    "subclasses": name.get("subtypes", name.get("subclasses", []))
                }
        schema["classes"] = new_classes
        fixes.append(f"  Converted classes from list ({len(new_classes)} items) to dict format")
        classes = new_classes

    # Case 2: classes is a dict — normalize each entry
    for class_name, class_data in list(classes.items()):
        if not isinstance(class_data, dict):
            classes[class_name] = {"description": str(class_data), "subclasses": []}
            fixes.append(f"  Fixed class '{class_name}' — was not a dict")
            continue

        # Fix subclasses: dict {"AMD": {}} → list ["AMD"]
        subclasses = class_data.get("subclasses", [])
        if isinstance(subclasses, dict):
            class_data["subclasses"] = list(subclasses.keys())
            fixes.append(f"  Fixed '{class_name}'.subclasses — dict → list ({len(subclasses)} items)")

        # Fix subtypes field used instead of subclasses
        if "subtypes" in class_data and "subclasses" not in class_data:
            subtypes = class_data.pop("subtypes")
            if isinstance(subtypes, dict):
                class_data["subclasses"] = list(subtypes.keys())
            elif isinstance(subtypes, list):
                class_data["subclasses"] = [s["name"] if isinstance(s, dict) else s for s in subtypes]
            fixes.append(f"  Fixed '{class_name}' — renamed 'subtypes' to 'subclasses'")

        # Remove extra fields — keep only description and subclasses
        allowed_fields = {"description", "subclasses"}
        extra_fields = set(class_data.keys()) - allowed_fields
        if extra_fields:
            for field in extra_fields:
                del class_data[field]
            fixes.append(f"  Cleaned '{class_name}' — removed extra fields: {extra_fields}")

        # Ensure description exists
        if "description" not in class_data:
            class_data["description"] = class_name

        # Ensure subclasses exists as list
        if "subclasses" not in class_data:
            class_data["subclasses"] = []

    return schema, fixes


def normalize_properties(schema: dict) -> tuple[dict, list[str]]:
    """Normalize properties to the expected format: dict with domain, range, description."""
    fixes = []
    props = schema.get("properties", {})

    # Case 1: properties is a list
    if isinstance(props, list):
        new_props = {}
        for p in props:
            if isinstance(p, dict) and "name" in p:
                name = p.pop("name")
                new_props[name] = p
        schema["properties"] = new_props
        fixes.append(f"  Converted properties from list ({len(new_props)} items) to dict format")
        props = new_props

    # Case 2: "relationships" used instead of "properties"
    if "relationships" in schema and "properties" not in schema:
        schema["properties"] = schema.pop("relationships")
        fixes.append("  Renamed 'relationships' to 'properties'")
    elif "relationships" in schema:
        # Merge relationships into properties
        rels = schema.pop("relationships")
        if isinstance(rels, dict):
            for key, val in rels.items():
                if key not in props:
                    props[key] = val
            fixes.append(f"  Merged 'relationships' into 'properties' ({len(rels)} items)")

    # Normalize each property
    for prop_name, prop_data in list(props.items()):
        if isinstance(prop_data, dict):
            # Fix range if it's a list
            if isinstance(prop_data.get("range"), list):
                prop_data["range"] = prop_data["range"][0] if prop_data["range"] else "Thing"
                fixes.append(f"  Fixed '{prop_name}'.range — was a list, took first element")

    return schema, fixes


def normalize_individuals(schema: dict) -> tuple[dict, list[str]]:
    """Normalize individuals to the expected format: dict of lists."""
    fixes = []
    individuals = schema.get("individuals", {})

    # Case 1: individuals is a flat list
    if isinstance(individuals, list):
        new_ind = {}
        for item in individuals:
            if isinstance(item, dict) and "name" in item and "type" in item:
                parent = item["type"]
                if parent not in new_ind:
                    new_ind[parent] = []
                new_ind[parent].append(item["name"])
            elif isinstance(item, str):
                if "Uncategorized" not in new_ind:
                    new_ind["Uncategorized"] = []
                new_ind["Uncategorized"].append(item)
        schema["individuals"] = new_ind
        fixes.append(f"  Converted individuals from flat list to grouped dict ({len(new_ind)} groups)")
        individuals = new_ind

    # Case 2: individuals values are dicts {"Ranibizumab": {}} → lists ["Ranibizumab"]
    for parent, ind_data in list(individuals.items()):
        if isinstance(ind_data, dict):
            individuals[parent] = list(ind_data.keys())
            fixes.append(f"  Fixed '{parent}' individuals — dict → list ({len(ind_data)} items)")
        elif not isinstance(ind_data, list):
            individuals[parent] = []
            fixes.append(f"  Fixed '{parent}' individuals — was {type(ind_data).__name__}, set to empty list")

    # Remove empty individual groups
    empty = [k for k, v in individuals.items() if not v]
    for k in empty:
        del individuals[k]
    if empty:
        fixes.append(f"  Removed {len(empty)} empty individual groups")

    return schema, fixes


def print_summary(schema: dict):
    classes = schema.get("classes", {})
    properties = schema.get("properties", {})
    individuals = schema.get("individuals", {})
    total_ind = sum(len(v) for v in individuals.values()) if isinstance(individuals, dict) else 0
    total_subs = sum(len(c.get("subclasses", [])) for c in classes.values()) if isinstance(classes, dict) else 0

    print(f"\n  Classes      : {len(classes)}")
    print(f"  Subclasses   : {total_subs}")
    print(f"  Properties   : {len(properties)}")
    print(f"  Individuals  : {total_ind} (across {len(individuals)} groups)")

    # Verify format
    format_ok = True
    if isinstance(classes, dict):
        for name, data in classes.items():
            if not isinstance(data.get("subclasses", []), list):
                print(f"  FORMAT ERROR: {name}.subclasses is not a list!")
                format_ok = False
    if isinstance(individuals, dict):
        for name, data in individuals.items():
            if not isinstance(data, list):
                print(f"  FORMAT ERROR: individuals.{name} is not a list!")
                format_ok = False
    if format_ok:
        print("  Format       : ALL CORRECT ✓")


def run(input_path: str, output_path: str):
    with open(input_path, encoding="utf-8") as f:
        schema = json.load(f)

    print(f"\nLoaded schema from: {input_path}")
    all_fixes = []

    print("\n── Normalizing classes ──")
    schema, fixes = normalize_classes(schema)
    all_fixes.extend(fixes)
    for f in fixes: print(f)
    if not fixes: print("  Classes format OK ✓")

    print("\n── Normalizing properties ──")
    schema, fixes = normalize_properties(schema)
    all_fixes.extend(fixes)
    for f in fixes: print(f)
    if not fixes: print("  Properties format OK ✓")

    print("\n── Normalizing individuals ──")
    schema, fixes = normalize_individuals(schema)
    all_fixes.extend(fixes)
    for f in fixes: print(f)
    if not fixes: print("  Individuals format OK ✓")

    # Save
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(schema, f, indent=4, ensure_ascii=False)

    print(f"\n{'='*55}")
    print(f"  SUMMARY — {len(all_fixes)} format fixes applied")
    print(f"{'='*55}")
    print_summary(schema)
    print(f"\n  Saved to: {output_path}")
    print(f"{'='*55}\n")


def main():
    parser = argparse.ArgumentParser(description="Normalize schema JSON format — fixes dict/list inconsistencies from different LLMs")
    parser.add_argument("--input", default="results/amd/final/amd_ontology_final.json",
                        help="Input schema JSON")
    parser.add_argument("--output", default=None,
                        help="Output path (default: overwrites input)")
    args = parser.parse_args()
    output = args.output or args.input
    run(args.input, output)


if __name__ == "__main__":
    main()
