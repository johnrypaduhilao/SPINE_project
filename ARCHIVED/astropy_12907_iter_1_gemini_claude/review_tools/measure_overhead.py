"""measure_overhead.py  Re-derives the Overhead sheet. Manual numbers govern; this reproduces them.
Usage: python measure_overhead.py  (paths below point at the real_artifacts layout)"""
import json, timeit, statistics, os, sys
PATHS={
 "CLAUDE tree":"../CLAUDE-SONNET/claude_plan_structured/outputs/pilot_tree_astropy__astropy-12907.json",
 "GEMINI tree":"../GEMINI-FLASH/gemini_plan_structured/outputs/pilot_tree_astropy__astropy-12907-3.5-flash.json",
 "CLAUDE prose":"../CLAUDE-SONNET/claude_plan_unstructured/outputs/plan_unstructured_astropy__astropy-12907_claude-sonnet-4-6_run1.json",
 "GEMINI prose":"../GEMINI-FLASH/gemini_plan_unstructured/outputs/plan_unstructured_astropy__astropy-12907_gemini-3.5-flash_run1.json",
 "CLAUDE exec":"../CLAUDE-SONNET/claude_exec_unstructured/outputs/unstructured_trajectory_astropy12907_run1.json",
 "GEMINI exec":"../GEMINI-FLASH/gemini_exec_unstructured/outputs/unstructured_trajectory-3.5-flash.json",
}
root=sys.argv[1] if len(sys.argv)>1 else "."
def traverse(pol,parent,leaf):
    chain=[]; i=leaf
    while i is not None: chain.append(pol[i]); i=parent[i]
    return chain
for label,rel in PATHS.items():
    p=os.path.join(root,rel)
    if not os.path.isfile(p): print("%-14s MISSING %s"%(label,p)); continue
    d=json.load(open(p,encoding="utf-8"))
    if "tree" in label:
        pol={x["id"]:x for x in d["policies"]}; parent={x["id"]:x.get("parent_id") for x in d["policies"]}
        def depth(i):
            n=0
            while parent[i]: i=parent[i]; n+=1
            return n
        leaf=max(pol,key=depth)
        t=min(timeit.repeat(lambda:traverse(pol,parent,leaf),number=10000,repeat=7))/10000*1e6
        print("%-14s nodes=%2d chain=%d leaf=%-5s traversal=%.2f us file=%d B"
              %(label,len(pol),depth(leaf)+1,leaf,t,os.path.getsize(p)))
    else:
        text=d.get("response_text") or json.dumps(d["events"],ensure_ascii=False)
        scan=lambda:[l for l in text.splitlines() if "P4" in l or "_cstack" in l or "separab" in l]
        t=min(timeit.repeat(scan,number=2000,repeat=7))/2000*1e6
        print("%-14s chars=%6d full-scan=%.2f us file=%d B"%(label,len(text),t,os.path.getsize(p)))
