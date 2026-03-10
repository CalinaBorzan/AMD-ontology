import json

with open('data/abstracts_metadata.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

print("\n📄 ABSTRACT INSTANCES FOR DL-LEARNER:\n")
print("=" * 70)

wet_amd = []
dry_amd = []
unknown = []

for d in data:
    text_lower = d['text'].lower()
    abstract_id = d['id']
    
    # Check for WetAMD keywords
    if any(k in text_lower for k in ['wet amd', 'neovascular', 'cnv', 'ranibizumab', 'lucentis', 'anti-vegf', 'bevacizumab']):
        wet_amd.append(abstract_id)
        print(f"✅ WetAMD: {abstract_id}")
    # Check for DryAMD keywords
    elif any(k in text_lower for k in ['dry amd', 'drusen', 'geographic atrophy', 'non-exudative']):
        dry_amd.append(abstract_id)
        print(f"✅ DryAMD: {abstract_id}")
    else:
        unknown.append(abstract_id)
        print(f"⚪ Unknown: {abstract_id}")

print("\n" + "=" * 70)
print(f"\n📊 SUMMARY:")
print(f"   WetAMD instances: {len(wet_amd)}")
print(f"   DryAMD instances: {len(dry_amd)}")
print(f"   Unknown: {len(unknown)}")

print("\n💡 FOR DL-LEARNER CONFIG:\n")
print("lp.positiveExamples = {")
for i, abstract_id in enumerate(wet_amd[:5]):
    comma = "," if i < min(4, len(wet_amd)-1) else ""
    print(f'    "amd:abstract_{abstract_id}"{comma}')
print("}")

print("\nlp.negativeExamples = {")
for i, abstract_id in enumerate(dry_amd[:5]):
    comma = "," if i < min(4, len(dry_amd)-1) else ""
    print(f'    "amd:abstract_{abstract_id}"{comma}')
print("}")