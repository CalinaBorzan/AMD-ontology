"""
Simple data preparation for SCHEMA-MINERpro using abstracts_with_id.json
NOW WITH SUPPORT FOR ABSTRACT IDs FOR DL-LEARNER INSTANCES!
"""

import json
from pathlib import Path


def load_abstracts_from_file(filepath):
    """
    Load abstracts from abstracts_with_id.json file.
    Returns list of dicts with 'id' and 'text' fields.
    """
    abstracts = []

    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Extract id and text from each abstract
    for item in data:
        if isinstance(item, dict) and 'text' in item and 'id' in item:
            text = item['text']
            abstract_id = item['id']
            if text and text.strip():
                abstracts.append({
                    'id': abstract_id,
                    'text': text.strip()
                })

    return abstracts


def save_abstracts_metadata(abstracts, output_dir):
    """
    Save abstracts WITH their IDs for later instance creation in OWL
    """
    metadata_file = Path(output_dir) / "abstracts_metadata.json"

    with open(metadata_file, 'w', encoding='utf-8') as f:
        json.dump(abstracts, f, indent=2, ensure_ascii=False)

    print(f"✓ Saved abstracts metadata with IDs: {metadata_file}")
    return metadata_file


def create_domain_specification():
    """Create AMD domain specification document"""
    return """# Age-Related Macular Degeneration (AMD) Domain Specification

## Overview
Age-Related Macular Degeneration (AMD) is a progressive eye disease affecting the macula, 
the central part of the retina. It is the leading cause of vision loss in people over 60.

## Key Concepts

### Disease Types
- Dry AMD (Geographic Atrophy): Drusen deposits and gradual cell breakdown
- Wet AMD (Neovascular): Abnormal blood vessel growth beneath retina

### Pathological Features
- Drusen: Yellow deposits under retina
- Geographic Atrophy: Retinal cell death areas
- Choroidal Neovascularization (CNV): Abnormal vessel growth
- Retinal Pigment Epithelium (RPE) dysfunction

### Key Genes and Biomarkers
- Complement genes: CFH, C3, C2, CFB
- ARMS2/HTRA1
- VEGF (Vascular Endothelial Growth Factor)

### Treatments
- Anti-VEGF therapy: Ranibizumab, Aflibercept, Bevacizumab
- Photodynamic therapy: Verteporfin
- AREDS/AREDS2 supplements
- Laser therapy

### Diagnostic Methods
- Optical Coherence Tomography (OCT)
- Fundus Photography
- Fluorescein Angiography
- Visual Acuity Tests

## Research Areas
- Disease mechanisms and causation
- Novel treatments
- Biomarker discovery
- Genetic associations
- Prevention strategies
- Diagnostic improvements
"""


def prepare_data(abstracts_file, output_dir="./data"):
    """
    Prepare data for SCHEMA-MINERpro from abstracts_with_id.json
    """
    print(f"\n=== AMD Data Preparation for SCHEMA-MINERpro ===\n")
    print(f"Loading abstracts from: {abstracts_file}")

    try:
        abstracts = load_abstracts_from_file(abstracts_file)
    except FileNotFoundError:
        print(f"\nERROR: File '{abstracts_file}' not found!")
        print("Please make sure abstracts_with_id.json is in the same directory.")
        return
    except Exception as e:
        print(f"\nERROR: Failed to load abstracts: {e}")
        return

    print(f"Found {len(abstracts)} abstracts with IDs")

    if len(abstracts) == 0:
        print("ERROR: No abstracts found in file!")
        return

    # Show first abstract preview
    first_abstract = abstracts[0]
    print(f"\nFirst abstract:")
    print(f"  ID: {first_abstract['id']}")
    print(f"  Text preview (first 150 chars): {first_abstract['text'][:150]}...\n")

    # Create directory structure
    stage1_dir = Path(output_dir) / "stage-1" / "AMD"
    stage2_dir = Path(output_dir) / "stage-2" / "AMD" / "abstracts"
    stage3_dir = Path(output_dir) / "stage-3" / "AMD" / "abstracts"

    stage1_dir.mkdir(parents=True, exist_ok=True)
    stage2_dir.mkdir(parents=True, exist_ok=True)
    stage3_dir.mkdir(parents=True, exist_ok=True)

    # SAVE METADATA FILE (for convert_to_owl.py to create instances)
    save_abstracts_metadata(abstracts, output_dir)

    # Stage 1: Domain specification
    domain_spec = create_domain_specification()
    with open(stage1_dir / "amd_domain_spec.txt", "w", encoding="utf-8") as f:
        f.write(domain_spec)
    print(f"✓ Created domain specification: {stage1_dir / 'amd_domain_spec.txt'}")

    # Stage 2: Small curated corpus (first 20 abstracts)
    stage2_count = min(20, len(abstracts))
    for i in range(stage2_count):
        # Use abstract ID in filename
        abstract_id = abstracts[i]['id']
        filename = f"abstract_{abstract_id}.txt"
        with open(stage2_dir / filename, "w", encoding="utf-8") as f:
            f.write(abstracts[i]['text'])
    print(f"✓ Created Stage 2 corpus: {stage2_count} abstracts in {stage2_dir}")

    # Stage 3: Full corpus (all abstracts)
    for abstract in abstracts:
        abstract_id = abstract['id']
        filename = f"abstract_{abstract_id}.txt"
        with open(stage3_dir / filename, "w", encoding="utf-8") as f:
            f.write(abstract['text'])
    print(f"✓ Created Stage 3 corpus: {len(abstracts)} abstracts in {stage3_dir}")

    print("\n=== Summary ===")
    print(f"Total abstracts: {len(abstracts)}")
    print(f"Stage 1 (Domain Spec): {stage1_dir}")
    print(f"Stage 2 (Small Corpus): {stage2_dir} - {stage2_count} abstracts")
    print(f"Stage 3 (Full Corpus): {stage3_dir} - {len(abstracts)} abstracts")
    print(f"Metadata (for OWL instances): {output_dir}/abstracts_metadata.json")
    print("\n✓ Data preparation complete!")
    print("\nNext steps:")
    print("1. Make sure you have installed: pip install schema-miner")
    print("2. Run: python run_schema_miner_amd_quick.py")
    print("3. Run: python convert_to_owl.py results_quick_test/stage-3/AMD/llama3.1-8b.json")
    print("\n💡 The abstracts_metadata.json will be used by convert_to_owl.py")
    print("   to create instances with real abstract IDs for DL-Learner!")


if __name__ == "__main__":
    import sys

    # Allow specifying file as command line argument
    if len(sys.argv) > 1:
        abstracts_file = sys.argv[1]
    else:
        abstracts_file = "abstracts_with_id.json"
    
    prepare_data(abstracts_file)