"""Generate benchmark chart for LinkedIn post."""

import matplotlib.pyplot as plt
import matplotlib.ticker as mtick

# ── Dark theme ──────────────────────────────────────────────
BG = "#0f1117"
CARD_BG = "#1a1b26"
TEXT = "#c0caf5"
MUTED = "#565f89"
GRID = "#24283b"

RED = "#f7768e"
ORANGE = "#ff9e64"
BLUE = "#7aa2f7"
GREEN = "#9ece6a"

plt.rcParams.update({
    "figure.facecolor": BG,
    "axes.facecolor": CARD_BG,
    "axes.edgecolor": GRID,
    "text.color": TEXT,
    "axes.labelcolor": TEXT,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "font.family": "sans-serif",
    "font.size": 13,
})

fig, ax = plt.subplots(figsize=(8, 6))

stages = ["Broken\nscorer", "Fixed\nbaseline", "Reranking\n(no LLM)", "Full\npipeline"]
values = [8.6, 34.5, 37.5, 79.4]
colors = [RED, ORANGE, BLUE, GREEN]

bars = ax.bar(stages, values, color=colors, width=0.55, edgecolor="none", zorder=3)

for bar, val in zip(bars, values):
    ax.text(
        bar.get_x() + bar.get_width() / 2, bar.get_height() + 1.5,
        f"{val}%", ha="center", va="bottom", fontsize=18, fontweight="bold", color=TEXT,
    )

ax.set_ylim(0, 95)
ax.set_ylabel("LoCoMo Accuracy", fontsize=14)
ax.yaxis.set_major_formatter(mtick.PercentFormatter())
ax.tick_params(axis="x", length=0, labelsize=13)
ax.grid(axis="y", color=GRID, linewidth=0.5, zorder=0)
ax.set_axisbelow(True)

# Remove top and right spines
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)

fig.savefig("images/benchmark_journey.png", dpi=200, bbox_inches="tight", facecolor=BG)
print("Saved to images/benchmark_journey.png")
plt.close()
