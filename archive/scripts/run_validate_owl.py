"""
OWL Validation Script — runs AFTER convert_to_owl.py and enrich_owl.py.
Fixes the final AMD.owl directly. No JSON manipulation, no guessing.

Fixes:
  1. Ensures AMD exists as owl:Class with rdfs:subClassOf Disease
  2. Moves AMD subtypes under AMD (not directly under Disease)
  3. Removes ALL punning (no entity is both owl:Class and owl:NamedIndividual)

Usage:
    python run_validate_owl.py
    python run_validate_owl.py --input AMD.owl --output AMD_validated.owl
"""

import argparse
from rdflib import Graph, Namespace, RDF, RDFS, OWL, Literal

AMD_NS = Namespace("http://example.org/amd#")

# AMD subtypes that should be under AMD, not directly under Disease
AMD_SUBTYPES = {
    "DryAMD", "WetAMD", "GeographicAtrophy", "IntermediateAMD",
    "EarlyAMD", "LateAMD", "NeovascularAMD", "ExudativeAMD",
    "NonExsudativeAMD", "EarlyARM", "LateARM",
    "ChoroidalNeovascularMembrane", "PolypoidalChoroidalVasculopathy",
    "AtrophicMacularDegeneration", "IllDefinedCNV",
    "OcularHistoplasmosisSyndrome", "FeederVessels",
    "PosteriorVitreoMacularAdhesion", "DarkAdaptationDeficiency",
    "ReticularPseudodrusen", "GutMicrobiotaAlteration",
    "PigmentEpithelialDetachment", "ImmunologicalMechanism",
}

# These are NOT AMD subtypes — they are separate diseases associated with AMD.
# They should be under Disease directly, not under AMD.
NOT_AMD_SUBTYPES = {
    "AlzheimersDisease",              # separate neurodegenerative disease
    "Glaucoma",                       # separate eye disease
    "NeovascularGlaucoma",            # glaucoma subtype
    "DepressiveDisorder",             # comorbidity
    "ProliferativeDiabeticRetinopathy",  # diabetic, not AMD
    "MacularEdema",                   # can occur independently
    "PathologicMyopia",               # separate condition
    "PseudoxanthomaElasticum",        # separate genetic disorder
    "RubeosisIridis",                 # separate condition
    "UltrasoundEvaluation",           # diagnostic method, not a disease
}


def fix_amd_hierarchy(g):
    """Ensure Disease -> AMD -> subtypes exists, and misplaced entities are corrected."""
    fixes = []
    disease_uri = AMD_NS["Disease"]
    amd_uri = AMD_NS["AMD"]

    # Ensure Disease is a class
    if (disease_uri, RDF.type, OWL.Class) not in g:
        g.add((disease_uri, RDF.type, OWL.Class))
        g.add((disease_uri, RDFS.label, Literal("Disease")))
        fixes.append("Added Disease as owl:Class")

    # Ensure AMD is a class (NOT just NamedIndividual)
    if (amd_uri, RDF.type, OWL.Class) not in g:
        g.add((amd_uri, RDF.type, OWL.Class))
        fixes.append("Added AMD as owl:Class")

    # Ensure AMD subClassOf Disease
    if (amd_uri, RDFS.subClassOf, disease_uri) not in g:
        g.add((amd_uri, RDFS.subClassOf, disease_uri))
        fixes.append("Added AMD rdfs:subClassOf Disease")

    # Ensure AMD has a label and description
    if (amd_uri, RDFS.label, None) not in g:
        g.add((amd_uri, RDFS.label, Literal("AMD")))
    if (amd_uri, RDFS.comment, None) not in g:
        g.add((amd_uri, RDFS.comment, Literal("Age-related macular degeneration")))

    # Move entities that are NOT AMD subtypes: AMD -> entity becomes Disease -> entity
    for entity_name in NOT_AMD_SUBTYPES:
        entity_uri = AMD_NS[entity_name]
        if (entity_uri, RDFS.subClassOf, amd_uri) in g:
            g.remove((entity_uri, RDFS.subClassOf, amd_uri))
            if (entity_uri, RDFS.subClassOf, disease_uri) not in g:
                g.add((entity_uri, RDFS.subClassOf, disease_uri))
            fixes.append(f"Moved {entity_name}: AMD -> Disease (not an AMD subtype)")

    # Move AMD subtypes: Disease -> subtype becomes AMD -> subtype
    for subtype_name in AMD_SUBTYPES:
        subtype_uri = AMD_NS[subtype_name]
        # Check if this subtype is directly under Disease
        if (subtype_uri, RDFS.subClassOf, disease_uri) in g:
            # Remove direct link to Disease
            g.remove((subtype_uri, RDFS.subClassOf, disease_uri))
            # Add link to AMD instead
            if (subtype_uri, RDFS.subClassOf, amd_uri) not in g:
                g.add((subtype_uri, RDFS.subClassOf, amd_uri))
                fixes.append(f"Moved {subtype_name}: Disease -> AMD")

    return fixes


