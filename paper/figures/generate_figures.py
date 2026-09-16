#!/usr/bin/env python3
"""Generate the paper's Section 7 figures as SVG. Standard library only.

Data is embedded verbatim from the measured result tables in
experiments/results/ (swebench-margin-2.0.md, agentdojo-injection.md),
so the figures are reproducible from this script alone:
    python3 generate_figures.py
Colors follow the repository's chart conventions: divergence channel
#2a78d6 (blue), CUSUM channel #eb6834 (orange); text and grid in neutral
inks. Palette validated for color-vision deficiency on a white surface.
"""

import os

FONT = "system-ui, -apple-system, 'Segoe UI', sans-serif"
BLUE, ORANGE = "#2a78d6", "#eb6834"          # divergence, CUSUM
INK, INK2, MUTED = "#0b0b0b", "#52514e", "#898781"
GRID, AXIS, SURFACE = "#e1e0d9", "#c3c2b7", "#ffffff"

# (label, JSD, det_div %, det_cusum %) — swebench-margin-2.0.md, sorted by JSD
VERSION_PAIRS = [
    ("Emergent: same version twice (control)",        0.000,   0,   0),
    ("OpenHands: same model, scaled attempts",        0.000,  60,   0),
    ("OpenHands: Claude 4 Sonnet → Kimi K2",     0.002,  20,  50),
    ("OpenHands: 2025-04 → Claude 4 Sonnet",     0.006,  10,   0),
    ("OpenHands: scaled → 2025-04",              0.013,  30, 100),
    ("Trae: 2025-05 → 2025-06",                  0.021,   0,  80),
    ("SWE-agent: LM-32B → Kimi K2",              0.075,  30, 100),
    ("SWE-agent: Claude 3 Opus → GPT-4",         0.085,  10,  50),
    ("SWE-agent: Claude 3.5 → GPT-4o",           0.091,   0,  90),
    ("OpenHands: Kimi K2 → GPT-5",               0.105,  90,   0),
    ("SWE-agent: GPT-4 → Claude 3.5",            0.116,  40, 100),
    ("SWE-agent: GPT-4o → LM-32B",               0.813, 100, 100),
]

# per-channel null-stream FP rates (%), 20 submissions — swebench-margin-2.0.md
NULL_FP_DIV = [0, 0, 0, 0, 0, 10, 0, 0, 20, 10, 0, 20, 0, 10, 30, 0, 30, 0, 30, 10]
NULL_FP_CUSUM = [20, 20, 30, 0, 0, 0, 10, 0, 0, 0, 50, 30, 0, 0, 40, 0, 0, 30, 20, 10]

# (detection %, FPR %) per pipeline — agentdojo-injection.md, per-run table
AGENTDOJO = [
    (2.1, 6.9), (0.5, 6.2), (3.8, 7.5), (3.0, 4.0), (0.0, 3.0), (0.0, 2.6),
    (0.4, 2.7), (0.0, 3.2), (5.8, 10.8), (1.5, 3.4), (0.7, 6.0), (7.7, 8.6),
    (4.1, 6.1), (0.3, 2.3), (0.0, 1.7), (3.3, 5.8), (2.7, 6.6), (3.0, 7.1),
    (1.5, 4.4), (2.0, 4.4), (4.9, 6.8), (0.1, 1.7), (1.6, 4.6), (1.4, 3.9),
]


def svg_open(w, h):
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" font-family="{FONT}">',
        f'<rect width="{w}" height="{h}" fill="{SURFACE}"/>',
    ]


def text(x, y, s, size=11, fill=INK2, anchor="start", weight="normal"):
    return (f'<text x="{x}" y="{y}" font-size="{size}" fill="{fill}" '
            f'text-anchor="{anchor}" font-weight="{weight}">{s}</text>')


def dot(x, y, color, r=5):
    return (f'<circle cx="{x}" cy="{y}" r="{r + 2}" fill="{SURFACE}"/>'
            f'<circle cx="{x}" cy="{y}" r="{r}" fill="{color}"/>')


def legend(x, y, entries):
    out, cx = [], x
    for label, color in entries:
        out.append(f'<circle cx="{cx}" cy="{y - 4}" r="5" fill="{color}"/>')
        out.append(text(cx + 10, y, label, 11, INK2))
        cx += 10 + 7 * len(label) + 26
    return out


def fig_version_drift(path):
    """Dot plot: detection rate per submission pair, both channels."""
    W, LEFT, RIGHT, TOP, ROW = 660, 268, 24, 92, 30
    H = TOP + ROW * len(VERSION_PAIRS) + 42
    px = lambda v: LEFT + (W - LEFT - RIGHT) * v / 100.0
    s = svg_open(W, H)
    s.append(text(16, 24, "Version drift: detection rate vs. size of the behavioral change",
                  13, INK, weight="600"))
    s.append(text(16, 42, "rows sorted by the Jensen–Shannon divergence (JSD) between the "
                          "two versions' tool distributions", 11, INK2))
    s += legend(16, 64, [("divergence channel", BLUE), ("CUSUM channel", ORANGE)])
    for v in (0, 25, 50, 75, 100):
        s.append(f'<line x1="{px(v)}" y1="{TOP}" x2="{px(v)}" '
                 f'y2="{H - 38}" stroke="{GRID}" stroke-width="1"/>')
        s.append(text(px(v), H - 22, f"{v}%", 10, MUTED, anchor="middle"))
    s.append(text((LEFT + W - RIGHT) / 2, H - 6,
                  "trials detecting the version change", 10, MUTED, anchor="middle"))
    for i, (label, jsd, d_div, d_cus) in enumerate(VERSION_PAIRS):
        y = TOP + ROW * i + ROW // 2
        s.append(text(LEFT - 60, y + 4, label, 10.5, INK2, anchor="end"))
        s.append(text(LEFT - 12, y + 4, f"{jsd:.3f}", 10, MUTED, anchor="end"))
        lo, hi = sorted((px(d_div), px(d_cus)))
        if hi - lo > 1:
            s.append(f'<line x1="{lo}" y1="{y}" x2="{hi}" y2="{y}" '
                     f'stroke="{GRID}" stroke-width="1"/>')
        s.append(dot(px(d_div), y, BLUE))
        s.append(dot(px(d_cus), y, ORANGE))
    s.append(text(LEFT - 12, TOP - 6, "JSD", 10, MUTED, anchor="end"))
    s.append("</svg>")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(s))


