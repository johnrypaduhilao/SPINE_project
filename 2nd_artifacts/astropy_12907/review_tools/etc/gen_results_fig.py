"""
gen_results_fig.py
Results figure for astropy__astropy-12907 run 1. John's palette, facts only.
Regenerate: python gen_results_fig.py
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, FancyBboxPatch

PEACH    = "#FBEFE3"
LAVENDER = "#DCD4EC"
PINK     = "#F0A6AE"
GREEN    = "#93C48F"
BLUE     = "#BCD7EC"
INK      = "#2E2E2E"
LW       = 0.9

METRICS = ["Recall", "Precision", "TC", "AC", "EF", "SIF"]
CLAUDE_U = [1.00, 0.67, 0.00, 0.00, 0.00, 0.30]
CLAUDE_S = [1.00, 0.69, 1.00, 1.00, 1.00, 1.00]
GEMINI_U = [1.00, 1.00, 0.00, 0.00, 0.00, 0.30]
GEMINI_S = [0.92, 1.00, 1.00, 1.00, 1.00, 1.00]

fig = plt.figure(figsize=(13.2, 7.6), dpi=170)
fig.patch.set_facecolor(PEACH)

# header
fig.patches.append(FancyBboxPatch((0.035, 0.885), 0.93, 0.082,
    boxstyle="round,pad=0.006", transform=fig.transFigure,
    facecolor=LAVENDER, edgecolor=INK, linewidth=LW, zorder=1))
fig.text(0.055, 0.938, "Refinement results: astropy__astropy-12907 (SWE-bench Lite)",
         fontsize=15.5, fontweight="bold", color=INK, va="center", zorder=2)
fig.text(0.055, 0.907, "Plan vs plan, same intent, same prompt (sha256 d65a655202a3ffd4). "
         "Ground truth: 9 nodes, 6 obligations. Manual scoring.",
         fontsize=9.6, color=INK, va="center", zorder=2)

def panel(ax, u, s, title, sub):
    ax.set_facecolor(PEACH)
    x = range(len(METRICS)); w = 0.36
    b1 = ax.bar([i - w/2 for i in x], u, w, color=PINK, edgecolor=INK, linewidth=LW, label="unstructured")
    b2 = ax.bar([i + w/2 for i in x], s, w, color=GREEN, edgecolor=INK, linewidth=LW, label="structured")
    for bars in (b1, b2):
        for b in bars:
            ax.text(b.get_x() + b.get_width()/2, b.get_height() + 0.035,
                    "%.2f" % b.get_height(), ha="center", va="bottom",
                    fontsize=8.6, color=INK)
    ax.set_xticks(list(x)); ax.set_xticklabels(METRICS, fontsize=10.2, color=INK)
    ax.set_ylim(0, 1.22); ax.set_yticks([0, 0.5, 1.0])
    ax.set_yticklabels(["0.00", "0.50", "1.00"], fontsize=9, color=INK)
    ax.set_title(title, fontsize=12.6, fontweight="bold", color=INK, pad=16)
    ax.text(0.5, 1.035, sub, transform=ax.transAxes, ha="center",
            fontsize=8.8, color=INK, style="italic")
    ax.axvspan(1.5, 4.5, color=BLUE, alpha=0.30, zorder=0)
    for sp in ax.spines.values():
        sp.set_color(INK); sp.set_linewidth(LW)
    ax.tick_params(length=3, color=INK)
    ax.grid(axis="y", color=INK, alpha=0.12, linewidth=0.7)
    ax.set_axisbelow(True)

ax1 = fig.add_axes([0.065, 0.345, 0.415, 0.455])
ax2 = fig.add_axes([0.555, 0.345, 0.415, 0.455])
panel(ax1, CLAUDE_U, CLAUDE_S, "Claude Sonnet 4.6", "17-policy tree / 18-step prose")
panel(ax2, GEMINI_U, GEMINI_S, "Gemini 3.5 Flash", "6-policy tree / 4-step prose")

ax1.legend(loc="upper center", bbox_to_anchor=(1.115, -0.145), ncol=2,
           frameon=True, fontsize=10.2, edgecolor=INK, facecolor=PEACH)

fig.text(0.5, 0.228, "shaded band = recoverability metrics",
         ha="center", fontsize=8.6, color=INK, style="italic")

# findings band
fig.patches.append(FancyBboxPatch((0.035, 0.035), 0.93, 0.155,
    boxstyle="round,pad=0.008", transform=fig.transFigure,
    facecolor=BLUE, edgecolor=INK, linewidth=LW, zorder=1))
fig.text(0.055, 0.163, "TC / AC / EF: 0.00 unstructured, 1.00 structured. Two vendors, no exceptions.",
         fontsize=11.4, fontweight="bold", color=INK, va="center", zorder=2)
lines = [
 "Recall is 1.00 in three of four cells, and the one deficit (Gemini structured, 0.92) belongs to the structured arm.",
 "Precision is flat for Claude: 0.67 unstructured, 0.69 structured. Root excluded from both trees.",
 "Claude's prose invented ids and a dependency diagram with no schema in the prompt. Lineage was still depicted document-wide, not retrievable per node.",
 "Tree sizes differ 3x (17 vs 6 policies). Recoverability is identical. Gemini ran on a flash tier; pro tier exists now but in preview mode.",
]
for i, t in enumerate(lines):
    fig.text(0.055, 0.132 - i*0.0265, t, fontsize=8.9, color=INK, va="center", zorder=2)

fig.savefig("results_astropy12907_run1.png", facecolor=PEACH, bbox_inches="tight", pad_inches=0.22)
print("wrote results_astropy12907_run1.png")
