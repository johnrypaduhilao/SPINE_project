"""
validate_ontology.py

Validates an OWL/Turtle ontology you authored against the ontologies it reuses.
Three checks, in order of how much they matter for this project:

  1. Syntax     -- does the file parse at all?
  2. Hard refs  -- does every owl:equivalentClass / rdfs:subClassOf target that
                   points into a reused ontology actually resolve to a class
                   declared there?  (This is the check that catches a dangling
                   alignment such as `av:Road owl:equivalentClass map:Road`
                   when no `map:Road` class exists.)
  3. Soft refs  -- do rdfs:seeAlso targets resolve?  These are documentation
                   links, so misses are warnings, not failures.

What this does NOT do: OWL reasoning (consistency, satisfiability, subsumption).
rdflib is an RDF library, not a reasoner. For that you need owlready2 + a
reasoner (HermiT/Pellet, needs Java), or Protege / ROBOT. For catching the
errors that actually bit this ontology, the checks below are what you want.

Setup:   pip install rdflib
Run:     python validate_ontology.py
         (put this file next to the .ttl and the three TTI .owl files,
          or edit the paths in the CONFIG block.)
"""

from rdflib import Graph, RDF, RDFS, OWL, URIRef

# ============================ CONFIG =======================================
# The ontology you authored, under test:
ONTOLOGY = ("av_ontology.ttl", "turtle")

# The ontologies it reuses (its equivalentClass/subClassOf targets live here):
REFERENCES = [
    ("zhao_ttl\TTIMapOnto.owl", "xml"),
    ("zhao_ttl\TTIControlOnto.owl", "xml"),
    ("zhao_ttl\TTICarOnto.owl", "xml"),
]

# Namespace of YOUR classes -- only your outbound links are audited:
MY_NS = "https://example.org/intent-assurance/av#"

# Namespace root of the reused ontologies. A hard reference into this root
# MUST resolve; a seeAlso into it that misses is only a warning (e.g. the TTI
# `sensor#` classes live in a file not loaded here).
FOREIGN_ROOT = "http://www.toyota-ti.ac.jp/"
# ===========================================================================


def load(path, fmt):
    g = Graph()
    try:
        g.parse(path, format=fmt)
    except Exception as e:
        print(f"  PARSE FAILED  {path}\n    {e}")
        return None
    print(f"  parsed  {path:24s} {len(g):6d} triples")
    return g


def local(iri):
    s = str(iri)
    return s.split("#")[-1] if "#" in s else s.rsplit("/", 1)[-1]


print("1. Syntax check")
under_test = load(*ONTOLOGY)
if under_test is None:
    raise SystemExit("Fix the parse error above first.")

combined = Graph()
for triple in under_test:
    combined.add(triple)
for path, fmt in REFERENCES:
    g = load(path, fmt)
    if g is not None:
        for triple in g:
            combined.add(triple)

# Every class declared anywhere in the loaded vocabulary.
declared = set(combined.subjects(RDF.type, OWL.Class))
print(f"\n  combined graph: {len(combined)} triples, {len(declared)} declared classes")

print("\n2. Hard references (equivalentClass / subClassOf)")
dangling = []
for s, p, o in combined:
    if not str(s).startswith(MY_NS):
        continue
    if p not in (OWL.equivalentClass, RDFS.subClassOf):
        continue
    if not isinstance(o, URIRef):
        continue                          # skip blank-node restrictions
    if str(o).startswith(MY_NS):
        continue                          # your own classes
    if str(o).startswith(FOREIGN_ROOT) and o not in declared:
        dangling.append((s, p, o))

if dangling:
    for s, p, o in dangling:
        rel = "equivalentClass" if p == OWL.equivalentClass else "subClassOf"
        print(f"  DANGLING  {local(s):18s} {rel:16s} -> {o}")
else:
    print("  OK -- every equivalentClass/subClassOf target is declared.")

print("\n3. Soft references (seeAlso)")
warnings = []
for s, p, o in combined:
    if str(s).startswith(MY_NS) and p == RDFS.seeAlso and isinstance(o, URIRef):
        if str(o).startswith(FOREIGN_ROOT) and o not in declared:
            warnings.append((s, o))

if warnings:
    for s, o in warnings:
        print(f"  warn      {local(s):18s} seeAlso          -> {o}")
    print("  (seeAlso is a documentation link; a miss is fine when the target")
    print("   ontology isn't loaded -- e.g. the TTI sensor# namespace.)")
else:
    print("  OK -- every seeAlso target is declared.")

print("\nRESULT:", "FAIL -- fix the dangling references above" if dangling else "PASS")