def fig_null_fpr(path):
    """Dot histograms of null-stream false-positive rates, one panel per channel."""
    W, H, PW, TOP, BASE = 660, 250, 300, 64, 210
    DX, DY, R = 13, 12, 5
    s = svg_open(W, H)
    s.append(text(16, 24, "False alarms on drift-free streams (20 submissions, margin 2.0)",
                  13, INK, weight="600"))
    s.append(text(16, 42, "each dot is one submission's null-stream false-positive rate",
                  11, INK2))
    panels = [("divergence channel", BLUE, NULL_FP_DIV, 30),
              ("CUSUM channel", ORANGE, NULL_FP_CUSUM, 360)]
    for title, color, values, x0 in panels:
        s.append(text(x0, TOP, title, 11, INK2, weight="600"))
        s.append(f'<line x1="{x0}" y1="{BASE}" x2="{x0 + PW - 30}" y2="{BASE}" '
                 f'stroke="{AXIS}" stroke-width="1"/>')
        for b in range(6):
            fp = b * 10
            n = sum(1 for v in values if v == fp)
            cx = x0 + 18 + b * (DX * 3)
            s.append(text(cx, BASE + 16, f"{fp}%", 10, MUTED, anchor="middle"))
            for k in range(n):
                s.append(dot(cx, BASE - 10 - k * DY, color, R))
    s.append("</svg>")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(s))


def fig_agentdojo(path):
    """Scatter: per-run injection detection vs. false-positive rate, 24 pipelines."""
    W, H, LEFT, TOP, BOT, RIGHT = 660, 330, 210, 56, 44, 130
    plot_w = W - LEFT - RIGHT
    plot_h = H - TOP - BOT
    vmax = 12.0
    px = lambda v: LEFT + plot_w * v / vmax
    py = lambda v: H - BOT - plot_h * v / vmax
    s = svg_open(W, H)
    s.append(text(16, 24, "Successful injections are near-invisible to per-run tool statistics",
                  13, INK, weight="600"))
    s.append(text(16, 42, "AgentDojo, 24 model pipelines: detection barely exceeds the false-positive rate",
                  11, INK2))
    for v in (0, 4, 8, 12):
        s.append(f'<line x1="{px(v)}" y1="{TOP}" x2="{px(v)}" y2="{H - BOT}" '
                 f'stroke="{GRID}" stroke-width="1"/>')
        s.append(text(px(v), H - BOT + 16, f"{v}%", 10, MUTED, anchor="middle"))
        if v:
            s.append(f'<line x1="{LEFT}" y1="{py(v)}" x2="{W - RIGHT}" y2="{py(v)}" '
                     f'stroke="{GRID}" stroke-width="1"/>')
        s.append(text(LEFT - 8, py(v) + 4, f"{v}%", 10, MUTED, anchor="end"))
    s.append(f'<line x1="{LEFT}" y1="{H - BOT}" x2="{W - RIGHT}" y2="{H - BOT}" '
             f'stroke="{AXIS}" stroke-width="1"/>')
    # chance reference: detection equal to false-positive rate
    s.append(f'<line x1="{px(0)}" y1="{py(0)}" x2="{px(vmax)}" y2="{py(vmax)}" '
             f'stroke="{MUTED}" stroke-width="1"/>')
    s.append(text(px(vmax) + 8, py(vmax) + 4, "detection = FPR", 10, MUTED))
    s.append(text(px(vmax) + 8, py(vmax) + 18, "(chance level)", 10, MUTED))
    for det, fpr in AGENTDOJO:
        s.append(dot(px(fpr), py(det), BLUE))
    s.append(text(LEFT - 60, TOP + plot_h / 2, "detection", 10, MUTED, anchor="middle"))
    s.append(text((LEFT + W - RIGHT) / 2, H - 8,
                  "false-positive rate on held-out benign runs", 10, MUTED, anchor="middle"))
    s.append("</svg>")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(s))


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    fig_version_drift(os.path.join(here, "fig1-version-drift.svg"))
    fig_null_fpr(os.path.join(here, "fig2-null-fpr.svg"))
    fig_agentdojo(os.path.join(here, "fig3-agentdojo-perrun.svg"))
    print("wrote fig1-version-drift.svg, fig2-null-fpr.svg, fig3-agentdojo-perrun.svg")


if __name__ == "__main__":
    main()
