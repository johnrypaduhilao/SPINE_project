import json

# point these at the six policy-tree outputs
files = {
    ("AV", "Copilot"):       "result_copilot_av.json",
    ("AV", "Gemini"):        "result_gemini_av.json",
    ("Code", "Copilot"):     "result_copilot_code.json",
    ("Code", "Gemini"):      "result_gemini_code.json",
    ("Embodied", "Copilot"): "result_copilot_embodied.json",
    ("Embodied", "Gemini"):  "result_gemini_embodied.json",
}


def load(path):
    text = open(path, encoding="utf-8", errors="ignore").read()
    return json.loads(text[text.index("{"):])["policies"]


def size(obj):
    return len(json.dumps(obj, ensure_ascii=False).encode("utf-8"))


def main():
    records = total = pointer = rationale = 0
    print("%-10s%-9s%8s%8s%9s%11s" % ("domain", "model", "records", "bytes", "pointer", "rationale"))
    for (domain, model), path in files.items():
        policies = load(path)
        n = len(policies)
        rec = sum(size(p) for p in policies)
        ptr = sum(size({"parent_id": p.get("parent_id")}) for p in policies)
        rat = sum(size({"rationale": p.get("rationale", "")}) for p in policies)
        print("%-10s%-9s%8d%8d%8.1f%%%10.1f%%" % (domain, model, n, rec, 100 * ptr / rec, 100 * rat / rec))
        records += n; total += rec; pointer += ptr; rationale += rat

    print("%-19s%8d%8d%8.1f%%%10.1f%%" % ("overall", records, total, 100 * pointer / total, 100 * rationale / total))
    print()
    print("parent-pointer overhead: %.1f%% of a record, %.0f bytes/record (constant)"
          % (100 * pointer / total, pointer / records))
    print("rationale prose share:   %.1f%% of storage" % (100 * rationale / total))


if __name__ == "__main__":
    main()
