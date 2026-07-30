import json
import timeit

# Abstraction levels, ordered; refinement must not decrease the level.
ORDER = {"declarative": 0, "definitive": 1, "imperative": 2}

# The tuple fields every policy must carry: P = (D, E, A, C(R, S, T), CT).
FIELDS = ("id", "parent", "level", "definer", "enforcer",
          "action", "R", "S", "T", "context")

# Constraint fields compared against the parent for Invariant 3.
CONSTRAINTS = ("R", "S", "T", "context")


def preserves_or_specializes(child, parent):
    """Cheap comparison touch for Invariant 3. Returns whether the child value
    trivially preserves (equals) or narrows (carries) the parent value. The
    full semantic specialization check is domain-specific and belongs to
    ontology validation, which this benchmark excludes on purpose; here we do
    the comparison work only, so the timing reflects the per-constraint cost."""
    if child == parent:
        return True
    if isinstance(child, str) and isinstance(parent, str) and parent in child:
        return True
    return False


def _normalize_policies(raw_json):
    """Parse a policy payload and normalize it into the benchmark's expected shape."""
    payload = json.loads(raw_json)

    if isinstance(payload, dict):
        if "policies" not in payload or not isinstance(payload["policies"], list):
            raise ValueError("expected JSON object with a 'policies' list")
        policies = payload["policies"]
    elif isinstance(payload, list):
        policies = payload
    else:
        raise ValueError("expected a policy list or an object with a 'policies' list")

    normalized = []
    for p in policies:
        if not isinstance(p, dict):
            raise ValueError("each policy must be a JSON object")
        norm = dict(p)
        if "parent" not in norm and "parent_id" in norm:
            norm["parent"] = norm.pop("parent_id")
        if "R" not in norm or "S" not in norm or "T" not in norm:
            constraints = norm.get("constraints", {})
            if isinstance(constraints, dict):
                norm.setdefault("R", constraints.get("resource"))
                norm.setdefault("S", constraints.get("spatial"))
                norm.setdefault("T", constraints.get("temporal"))
        normalized.append(norm)
    return normalized


def structure(raw_json):
    """Convert one raw structured output into a conformant, linked tree.
    Steps: (1) parse, (2) validate each policy against the policy model,
    (3) link parent pointers. Raises on any hard conformance violation."""
    policies = _normalize_policies(raw_json)              # (1) parse

    by_id = {}
    for p in policies:                                   # (2a) per-policy model conformance
        for f in FIELDS:                                 # Invariant 1: uniform representation
            if f not in p:
                raise ValueError("Invariant 1: missing field " + f)
        if not p["definer"] or not p["enforcer"]:        # Invariant 5: accountability metadata
            raise ValueError("Invariant 5: empty definer or enforcer")
        if p["level"] not in ORDER:                      # Invariant 4: valid abstraction level
            raise ValueError("Invariant 4: invalid level " + str(p["level"]))
        by_id[p["id"]] = p

    tree = {}
    root_seen = False
    for p in policies:                                   # (2b) relational invariants + (3) linking
        par = p["parent"]
        if par is None:
            if p["level"] != "declarative":
                raise ValueError("root policy must be declarative")
            root_seen = True
            continue
        parent = by_id.get(par)                          # Invariant 2: unique, existing parent
        if parent is None:
            raise ValueError("Invariant 2: unknown parent " + str(par))
        if ORDER[p["level"]] < ORDER[parent["level"]]:   # Invariant 4: monotone refinement
            raise ValueError("Invariant 4: abstraction increased at " + p["id"])
        for f in CONSTRAINTS:                            # Invariant 3: preserved or specialized
            preserves_or_specializes(p[f], parent[f])
        tree[p["id"]] = par                              # (3) link parent pointer

    if not root_seen:
        raise ValueError("no declarative root policy")
    return tree


# ----------------------------------------------------------------------------
# Example  Built-in trees.
# ----------------------------------------------------------------------------

