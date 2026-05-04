import re
from pathlib import Path
from rdflib import Graph, Namespace, RDF, RDFS, OWL, Literal

AMD = Namespace("http://example.org/amd#")

TREATMENT_CLASSES = {"AntiVEGFTherapy","SurgicalTherapy","SupplementTherapy","EmergingTherapy","SteroidTherapy","TranspupillaryThermotherapy","Ellex2RTLaser","StereotacticRadiosurgery","NightTimeLightTherapy","IntraocularLensImplantation","PulseDiodeLaserPhotocoagulation","OculomotorTraining","PhotodynamicTherapy","Rheohemapheresis","CNTFImplantTherapy","CopaxoneTherapy","ISONEPTherapy","LowVisionRehabilitation","PreferredRetinalLocusTraining","EccentricViewingTraining","ClosedCircuitTelevision","AntiTNFTherapy"}
GENE_CLASSES = {"RiskGenes","MolecularTargets","GeneticVariants"}
BIOMARKER_CLASSES = {"StructuralBiomarkers","FunctionalBiomarkers"}
DIAGNOSTIC_CLASSES = {"ImagingMethods","FunctionalMethods"}
RISK_CLASSES = {"NonModifiableRiskFactors","ModifiableRiskFactors"}
OUTCOME_CLASSES = {"PrimaryOutcomes","SecondaryOutcomes"}

NEW_PROPS = [(AMD.involvesTreatment,"Links an abstract to a treatment mentioned in it"),(AMD.involvesGene,"Links an abstract to a gene mentioned in it"),(AMD.involvesBiomarker,"Links an abstract to a biomarker mentioned in it"),(AMD.involvesDiagnosticMethod,"Links an abstract to a diagnostic method mentioned in it"),(AMD.involvesRiskFactor,"Links an abstract to a risk factor mentioned in it"),(AMD.involvesOutcome,"Links an abstract to a clinical outcome mentioned in it"),]

SKIP_LABELS = {"amd","age","diet","loc"}

ALIASES = {'Ranibizumab': ['ranibizumab', 'lucentis'], 'Aflibercept': ['aflibercept', 'eylea'], 'Bevacizumab': ['bevacizumab', 'avastin'], 'Verteporfin': ['verteporfin'], 'SqualamineLactate': ['squalamine lactate', 'squalamine'], 'PhotodynamicTherapy': ['photodynamic therapy', 'pdt'], 'LaserPhotocoagulation': ['laser photocoagulation'], 'SubmacularSurgery': ['submacular surgery'], 'TransparsPlanavitrectomy': ['pars plana vitrectomy', 'vitrectomy'], 'TranspupillaryThermotherapy': ['transpupillary thermotherapy', 'ttt'], 'StereotacticRadiosurgery': ['stereotactic radiosurgery'], 'Sirolimus': ['sirolimus', 'rapamycin'], 'Copaxone': ['copaxone', 'glatiramer'], 'Infliximab': ['infliximab', 'remicade'], 'AREDS': ['areds', 'age-related eye disease study'], 'GeneTherapy': ['gene therapy'], 'StemCellTherapy': ['stem cell therapy', 'stem cell'], 'ComplementInhibitors': ['complement inhibitor'], 'CNTFImplant': ['cntf implant', 'ciliary neurotrophic factor'], 'OCT': ['optical coherence tomography', 'oct'], 'FluoresceinAngiography': ['fluorescein angiography'], 'FundusAutofluorescence': ['fundus autofluorescence', 'faf'], 'ICGA': ['indocyanine green angiography', 'icga'], 'FundusPhotography': ['fundus photography'], 'Electroretinography': ['electroretinography', 'erg'], 'HeterochromaticFlickerPhotometry': ['heterochromatic flicker photometry', 'hfp'], 'VisualFieldTesting': ['visual field', 'perimetry'], 'CFH': ['cfh', 'complement factor h'], 'VEGF': ['vegf', 'vascular endothelial growth factor'], 'ARMS2': ['arms2'], 'HTRA1': ['htra1'], 'C3': ['complement c3'], 'CFB': ['complement factor b', 'cfb'], 'PDGF': ['pdgf', 'platelet-derived growth factor'], 'TNF-alpha': ['tnf-alpha', 'tnf alpha', 'tumor necrosis factor'], 'ComplementPathwayProteins': ['complement pathway', 'complement system'], 'Drusen': ['drusen'], 'SubretinalFluid': ['subretinal fluid'], 'RetinalThickness': ['retinal thickness'], 'ChoroidalThickness': ['choroidal thickness'], 'Lipofuscin': ['lipofuscin'], 'ReticularPseudodrusen': ['reticular pseudodrusen', 'pseudodrusen'], 'PigmentEpithelialDetachment': ['pigment epithelial detachment', 'ped'], 'MacularPigmentOpticalDensity': ['macular pigment optical density', 'mpod', 'macular pigment'], 'VisualAcuity': ['visual acuity', 'best corrected visual acuity', 'bcva', 'etdrs'], 'ContrastSensitivity': ['contrast sensitivity'], 'ReadingSpeed': ['reading speed'], 'DarkAdaptation': ['dark adaptation'], 'Smoking': ['smoking', 'cigarette', 'tobacco'], 'Hypertension': ['hypertension', 'high blood pressure'], 'Hypotension': ['hypotension', 'low blood pressure'], 'CardiovascularDisease': ['cardiovascular disease', 'cardiovascular'], 'BMI': ['bmi', 'body mass index', 'obesity'], 'SunExposure': ['sun exposure', 'sunlight', 'uv exposure'], 'GutMicrobiotaAlteration': ['gut microbiota', 'microbiome'], 'VisualAcuityChange': ['visual acuity change', 'vision loss', 'vision gain'], 'LesionSizeChange': ['lesion size'], 'CNVRegression': ['cnv regression'], 'QualityOfLifeChange': ['quality of life', 'qol'], 'ProgressionToLateAMD': ['progression to late amd', 'disease progression'], 'ChoroidalThicknessChange': ['choroidal thickness change'], 'DarkAdaptationChange': ['dark adaptation change']}


