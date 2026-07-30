"""gen_pipeline_fig.py  Pipeline status + execute-arm design. John's palette, facts only."""
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

PEACH="#FBEFE3"; LAV="#DCD4EC"; PINK="#F4C7CB"; GREEN="#CFE6C9"; BLUE="#CFE0F0"
GREY="#E6E4E0"; WHITE="#FFFFFF"; INK="#2E2E2E"; LW=1.0
fig=plt.figure(figsize=(15.4,8.9),dpi=165); fig.patch.set_facecolor(PEACH)
def box(x,y,w,h,fc,r=0.012,z=1,ec=INK,lw=LW):
    fig.patches.append(FancyBboxPatch((x,y),w,h,boxstyle="round,pad=%.3f"%r,
        transform=fig.transFigure,facecolor=fc,edgecolor=ec,linewidth=lw,zorder=z))
def txt(x,y,s,fs=9.4,w="normal",c=INK,ha="left",st="normal",z=3):
    fig.text(x,y,s,fontsize=fs,fontweight=w,color=c,ha=ha,va="center",style=st,zorder=z)
def arrow(x1,y1,x2,y2):
    fig.patches.append(FancyArrowPatch((x1,y1),(x2,y2),transform=fig.transFigure,
        arrowstyle="-|>",mutation_scale=13,color=INK,linewidth=1.2,zorder=4))

txt(0.5,0.955,"Where we are in the pipeline, and what comes next",16.5,"bold",ha="center")

stages=[("1 dataset","DONE",GREEN),("2 request","DONE",GREEN),
        ("3 exec noplan","DONE",GREEN),("4 plan structured","DONE",GREEN),
        ("5 key findings","DONE",GREEN),("6 scoring","DONE",GREEN),
        ("7 execute arm","IN PROGRESS",LAV),("8 Docker","queued",GREY)]
x0,w,gap,y,h=0.035,0.1105,0.0075,0.845,0.072
for i,(name,st,fc) in enumerate(stages):
    x=x0+i*(w+gap); box(x,y,w,h,fc,z=1)
    txt(x+w/2,y+h*0.66,name,10.2,"bold",ha="center")
    txt(x+w/2,y+h*0.28,st,8.6,"bold" if st=="IN PROGRESS" else "normal",ha="center")
    if i<len(stages)-1: arrow(x+w+0.0012,y+h/2,x+w+gap-0.0012,y+h/2)
txt(0.5,0.805,"scoring closed this week: 4 cells x 2 models scored against the 9-node ground truth",
    9.2,ha="center",st="italic")

# ---- left: execute arm
box(0.035,0.232,0.605,0.548,WHITE,z=1)
txt(0.3375,0.745,"ZOOM: execute arm design",13.2,"bold",ha="center")
txt(0.3375,0.716,"one harness, one budget (30 turns), one record schema, temperature 0",9.3,ha="center",st="italic")
txt(0.3375,0.696,"the plan handed to the agent is the ONLY variable",9.3,ha="center",st="italic")

cfg=[("exec_unstructured_noplan","no plan given","BANKED: 13 events,\nedit matched human patch",PINK),
     ("exec_unstructured_plan","prose plan in","to run",PINK),
     ("exec_trajectory_plan","trajectory plan in","conditional on the\nplan cell result",BLUE),
     ("exec_structured_plan","policy tree in","to run",GREEN)]
cw,cgap=0.1385,0.0125; cx=0.052
for i,(n,sub,st,fc) in enumerate(cfg):
    x=cx+i*(cw+cgap); box(x,0.415,cw,0.245,fc,z=2)
    txt(x+cw/2,0.628,n,8.5,"bold",ha="center")
    txt(x+cw/2,0.597,sub,8.4,ha="center",st="italic")
    for j,line in enumerate(st.split("\n")):
        txt(x+cw/2,0.545-j*0.024,line,8.0,ha="center")
txt(0.3375,0.378,"E1 is already banked. It was run before this design existed:",8.9,ha="center")
txt(0.3375,0.356,"confirm its tools and budget match the harness, or re-run it clean.",8.9,ha="center")
txt(0.3375,0.318,"plan stage feeding it: plan_unstructured / plan_trajectory / plan_structured",9.4,"bold",ha="center")
txt(0.3375,0.293,"prose has no fields and no lineage; trajectory has fields, no lineage; the tree has both",8.8,ha="center",st="italic")
txt(0.3375,0.269,"that narrows the claim from 'structure helps' to 'lineage-bearing structure makes audit a traversal'",8.8,ha="center",st="italic")

# ---- right: record schema
box(0.660,0.232,0.305,0.548,LAV,z=1)
txt(0.8125,0.745,"What execution records",12.6,"bold",ha="center")
txt(0.8125,0.716,"identical schema in all four configs",9.0,ha="center",st="italic")
box(0.675,0.545,0.275,0.150,WHITE,z=2)
for j,l in enumerate(["step_id","action","observation","timestamp",
                      "policy_id","provenance_mode"]):
    txt(0.690,0.670-j*0.0235,l,8.6,"bold" if j>=4 else "normal")
txt(0.8125,0.518,"policy_id is what makes runtime audit a pointer walk",8.8,ha="center",st="italic")
txt(0.690,0.483,"structured: RECORDED at emit time, O(depth)",8.8,"bold")
txt(0.690,0.458,"others: RECONSTRUCTED after the fact from the",8.8)
txt(0.690,0.436,"full log plus chain-of-thought, O(n)",8.8)
txt(0.8125,0.402,"measured outputs",9.8,"bold",ha="center")
for j,l in enumerate(["% Resolved per config (Docker harness)",
                      "attribution rate: steps tied to a plan item",
                      "traversal cost: O(depth) vs O(n)",
                      "reconstruction disagreement between readers"]):
    txt(0.690,0.373-j*0.024,l,8.6)
txt(0.8125,0.258,"accounts: pending school research resources",8.8,"bold",ha="center")

# ---- findings band
box(0.035,0.035,0.930,0.180,BLUE,z=1)
txt(0.055,0.190,"Sequencing, one step at a time",11.2,"bold")
for i,t in enumerate([
 "1. stub the harness with all plan conditions, no API calls   2. structured plan live on Claude   3. unstructured plan live   4. Docker for all configs plus the sweagent CLI reference   5. repeat on the second model",
 "Gate stays OFF for the first run. The tree's delivery branch (commit, open PR) executes as written inside a sandbox with no network push, and the harness RECORDS what a gate would have vetoed.",
 "Gating one arm and not the other would put a hand on the scale. A recorded veto also shows the exact node and its parent chain, which is the stronger demonstration.",
 "Expect this: neither plan proposes the reference fix (one line in _cstack), and the plan-free run found it. Plan-driven execution may score lower on % Resolved. Structure is claimed for recoverability, not task success.",
]):
    txt(0.055,0.162-i*0.0295,t,8.7)

fig.savefig("pipeline_execute_arm.png",facecolor=PEACH,bbox_inches="tight",pad_inches=0.2)
print("wrote pipeline_execute_arm.png")