def fix_punning(g):
    """Remove owl:NamedIndividual from any entity that is also owl:Class."""
    fixes = []
    for entity in list(g.subjects(RDF.type, OWL.Class)):
        if (entity, RDF.type, OWL.NamedIndividual) in g:
            name = str(entity).split('#')[-1]
            if 'abstract_' not in name:
                g.remove((entity, RDF.type, OWL.NamedIndividual))
                fixes.append(f"Removed NamedIndividual from class: {name}")
    return fixes


def print_summary(g):
    classes = set(g.subjects(RDF.type, OWL.Class))
    props = set(g.subjects(RDF.type, OWL.ObjectProperty))
    all_ind = set(g.subjects(RDF.type, OWL.NamedIndividual))
    abstracts = [s for s in all_ind if 'abstract_' in str(s)]
    schema_ind = [s for s in all_ind if 'abstract_' not in str(s)]

    # Check punning
    punning = []
    for s in classes:
        if (s, RDF.type, OWL.NamedIndividual) in g:
            name = str(s).split('#')[-1]
            if 'abstract_' not in name:
                punning.append(name)

    # Check hierarchy
    amd_uri = AMD_NS["AMD"]
    disease_uri = AMD_NS["Disease"]
    amd_is_class = (amd_uri, RDF.type, OWL.Class) in g
    amd_under_disease = (amd_uri, RDFS.subClassOf, disease_uri) in g
    amd_subs = [str(s).split('#')[-1] for s in g.subjects(RDFS.subClassOf, amd_uri)]

    print(f"\n  Classes           : {len(classes)}")
    print(f"  Object Properties : {len(props)}")
    print(f"  Schema Individuals: {len(schema_ind)}")
    print(f"  Abstract Instances: {len(abstracts)}")
    print(f"  AMD is class      : {amd_is_class}")
    print(f"  AMD under Disease : {amd_under_disease}")
    print(f"  AMD subtypes      : {len(amd_subs)}")
    print(f"  Punning           : {len(punning)} {'- ' + str(punning[:5]) if punning else '- NONE'}")


def run(input_path: str, output_path: str):
    g = Graph()
    g.parse(input_path)

    print(f"\nLoaded: {input_path}")
    print_summary(g)

    all_fixes = []

    print("\n── Fix 1: AMD hierarchy ──")
    fixes = fix_amd_hierarchy(g)
    all_fixes.extend(fixes)
    for f in fixes:
        print(f"  {f}")
    if not fixes:
        print("  Already correct")

    print("\n── Fix 2: Punning ──")
    fixes = fix_punning(g)
    all_fixes.extend(fixes)
    for f in fixes:
        print(f"  {f}")
    if not fixes:
        print("  No punning found")

    # Save
    g.serialize(destination=output_path, format='xml')

    print(f"\n{'='*55}")
    print(f"  {len(all_fixes)} fixes applied")
    print(f"{'='*55}")
    print_summary(g)
    print(f"\n  Saved to: {output_path}")
    print(f"{'='*55}\n")


def main():
    parser = argparse.ArgumentParser(description="Validate AMD OWL — fix hierarchy + punning")
    parser.add_argument("--input", default="AMD.owl")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    run(args.input, args.output or args.input)


if __name__ == "__main__":
    main()