def camel_to_words(name):
    s = re.sub(r"([A-Z][a-z]+)", r" \1", name)
    s = re.sub(r"([A-Z]+)(?=[A-Z][a-z])", r" \1", s)
    return s.strip().lower()


def build_entity_map(g):
    entity_map = {}
    for ind in g.subjects(RDF.type, OWL.NamedIndividual):
        if "abstract_" in str(ind):
            continue
        label = g.value(ind, RDFS.label)
        if not label:
            continue
        label_str = str(label)
        if label_str.lower() in SKIP_LABELS:
            continue
        types = {str(t).split("#")[-1] for t in g.objects(ind, RDF.type) if t != OWL.NamedIndividual}
        if types & TREATMENT_CLASSES: prop = AMD.involvesTreatment
        elif types & GENE_CLASSES: prop = AMD.involvesGene
        elif types & BIOMARKER_CLASSES: prop = AMD.involvesBiomarker
        elif types & DIAGNOSTIC_CLASSES: prop = AMD.involvesDiagnosticMethod
        elif types & RISK_CLASSES: prop = AMD.involvesRiskFactor
        elif types & OUTCOME_CLASSES: prop = AMD.involvesOutcome
        else: continue
        terms = set()
        terms.add(label_str.lower())
        terms.add(camel_to_words(label_str))
        if label_str in ALIASES: terms.update(ALIASES[label_str])
        for term in terms:
            term = term.strip()
            if term and len(term) >= 3:
                entity_map[term] = (ind, prop)
    return entity_map


def find_mentions(text, entity_map):
    text_lower = text.lower()
    found = []
    seen_uris = set()
    for term, (uri, prop) in sorted(entity_map.items(), key=lambda x: -len(x[0])):
        pattern = r"\b" + re.escape(term) + r"\b"
        if re.search(pattern, text_lower) and uri not in seen_uris:
            found.append((uri, prop))
            seen_uris.add(uri)
    return found


def main():
    owl_file = "AMD.owl"
    abstracts_dir = Path("data/stage-3/AMD/abstracts")
    print("AMD OWL Enrichment")
    g = Graph()
    g.parse(owl_file)
    g.bind("amd", AMD)
    print(f"Loaded {len(g)} triples")
    for prop_uri, desc in NEW_PROPS:
        g.add((prop_uri, RDF.type, OWL.ObjectProperty))
        g.add((prop_uri, RDFS.label, Literal(str(prop_uri).split("#")[-1])))
        g.add((prop_uri, RDFS.comment, Literal(desc)))
    entity_map = build_entity_map(g)
    print(f"{len(entity_map)} searchable terms")
    abstract_files = sorted(abstracts_dir.glob("*.txt"))
    print(f"Processing {len(abstract_files)} abstracts")
    total_new_triples = 0
    enriched_count = 0
    for abstract_file in abstract_files:
        stem = abstract_file.stem
        abstract_id = stem.replace("abstract_", "")
        ind_uri = AMD[f"abstract_{abstract_id}"]
        if (ind_uri, RDF.type, OWL.NamedIndividual) not in g:
            print(f"SKIP {stem}")
            continue
        text = abstract_file.read_text(encoding="utf-8", errors="ignore")
        mentions = find_mentions(text, entity_map)
        for entity_uri, prop_uri in mentions:
            g.add((ind_uri, prop_uri, entity_uri))
            total_new_triples += 1
        if mentions:
            enriched_count += 1
            labels = [str(g.value(e, RDFS.label)) for e, _ in mentions]
            suffix = " ..." if len(mentions) > 6 else ""
            print(f"{stem}: {len(mentions)} links -> {labels[:6]}{suffix}")
        else:
            print(f"{stem}: no entities found")
    print(f"Enriched: {enriched_count}/{len(abstract_files)}")
    print(f"New triples: {total_new_triples}, Total: {len(g)}")
    g.serialize(destination=owl_file, format="xml")
    g.serialize(destination=owl_file.replace(".owl", ".ttl"), format="turtle")
    print("Done.")


if __name__ == "__main__":
    main()
