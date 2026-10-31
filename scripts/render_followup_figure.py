#!/usr/bin/env python3
"""Render the audited follow-up comparison (requires matplotlib)."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
audit = json.loads((ROOT / "research/outputs/scope_followup_audit.json").read_text())
groups = [audit["groups"][k] for k in
          ["cond4_flow", "cond4_unordered", "cond4_flow_scoped"]]
plt.rcParams.update({"font.family": "DejaVu Sans", "svg.fonttype": "none"})
fig = plt.figure(figsize=(14, 7), dpi=160, facecolor="#f6f4ef")
fig.text(.5, .91, "FLOWSPEC-GEMMA4", fontsize=15, weight="bold", color="#285f69", ha="center")
fig.text(.5, .825, "Order & Method Scope", fontsize=25, weight="bold", color="#17282e", ha="center")
fig.text(.5, .76, "V2 artifact verification · n=10 per condition", fontsize=13, color="#4c6066", ha="center")
ax = fig.add_axes([.405, .30, .285, .37], facecolor="none")
labels = ["Flow Base", "Unordered", "Flow + Scoped"]
colors = ["#9faeb2", "#c4b7a0", "#286978"]
values = [100 * g["full_passes"] / g["n"] for g in groups]
ax.barh([2, 1, 0], values, height=.48, color=colors)
for y, g in zip([2, 1, 0], groups):
    value = 100 * g["full_passes"] / g["n"]
    ax.text(value + 1.6, y, f"{g['full_passes']}/{g['n']}", va="center", fontsize=16, weight="bold", color="#17282e")
ax.set_xlim(0, 114)
ax.set_ylim(-.55, 2.55)
ax.set_yticks([2, 1, 0], labels, fontsize=15, color="#17282e")
ax.tick_params(axis="y", length=0, pad=18)
ax.set_xticks([0, 25, 50, 75, 100], ["0", "25", "50", "75", "100%"], fontsize=11, color="#617378")
ax.tick_params(axis="x", length=0, pad=8)
for spine in ax.spines.values():
    spine.set_visible(False)
ax.set_axisbelow(True)
ax.grid(axis="x", color="#dddeda", linewidth=.8)
fig.text(.5, .18, "SCOPED: 10/10 artifacts · 5/10 sessions completed", fontsize=13, weight="bold", color="#17282e", ha="center")
fig.text(.5, .12, "+29% total tokens vs Flow Base", fontsize=13, color="#285f69", ha="center")
fig.text(.5, .055, "46 unique study runs · exploratory cohorts", fontsize=11, color="#617378", ha="center")
for suffix in ["png", "svg"]:
    output = ROOT / "docs" / f"flowspec_gemma4_thumbnail.{suffix}"
    fig.savefig(output, facecolor=fig.get_facecolor())
    if suffix == "svg":
        output.write_text("\n".join(line.rstrip() for line in output.read_text().splitlines()) + "\n")
plt.close(fig)
