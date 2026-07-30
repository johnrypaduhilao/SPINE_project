import json


def size(obj):
    return len(json.dumps(obj, separators=(",", ":")).encode("utf-8"))


record = {
    "record_id": "r-0007",
    "timestamp": "2026-06-20T14:03:11Z",
    "actor": "agent:coding-assistant",
    "tool": "PythonREPL",
    "operation": "read",
    "target": "/srv/app/config/.env",
    "outcome": "blocked",
    "policy_id": "P3.1",
    "parent_id": "P3",
}

pointer_fields = {"policy_id": record["policy_id"], "parent_id": record["parent_id"]}
plain_record = {k: v for k, v in record.items() if k not in pointer_fields}

rationale = ("reading is the direct disclosure path; an unauthorized read of a "
             "sensitive file is denied to preserve confidentiality under the "
             "protect-files intent")

full = size(record)
plain = size(plain_record)
pointer = full - plain
prose = len(rationale.encode("utf-8"))
prose_record = plain + prose

print("plain log entry (no lineage):      %4d bytes" % plain)
print("with parent-pointer lineage:       %4d bytes" % full)
print("  pointer cost:                    %4d bytes  (%.1f%% of the record)"
      % (pointer, 100.0 * pointer / full))
print("with rationale prose instead:      %4d bytes" % prose_record)
print("  prose cost:                      %4d bytes  (%.1f%% of the record)"
      % (prose, 100.0 * prose / prose_record))
print()
print("prose costs %.1fx the pointer for the same record" % (prose / pointer))
print("pointer is two ids, fixed per record (O(1)); prose grows with policy text")
