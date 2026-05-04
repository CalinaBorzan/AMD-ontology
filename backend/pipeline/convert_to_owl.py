import json
import sys
from datetime import datetime
from pathlib import Path

from rdflib import Graph, Namespace, RDF, RDFS, OWL, Literal


def json_to_owl(json_file, output_owl_file=None):
    if output_owl_file is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        ontology_dir = Path("ontology")
        ontology_dir.mkdir(parents=True, exist_ok=True)
        output_owl_file = str(ontology_dir / f"AMD_{timestamp}.owl")

    if Path(output_owl_file).exists():
        raise FileExistsError(
            f"'{output_owl_file}' already exists. Pass a different output "
            f"path as the second argument, or delete it first."
        )

    with open(json_file, "r", encoding="utf-8") as f:
        schema = json.load(f)

    g = Graph()
    AMD = Namespace("http://example.org/amd#")
    g.bind("amd", AMD)
    g.bind("owl", OWL)
    g.bind("rdf", RDF)
    g.bind("rdfs", RDFS)

    ontology_uri = AMD["AMD_Ontology"]
    g.add((ontology_uri, RDF.type, OWL.Ontology))
    g.add((ontology_uri, RDFS.label, Literal("Age-Related Macular Degeneration Ontology")))
    g.add((ontology_uri, RDFS.comment, Literal(
        "AMD ontology auto-generated from research abstracts using SCHEMA-MINERpro and Agentic AI"
    )))
    g.add((ontology_uri, OWL.versionInfo, Literal("1.0")))

    # Disjoint groups are declarative — extended in the JSON without touching this converter.
    for group in schema.get("disjoint_groups", []):
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                g.add((AMD[a.replace(" ", "_")], OWL.disjointWith,
                       AMD[b.replace(" ", "_")]))

    classes_count = 0
    subclasses_count = 0
    instances_count = 0

    for class_name, class_info in schema.get("classes", {}).items():
        class_uri = AMD[class_name.replace(" ", "_")]
        g.add((class_uri, RDF.type, OWL.Class))
        g.add((class_uri, RDFS.label, Literal(class_name)))
        classes_count += 1

        if not isinstance(class_info, dict):
            continue

        if class_info.get("description"):
            g.add((class_uri, RDFS.comment, Literal(class_info["description"])))

        for subclass_name in class_info.get("subclasses") or []:
            subclass_uri = AMD[subclass_name.replace(" ", "_")]
            g.add((subclass_uri, RDF.type, OWL.Class))
            g.add((subclass_uri, RDFS.subClassOf, class_uri))
            g.add((subclass_uri, RDFS.label, Literal(subclass_name)))
            subclasses_count += 1

        for instance_name in class_info.get("instances") or []:
            if not instance_name or not instance_name.strip():
                continue
            instance_uri = AMD[instance_name.replace(" ", "_")]
            g.add((instance_uri, RDF.type, class_uri))
            g.add((instance_uri, RDF.type, OWL.NamedIndividual))
            g.add((instance_uri, RDFS.label, Literal(instance_name)))
            instances_count += 1

    properties_count = 0
    triples_count = 0

    for prop_name, prop_info in schema.get("properties", {}).items():
        prop_uri = AMD[prop_name]
        g.add((prop_uri, RDF.type, OWL.ObjectProperty))
        g.add((prop_uri, RDFS.label, Literal(prop_name)))
        properties_count += 1

        if not isinstance(prop_info, dict):
            continue

        if "description" in prop_info:
            g.add((prop_uri, RDFS.comment, Literal(prop_info["description"])))

        if "domain" in prop_info:
            g.add((prop_uri, RDFS.domain, AMD[prop_info["domain"].replace(" ", "_")]))

        if "range" in prop_info:
            g.add((prop_uri, RDFS.range, AMD[prop_info["range"].replace(" ", "_")]))

        for example in prop_info.get("examples") or []:
            if len(example) < 3:
                continue
            subject_name = str(example[0]).replace(" ", "_")
            object_name = str(example[2]).replace(" ", "_")
            if subject_name and object_name:
                g.add((AMD[subject_name], prop_uri, AMD[object_name]))
                triples_count += 1

    individuals_count = 0

    if isinstance(schema.get("individuals"), dict):
        for instances in schema["individuals"].values():
            if not isinstance(instances, list):
                continue
            for instance_name in instances:
                if not instance_name or not instance_name.strip():
                    continue
                instance_uri = AMD[instance_name.replace(" ", "_")]
                g.add((instance_uri, RDF.type, OWL.NamedIndividual))
                g.add((instance_uri, RDFS.label, Literal(instance_name)))
                individuals_count += 1

    g.serialize(destination=output_owl_file, format="xml")
    turtle_file = output_owl_file.replace(".owl", ".ttl")
    g.serialize(destination=turtle_file, format="turtle")

    print(f"OWL: {output_owl_file}")
    print(f"TTL: {turtle_file}")
    print(
        f"Triples: {len(g)} | Classes: {classes_count} | Subclasses: {subclasses_count} | "
        f"Properties: {properties_count} | Relations: {triples_count} | Individuals: {individuals_count}"
    )

    return output_owl_file


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python convert_to_owl.py <json_schema> [output.owl]")
        sys.exit(1)

    json_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) >= 3 else None

    if not Path(json_file).exists():
        print(f"File not found: {json_file}")
        sys.exit(1)

    json_to_owl(json_file, output_file)
