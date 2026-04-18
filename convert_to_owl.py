"""
Convert SCHEMA-MINERpro JSON to OWL Ontology
Takes the JSON schema from Stage 3 and creates AMD2.owl file

Usage:
    python convert_to_owl.py <path_to_json_schema>

Example:
    python convert_to_owl.py results_quick_test/stage-3/AMD/llama3.1-8b.json
"""

import json
from rdflib import Graph, Namespace, RDF, RDFS, OWL, Literal, URIRef
from pathlib import Path
import sys


def json_to_owl(json_file, output_owl_file="AMD3.owl"):
    """
    Convert SCHEMA-MINERpro JSON schema to OWL ontology

    Args:
        json_file: Path to final JSON schema (e.g., results/stage-3/AMD/llama3.1-8b.json)
        output_owl_file: Where to save the OWL file (default: AMD2.owl)
    """

    print(f"📂 Loading JSON schema from: {json_file}")

    # Load JSON schema
    with open(json_file, 'r', encoding='utf-8') as f:
        schema = json.load(f)

    # Create RDF graph
    g = Graph()

    # Define namespaces
    AMD = Namespace("http://example.org/amd#")
    g.bind("amd", AMD)
    g.bind("owl", OWL)
    g.bind("rdf", RDF)
    g.bind("rdfs", RDFS)

    print("🏗️  Creating ontology header...")

    # Create ontology header
    ontology_uri = AMD["AMD_Ontology"]
    g.add((ontology_uri, RDF.type, OWL.Ontology))
    g.add((ontology_uri, RDFS.label, Literal("Age-Related Macular Degeneration Ontology")))
    g.add((ontology_uri, RDFS.comment, Literal(
        "AMD ontology auto-generated from research abstracts using SCHEMA-MINERpro and Agentic AI"
    )))
    g.add((ontology_uri, OWL.versionInfo, Literal("1.0")))

    # ===== PROCESS CLASSES =====
    print("\n📦 Processing classes...")

    classes_count = 0
    subclasses_count = 0
    instances_count = 0

    if "classes" in schema:
        for class_name, class_info in schema["classes"].items():
            # Skip procedural/irrelevant classes
            skip_classes = ["SkinBiopsy", "CorticosteroidTreatment", "Procedure"]
            if class_name in skip_classes:
                print(f"   ⏭️  Skipping non-essential class: {class_name}")
                continue

            class_uri = AMD[class_name.replace(" ", "_")]
            g.add((class_uri, RDF.type, OWL.Class))
            g.add((class_uri, RDFS.label, Literal(class_name)))
            classes_count += 1

            if isinstance(class_info, dict):
                # Add description
                if "description" in class_info and class_info["description"]:
                    g.add((class_uri, RDFS.comment, Literal(class_info["description"])))

                # Add subclasses
                if "subclasses" in class_info and class_info["subclasses"]:
                    for subclass_name in class_info["subclasses"]:
                        subclass_uri = AMD[subclass_name.replace(" ", "_")]
                        g.add((subclass_uri, RDF.type, OWL.Class))
                        g.add((subclass_uri, RDFS.subClassOf, class_uri))
                        g.add((subclass_uri, RDFS.label, Literal(subclass_name)))
                        subclasses_count += 1
                        print(f"   ✅ Added subclass: {subclass_name} → {class_name}")

                # Add instances as individuals
                if "instances" in class_info and class_info["instances"]:
                    for instance_name in class_info["instances"]:
                        if not instance_name or instance_name.strip() == "":
                            continue
                        instance_uri = AMD[instance_name.replace(" ", "_")]
                        g.add((instance_uri, RDF.type, class_uri))
                        g.add((instance_uri, RDF.type, OWL.NamedIndividual))
                        g.add((instance_uri, RDFS.label, Literal(instance_name)))
                        instances_count += 1
                        print(f"   ✅ Added instance: {instance_name} as {class_name}")

    # ===== PROCESS PROPERTIES =====
    print("\n🔗 Processing properties...")

    properties_count = 0
    triples_count = 0

    if "properties" in schema:
        for prop_name, prop_info in schema["properties"].items():
            # Skip overly specific or procedural properties
            skip_props = ["involvesSkinBiopsy", "involvesGeneExpression"]
            if any(skip in prop_name for skip in skip_props):
                print(f"   ⏭️  Skipping overly specific property: {prop_name}")
                continue

            prop_uri = AMD[prop_name]
            g.add((prop_uri, RDF.type, OWL.ObjectProperty))
            g.add((prop_uri, RDFS.label, Literal(prop_name)))
            properties_count += 1

            if isinstance(prop_info, dict):
                # Add description
                if "description" in prop_info:
                    g.add((prop_uri, RDFS.comment, Literal(prop_info["description"])))

                # Add domain
                if "domain" in prop_info:
                    domain_uri = AMD[prop_info["domain"].replace(" ", "_")]
                    g.add((prop_uri, RDFS.domain, domain_uri))

                # Add range
                if "range" in prop_info:
                    range_uri = AMD[prop_info["range"].replace(" ", "_")]
                    g.add((prop_uri, RDFS.range, range_uri))

                # Add example triples as assertions
                if "examples" in prop_info and prop_info["examples"]:
                    for example in prop_info["examples"]:
                        if len(example) >= 2:
                            subject_name = str(example[0]).replace(" ", "_")
                            object_name = str(example[2]).replace(" ", "_") if len(example) > 2 else None

                            if object_name and subject_name:
                                subject_uri = AMD[subject_name]
                                object_uri = AMD[object_name]

                                # Create the triple
                                g.add((subject_uri, prop_uri, object_uri))
                                triples_count += 1
                                print(f"   ✅ Added triple: {subject_name} {prop_name} {object_name}")

    # ===== PROCESS INDIVIDUALS =====
    print("\n👥 Processing individuals...")

    individuals_count = 0

    if "individuals" in schema and isinstance(schema["individuals"], dict):
        for category, instances in schema["individuals"].items():
            if isinstance(instances, list) and instances:
                for instance_name in instances:
                    if not instance_name or instance_name.strip() == "":
                        continue
                    instance_uri = AMD[instance_name.replace(" ", "_")]
                    g.add((instance_uri, RDF.type, OWL.NamedIndividual))
                    g.add((instance_uri, RDFS.label, Literal(instance_name)))
                    individuals_count += 1
                    print(f"   ✅ Added individual: {instance_name} ({category})")

    # ===== SAVE OWL FILE =====
    print(f"\n💾 Saving OWL ontology to: {output_owl_file}")

    # Serialize to OWL/XML format
    g.serialize(destination=output_owl_file, format='xml')

    # Also save as Turtle (easier to read)
    turtle_file = output_owl_file.replace('.owl', '.ttl')
    g.serialize(destination=turtle_file, format='turtle')

    # Print statistics
    print("\n" + "=" * 70)
    print("✅ OWL ONTOLOGY CREATED SUCCESSFULLY!")
    print("=" * 70)
    print(f"\n📊 Statistics:")
    print(f"   Total RDF triples: {len(g)}")
    print(f"   Classes: {classes_count}")
    print(f"   Subclasses: {subclasses_count}")
    print(f"   Object Properties: {properties_count}")
    print(f"   Relationship Triples: {triples_count}")
    print(f"   Schema Individuals: {individuals_count}")

    print(f"\n   Files created:")
    print(f"   {output_owl_file} (OWL/XML format)")
    print(f"   {turtle_file} (Turtle format)")

    return output_owl_file


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("🔬 SCHEMA-MINERpro JSON to OWL Converter")
    print("=" * 70 + "\n")

    if len(sys.argv) < 2:
        print("❌ ERROR: Missing JSON schema file path")
        print("\nUsage:")
        print("  python convert_to_owl.py <path_to_json_schema>")
        print("\nExamples:")
        print("  python convert_to_owl.py results/stage-3/AMD/llama3.1-8b.json")
        print("  python convert_to_owl.py results_quick_test/stage-3/AMD/llama3.1-8b.json")
        print("\n💡 Tip: Make sure to run Stages 1-3 first to generate the JSON schema!")
        sys.exit(1)

    json_file = sys.argv[1]

    # Check if file exists
    if not Path(json_file).exists():
        print(f"❌ ERROR: File not found: {json_file}")
        print(f"\n📁 Current directory: {Path.cwd()}")
        print("\n💡 Make sure the path is correct and the file exists.")
        print("   Try using an absolute path if relative path doesn't work.")
        sys.exit(1)

    # Convert to OWL
    try:
        owl_file = json_to_owl(json_file)
        print(f"\n🎉 Success! Open {owl_file} in Protégé to view your AMD ontology!")
    except Exception as e:
        print(f"\n❌ ERROR: Conversion failed!")
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)