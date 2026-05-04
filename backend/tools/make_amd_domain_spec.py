import json
from json import JSONDecodeError


def _get_text_from_item(item):
    """Return the main text for an item, trying common keys.

    Handles dicts with keys like 'text' or 'abstract', and tolerates
    strings or nested structures.
    """
    if item is None:
        return ""
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        for key in ("abstract", "text", "description", "summary"):
            if key in item and item[key]:
                val = item[key]
                if isinstance(val, list):
                    return "\n\n".join(str(x) for x in val)
                return str(val)
        # try to find any string value
        for v in item.values():
            if isinstance(v, str) and v.strip():
                return v
    return ""


def _load_json_file(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except JSONDecodeError:
        # fallback: try reading as newline-delimited JSON or plain text
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read().strip()
        try:
            return json.loads(text)
        except Exception:
            return []


def main():
    abstracts = _load_json_file("abstracts_with_id.json") or []
    ann = _load_json_file("abstracts.json") or []

    all_texts = []

    for item in abstracts:
        t = _get_text_from_item(item)
        if t:
            all_texts.append(t)

    for item in ann:
        t = _get_text_from_item(item)
        if t:
            all_texts.append(t)

    domain_spec_text = "\n\n".join(all_texts)

    with open("amd_domain_spec.txt", "w", encoding="utf-8") as out:
        out.write(domain_spec_text)

    print("Saved amd_domain_spec.txt")


if __name__ == "__main__":
    main()