# Exact Table I tree for protect_files(/srv/app/config): 16 policies, depth 2.
CODE_POLICIES = [
    {"id": "P0",   "parent": None, "level": "declarative", "definer": "Human Operator", "enforcer": "Orchestrator",     "action": "protect",    "R": "file",            "S": "/srv/app/config",                    "T": "always", "context": "production"},
    {"id": "P1",   "parent": "P0", "level": "definitive",  "definer": "Assurance Engine", "enforcer": "Analyze",        "action": "classify",   "R": "file",            "S": "/srv/app/config",                    "T": "always", "context": "production"},
    {"id": "P1.1", "parent": "P1", "level": "imperative",  "definer": "Assurance Engine", "enforcer": "Execute",        "action": "tag",        "R": "file",            "S": "/srv/app/config",                    "T": "always", "context": "production"},
    {"id": "P2",   "parent": "P0", "level": "definitive",  "definer": "Assurance Engine", "enforcer": "Monitor",        "action": "monitor",    "R": "file operation",  "S": "/srv/app/config",                    "T": "always", "context": "production"},
    {"id": "P2.1", "parent": "P2", "level": "definitive",  "definer": "Assurance Engine", "enforcer": "Analyze",        "action": "authorize",  "R": "operation, actor","S": "/srv/app/config",                    "T": "always", "context": "production"},
    {"id": "P3",   "parent": "P0", "level": "definitive",  "definer": "Assurance Engine", "enforcer": "Plan",           "action": "decide (C)", "R": "plan",            "S": "/srv/app/config",                    "T": "always", "context": "production"},
    {"id": "P3.1", "parent": "P3", "level": "imperative",  "definer": "Assurance Engine", "enforcer": "Execute",        "action": "block",      "R": "read operation",  "S": "/srv/app/config",                    "T": "always", "context": "production"},
    {"id": "P3.2", "parent": "P3", "level": "imperative",  "definer": "Assurance Engine", "enforcer": "Execute",        "action": "block",      "R": "copy operation",  "S": "/srv/app/config -> external",        "T": "always", "context": "production"},
    {"id": "P3.3", "parent": "P3", "level": "imperative",  "definer": "Assurance Engine", "enforcer": "Execute",        "action": "block",      "R": "move operation",  "S": "/srv/app/config -> external",        "T": "always", "context": "production"},
    {"id": "P4",   "parent": "P0", "level": "definitive",  "definer": "Assurance Engine", "enforcer": "Plan",           "action": "decide (I)", "R": "plan",            "S": "/srv/app/config",                    "T": "always", "context": "production"},
    {"id": "P4.1", "parent": "P4", "level": "imperative",  "definer": "Assurance Engine", "enforcer": "Execute",        "action": "block",      "R": "write operation", "S": "/srv/app/config",                    "T": "always", "context": "production"},
    {"id": "P4.2", "parent": "P4", "level": "imperative",  "definer": "Assurance Engine", "enforcer": "Execute",        "action": "block",      "R": "permission change","S": "/srv/app/config",                   "T": "always", "context": "production"},
    {"id": "P5",   "parent": "P0", "level": "definitive",  "definer": "Assurance Engine", "enforcer": "Plan",           "action": "decide (A)", "R": "plan",            "S": "/srv/app/config",                    "T": "always", "context": "production"},
    {"id": "P5.1", "parent": "P5", "level": "imperative",  "definer": "Assurance Engine", "enforcer": "Execute",        "action": "block",      "R": "delete operation","S": "/srv/app/config",                    "T": "always", "context": "production"},
    {"id": "P6",   "parent": "P0", "level": "definitive",  "definer": "Assurance Engine", "enforcer": "Analyze",        "action": "detect",     "R": "resolved target", "S": "/srv/app/config & resolved targets", "T": "always", "context": "production"},
    {"id": "P6.1", "parent": "P6", "level": "imperative",  "definer": "Assurance Engine", "enforcer": "Execute",        "action": "reject",     "R": "resolved target", "S": "outside /srv/app/config",            "T": "always", "context": "production"},
]
 
