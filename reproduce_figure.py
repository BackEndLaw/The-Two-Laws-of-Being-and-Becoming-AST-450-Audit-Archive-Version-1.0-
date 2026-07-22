import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Ellipse, FancyBboxPatch, FancyArrowPatch
import matplotlib.gridspec as gridspec


plt.rcParams.update(
    {
        "font.size": 11,
        "font.family": "DejaVu Sans",
        "axes.titlesize": 14,
        "axes.labelsize": 12,
    }
)


# Page size A4 landscape in inches
fig = plt.figure(figsize=(11.69, 8.27), dpi=300, constrained_layout=True)
gs = fig.add_gridspec(
    2, 2, width_ratios=[3, 2], height_ratios=[2, 1], wspace=0.35, hspace=0.25
)


# Panel A: Door/Gate phase space (left, spans both rows)
axA = fig.add_subplot(gs[:, 0])
axA.set_title("Panel A. Door-Gate Phase Space", pad=12)
axA.set_xlabel("Generativity cost G (low to high)")
axA.set_ylabel("Continuity C (high to low)")
axA.set_xlim(-0.2, 1.2)
axA.set_ylim(1.05, -0.05)
axA.set_xticks([0.0, 0.5, 1.0])
axA.set_yticks([1.0, 0.5, 0.0])
axA.grid(alpha=0.25, linestyle="--", linewidth=0.7)

# Draw soft ellipses representing regions
ell_door = Ellipse(
    (0.15, 0.85), width=0.5, height=0.5, angle=10, alpha=0.22, color="#3FB0AC"
)
ell_gen = Ellipse(
    (0.6, 0.55), width=0.6, height=0.7, angle=-10, alpha=0.20, color="#F6A24A"
)
ell_close = Ellipse(
    (0.85, 0.25), width=0.6, height=0.6, angle=-20, alpha=0.25, color="#C75C9A"
)
axA.add_patch(ell_door)
axA.add_patch(ell_gen)
axA.add_patch(ell_close)

# Points for WD, NS, BH
axA.scatter([0.12], [0.82], s=420, marker="o", color="#3FB0AC", edgecolor="k", zorder=4)
axA.text(0.12, 0.82, "  White Dwarf\n  (WD)", va="center", ha="left", fontsize=11, weight="bold")

axA.scatter([0.55], [0.52], s=420, marker="o", color="#F6A24A", edgecolor="k", zorder=4)
axA.text(0.55, 0.52, "  Neutron Star\n  (NS)", va="center", ha="left", fontsize=11, weight="bold")

axA.scatter([0.90], [0.22], s=420, marker="o", color="#C75C9A", edgecolor="k", zorder=4)
axA.text(0.90, 0.22, "  Black Hole\n  (BH)", va="center", ha="left", fontsize=11, weight="bold")

axA.text(0.08, 0.98, "Door", fontsize=10, weight="bold", color="#1F6E69")
axA.text(0.50, 0.70, "Generative Gate", fontsize=10, weight="bold", color="#9A5B12")
axA.text(0.74, 0.08, "Closure Gate", fontsize=10, weight="bold", color="#7A2A57")


# Panel B: MESA -> engine pipeline (top-right)
axB = fig.add_subplot(gs[0, 1])
axB.set_title("Panel B. MESA to Outcome Pipeline", pad=10)
axB.axis("off")

steps = [
    (0.06, 0.80, "MESA Grid\n(Progenitors)"),
    (0.06, 0.58, "Structure Metrics\n(xi2.5, E_bind)"),
    (0.06, 0.36, "Engine Sweep\n(f_heat, L_nu)"),
    (0.06, 0.14, "Outcome Class\nWD / NS / BH"),
]

for x, y, text in steps:
    box = FancyBboxPatch(
        (x, y),
        0.58,
        0.16,
        boxstyle="round,pad=0.02,rounding_size=0.03",
        linewidth=1.2,
        edgecolor="#2D2D2D",
        facecolor="#F5F7FA",
    )
    axB.add_patch(box)
    axB.text(x + 0.03, y + 0.08, text, va="center", ha="left", fontsize=10)

for y in [0.74, 0.52, 0.30]:
    arrow = FancyArrowPatch(
        (0.35, y),
        (0.35, y - 0.12),
        arrowstyle="-|>",
        mutation_scale=14,
        linewidth=1.4,
        color="#3C4A5B",
    )
    axB.add_patch(arrow)

# Side notes and decision marker
axB.text(0.70, 0.67, "Explodability\nthreshold", fontsize=9, color="#3C4A5B")
axB.text(0.70, 0.43, "Fallback and\nremnant mass", fontsize=9, color="#3C4A5B")
axB.text(0.70, 0.20, "Compute C, S_pre, G", fontsize=9, color="#3C4A5B")


# Panel C: Observational signatures (bottom-right)
axC = fig.add_subplot(gs[1, 1])
axC.set_title("Panel C. Observable Signatures", pad=10)
axC.set_xlim(0, 10)
axC.set_ylim(-0.5, 2.5)
axC.set_yticks([2, 1, 0])
axC.set_yticklabels(["WD", "NS", "BH"])
axC.set_xlabel("Relative timeline")
axC.grid(alpha=0.25, linestyle="--", linewidth=0.7)

# WD lane
axC.plot([0.8, 9.2], [2, 2], color="#3FB0AC", linewidth=3)
axC.scatter([2.0, 5.2, 8.1], [2, 2, 2], color="#3FB0AC", s=55, edgecolor="k", zorder=3)
axC.text(2.0, 2.15, "Envelope loss", fontsize=8, ha="center")
axC.text(5.2, 2.15, "Planetary nebula", fontsize=8, ha="center")
axC.text(8.1, 2.15, "Cooling track", fontsize=8, ha="center")

# NS lane
axC.plot([0.8, 9.2], [1, 1], color="#F6A24A", linewidth=3)
axC.scatter([3.2, 4.7, 6.2], [1, 1, 1], color="#F6A24A", s=55, edgecolor="k", zorder=3)
axC.text(3.2, 1.15, "SN burst", fontsize=8, ha="center")
axC.text(4.7, 1.15, "Neutrinos", fontsize=8, ha="center")
axC.text(6.2, 1.15, "Possible GW", fontsize=8, ha="center")

# BH lane
axC.plot([0.8, 9.2], [0, 0], color="#C75C9A", linewidth=3)
axC.scatter([3.8, 5.8, 7.6], [0, 0, 0], color="#C75C9A", s=55, edgecolor="k", zorder=3)
axC.text(3.8, 0.15, "Vanishing star", fontsize=8, ha="center")
axC.text(5.8, 0.15, "IR excess", fontsize=8, ha="center")
axC.text(7.6, 0.15, "Late accretion", fontsize=8, ha="center")


# Add concise global title and footnote
fig.suptitle("Stellar Successors in Door/Gate Taxonomy", fontsize=16, weight="bold", y=0.98)
fig.text(
    0.5,
    0.02,
    "Concept figure generated from reproducible Matplotlib code (MESA-to-engine logic).",
    ha="center",
    fontsize=9,
    color="#4C4C4C",
)


# Small helper curve to avoid an unused import warning and provide visual texture
x = np.linspace(0, 1, 200)
_ = np.exp(-5 * x)


plt.savefig("DoorGate_StellarRemnant_Taxonomy.png", dpi=300)
plt.show()