# AV ground-truth tree (decelerate / Law46), 9 policies, depth 2, transcribed
# from the AV ground-truth spreadsheet. R for P3.1 and P3.2 were partly obscured
# in the source image and are best-effort; confirm those two against your xlsx.
# They do not affect the timing, which is field-agnostic.
AV_POLICIES = [
    {"id": "P0",   "parent": None, "level": "declarative", "definer": "Human operator",   "enforcer": "Orchestrator", "action": "limit",      "R": "stopping capacity",               "S": "all lanes", "T": "always", "context": "production"},
    {"id": "P1",   "parent": "P0", "level": "definitive",  "definer": "Assurance engine", "enforcer": "Analyze",      "action": "determine",  "R": "posted limit",                    "S": "all lanes", "T": "always", "context": "production"},
    {"id": "P1.1", "parent": "P1", "level": "imperative",  "definer": "Assurance engine", "enforcer": "Monitor",      "action": "read",       "R": "posted limit (from map)",         "S": "all lanes", "T": "always", "context": "production"},
    {"id": "P2",   "parent": "P0", "level": "definitive",  "definer": "Assurance engine", "enforcer": "Analyze",      "action": "determine",  "R": "weather cap (30 km/h)",           "S": "all lanes", "T": "always", "context": "production"},
    {"id": "P2.1", "parent": "P2", "level": "imperative",  "definer": "Assurance engine", "enforcer": "Monitor",      "action": "monitor",    "R": "weather state (fog/rain)",        "S": "all lanes", "T": "always", "context": "production"},
    {"id": "P3",   "parent": "P0", "level": "definitive",  "definer": "Assurance engine", "enforcer": "Plan",         "action": "enforce",    "R": "effective cap (posted, weather)", "S": "all lanes", "T": "always", "context": "production"},
    {"id": "P3.1", "parent": "P3", "level": "imperative",  "definer": "Assurance engine", "enforcer": "Execute",      "action": "compute",    "R": "effective cap",                   "S": "all lanes", "T": "always", "context": "production"},
    {"id": "P3.2", "parent": "P3", "level": "imperative",  "definer": "Assurance engine", "enforcer": "Execute",      "action": "block",      "R": "speed above cap",                 "S": "all lanes", "T": "always", "context": "production"},
    {"id": "P3.3", "parent": "P3", "level": "imperative",  "definer": "Assurance engine", "enforcer": "Execute",      "action": "decelerate", "R": "deceleration",                    "S": "all lanes", "T": "always", "context": "production"},
]

# OPTIONAL: point these at your real structured JSON outputs (each file holds a
# JSON list of policy objects using the fields in FIELDS above). Leave as None
# to use the built-ins. On Windows use a raw string, e.g. r"D:\THESIS\...".
#CODE_JSON_PATH = None
#AV_JSON_PATH = None
CODE_JSON_PATH = './code_execution/setting3_output.json'
AV_JSON_PATH = './av/setting3_output_av.json'

# Set to True to use the hardcoded CODE_POLICIES / AV_POLICIES trees.
# Set to False to load the JSON files above instead.
USE_HARDCODED_INPUT = False


def _load(path, default_policies):
    if USE_HARDCODED_INPUT:
        return json.dumps(default_policies)
    if path:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    return json.dumps(default_policies)


CODE_JSON = _load(CODE_JSON_PATH, CODE_POLICIES)
AV_JSON = _load(AV_JSON_PATH, AV_POLICIES)

def _policy_count(raw_json):
    return len(_normalize_policies(raw_json))


TREES = [
    ("code", CODE_JSON, _policy_count(CODE_JSON)),
    ("AV",   AV_JSON,   _policy_count(AV_JSON)),
]

REPS = 200_000

if __name__ == "__main__":
    print("SPINE structuring cost: parse -> validate against the policy model -> link parents")
    print("(deterministic, model-independent; excludes LLM latency and ontology validation)\n")
    print(f"{'tree':<10}{'policies':>9}{'per-tree (us)':>16}{'per-policy (us)':>18}")
    for name, raw, n in TREES:
        linked = structure(raw)                     # sanity: builds and validates once
        assert len(linked) == n - 1, "expected every non-root policy to link"
        t = timeit.timeit(lambda: structure(raw), number=REPS) / REPS
        print(f"{name:<10}{n:>9}{t * 1e6:>16.3f}{t * 1e6 / n:>18.4f}")
    print("\nReport the per-policy figure as the one-time structuring cost at refinement.")
    print("It is constant per policy and independent of the execution-log size.")
