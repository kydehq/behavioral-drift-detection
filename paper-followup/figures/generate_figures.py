#!/usr/bin/env python3
"""Generate the observability-ladder paper's figures as SVG. Stdlib only.

Data is embedded verbatim from the measured result tables in
../../experiments/results/ (l1b-terminalwrench-artifacts.md,
l3-terminalwrench-rewardhack.md, trace-transfer.md,
l2-agentdojo-injection.md, trail-content-coverage.md,
swechat-real-timelines.md), so the figures are reproducible from this
script alone:
    python3 generate_figures.py
The one exception is WITHIN_ADJ (figure 4a): the per-user values behind
the result table's median/quartiles, recomputed via
driftdetect.eval_swechat.experiment_fingerprint's definition (JSD of a
user's first two 400-record blocks) and embedded here rounded to 3
decimals; the table's summary statistics reproduce from this list.

Colors follow the repository's chart conventions: neutral inks and
grid, white surface; the three Terminal Wrench models and the two
figure-4 series use the categorical triple #2a78d6 / #eb6834 / #1f9d8b
(validated for color-vision deficiency on the light surface: worst
adjacent-pair CVD delta-E 11.5, normal-vision 26.9, all steps >= 3:1
against the surface). Identity is never color-alone: every series is
also named by a legend or a direct label.
"""

import os

FONT = "system-ui, -apple-system, 'Segoe UI', sans-serif"
BLUE, ORANGE, TEAL = "#2a78d6", "#eb6834", "#1f9d8b"
INK, INK2, MUTED = "#0b0b0b", "#52514e", "#898781"
GRID, AXIS, SURFACE = "#e1e0d9", "#c3c2b7", "#ffffff"
GRAY = "#a5a39c"                                 # frozen-transfer / noise-floor marks

# --- Figure 1: reward hacking, detection by rung x detector type -----------
# Terminal Wrench eval split (l1-*.md, l1b-*.md, l3-*.md), models
# claude-opus-4.6 / gemini-3.1-pro / gpt-5.4; TRACE rows from trace-transfer.md.
LADDER_ROWS = [
    ("L0 · boundary records, token frequencies", (0.0, 0.0, 0.0), "0.0% FPR"),
    ("L1 · plain command lines, token frequencies", (0.0, 0.0, 0.0), "0.0% FPR"),
    ("L1 · the same lines, frozen mechanism rules", (72.9, 36.2, 70.0), "0.5–1.6% FPR"),
    ("L3 · reasoning text, justification patterns", (98.6, 97.5, 99.7), "0.2–1.2% FPR"),
]
TRANSFER_ROWS = [
    ("TRACE transfer · L1 mechanism rules, frozen", 1.9, "0.4% FPR"),
    ("TRACE transfer · L3 justification patterns, frozen", 1.5, "1.2% FPR"),
]
MODELS = [("claude-opus-4.6", BLUE), ("gemini-3.1-pro", ORANGE), ("gpt-5.4", TEAL)]

# --- Figure 2: AgentDojo, L0 vs L2 on the same axes -------------------------
# L0: (detection %, FPR %) per pipeline over successful-injection runs —
# same list as the companion's figure 3 (agentdojo-injection.md).
AGENTDOJO_L0 = [
    (2.1, 6.9), (0.5, 6.2), (3.8, 7.5), (3.0, 4.0), (0.0, 3.0), (0.0, 2.6),
    (0.4, 2.7), (0.0, 3.2), (5.8, 10.8), (1.5, 3.4), (0.7, 6.0), (7.7, 8.6),
    (4.1, 6.1), (0.3, 2.3), (0.0, 1.7), (3.3, 5.8), (2.7, 6.6), (3.0, 7.1),
    (1.5, 4.4), (2.0, 4.4), (4.9, 6.8), (0.1, 1.7), (1.6, 4.6), (1.4, 3.9),
]
# L2: (det. success %, FPR %) per pipeline, eval split
# (l2-agentdojo-injection.md; the one pipeline with zero successful
# injections in the eval split has no success-conditioned point).
AGENTDOJO_L2 = [
    (100.0, 6.4), (100.0, 7.5), (100.0, 3.6), (100.0, 2.2), (100.0, 7.3),
    (93.9, 7.0), (98.0, 4.3), (100.0, 3.8), (93.8, 2.2), (100.0, 4.0),
    (100.0, 2.2), (100.0, 2.9), (95.7, 5.1), (100.0, 6.7), (100.0, 4.3),
    (100.0, 2.7), (98.1, 5.6), (100.0, 2.1), (99.3, 3.3), (97.9, 3.0),
    (100.0, 4.0), (100.0, 1.9), (100.0, 5.4), (100.0, 3.2), (98.6, 8.2),
    (100.0, 3.4), (97.9, 5.4), (98.2, 5.5),
]

# --- Figure 3: TRAIL, coverage of the annotated error mass vs noise floor ---
# trail-content-coverage.md, eval split: (channel, coverage %, noise %).
# The runtime-status row is the L0 baseline at the same locations; it has
# no noise-floor pairing by construction.
TRAIL_PANELS = [
    ("GAIA (453 annotated locations)", [
        ("runtime status (the L0 bound)", 6.4, None),
        ("own stored outputs", 6.0, 5.9),
        ("+ 3-span downstream window", 12.8, 17.0),
        ("next-prompt delta (L1 replay)", 31.6, 13.4),
    ]),
    ("SWE Bench (201 annotated locations)", [
        ("runtime status (the L0 bound)", 5.5, None),
        ("own stored outputs", 16.9, 13.3),
        ("+ 3-span downstream window", 36.3, 34.8),
        ("next-prompt delta (L1 replay)", 11.9, 10.0),
    ]),
]

# --- Figure 4: SWE-chat real timelines --------------------------------------
# (a) JSD strips, 400-record blocks / version blocks (swechat-real-timelines.md)
WITHIN_ADJ = [
    0.046, 0.055, 0.063, 0.064, 0.066, 0.069, 0.073, 0.076, 0.077, 0.084,
    0.087, 0.087, 0.092, 0.099, 0.101, 0.104, 0.111, 0.114, 0.117, 0.120,
    0.122, 0.127, 0.131, 0.137, 0.141, 0.142, 0.144, 0.146, 0.149, 0.150,
    0.151, 0.152, 0.152, 0.154, 0.156, 0.163, 0.167, 0.171, 0.172, 0.183,
    0.184, 0.200, 0.206, 0.211, 0.214, 0.222, 0.223, 0.231, 0.240, 0.241,
    0.243, 0.272, 0.277, 0.291, 0.307, 0.309, 0.311, 0.425,
]
BOUNDARY_JSD = [
    0.048, 0.076, 0.085, 0.092, 0.107, 0.113, 0.122, 0.125, 0.127, 0.132,
    0.139, 0.140, 0.150, 0.152, 0.153, 0.155, 0.200, 0.335, 0.343,
]
BETWEEN_Q = {"p10": 0.240, "q1": 0.296, "med": 0.358, "q3": 0.424, "p90": 0.495}
DETECTION_LINE = 0.02   # the companion's batch-scale version-drift line
# (b) aging curve: (k, users, median JSD, median lag days)
AGING = [
    (1, 41, 0.137, 1.6), (2, 41, 0.158, 3.6), (3, 34, 0.155, 6.9),
    (4, 25, 0.158, 7.7), (5, 23, 0.154, 7.9), (6, 15, 0.201, 7.7),
    (7, 14, 0.221, 8.9), (8, 11, 0.160, 9.8), (9, 10, 0.134, 9.8),
    (10, 10, 0.169, 12.2), (11, 9, 0.174, 14.2), (12, 9, 0.206, 13.6),
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


def open_dot(x, y, color, r=5):
    return (f'<circle cx="{x}" cy="{y}" r="{r + 2}" fill="{SURFACE}"/>'
            f'<circle cx="{x}" cy="{y}" r="{r}" fill="{SURFACE}" '
            f'stroke="{color}" stroke-width="2"/>')


def legend(x, y, entries):
    out, cx = [], x
    for label, color, hollow in entries:
        if hollow:
            out.append(f'<circle cx="{cx}" cy="{y - 4}" r="5" fill="{SURFACE}" '
                       f'stroke="{color}" stroke-width="2"/>')
        else:
            out.append(f'<circle cx="{cx}" cy="{y - 4}" r="5" fill="{color}"/>')
        out.append(text(cx + 10, y, label, 11, INK2))
        cx += 10 + 7 * len(label) + 26
    return out


def fig_ladder(path):
    """Dot plot: reward-hacking detection by rung x detector type."""
    W, LEFT, RIGHT, TOP, ROW = 660, 300, 24, 96, 34
    rows = len(LADDER_ROWS) + len(TRANSFER_ROWS)
    H = TOP + ROW * rows + 46
    px = lambda v: LEFT + (W - LEFT - RIGHT) * v / 100.0
    s = svg_open(W, H)
    s.append(text(16, 24, "Reward hacking: the detector type, not the rung, buys detection",
                  13, INK, weight="600"))
    s.append(text(16, 42, "Terminal Wrench, held-out detection per model; the frozen detectors",
                  11, INK2))
    s.append(text(16, 56, "re-applied to TRACE (different hack provenance) collapse to base rate",
                  11, INK2))
    s += legend(16, 78, [(m, c, False) for m, c in MODELS]
                + [("frozen on TRACE", GRAY, True)])
    for v in (0, 25, 50, 75, 100):
        s.append(f'<line x1="{px(v)}" y1="{TOP}" x2="{px(v)}" '
                 f'y2="{H - 42}" stroke="{GRID}" stroke-width="1"/>')
        s.append(text(px(v), H - 26, f"{v}%", 10, MUTED, anchor="middle"))
    s.append(text((LEFT + W - RIGHT) / 2, H - 8,
                  "held-out detection of reward-hacked runs", 10, MUTED, anchor="middle"))
    y = TOP + ROW // 2
    for label, dets, fpr in LADDER_ROWS:
        s.append(text(LEFT - 12, y - 3, label, 10.5, INK2, anchor="end"))
        s.append(text(LEFT - 12, y + 10, f"at {fpr}", 9.5, MUTED, anchor="end"))
        lo, hi = px(min(dets)), px(max(dets))
        if hi - lo > 1:
            s.append(f'<line x1="{lo}" y1="{y}" x2="{hi}" y2="{y}" '
                     f'stroke="{GRID}" stroke-width="1"/>')
        for i, (d, (_, color)) in enumerate(zip(dets, MODELS)):
            # splay coincident values vertically so every model stays visible
            ties = [j for j, dv in enumerate(dets) if abs(dv - d) < 0.6]
            off = (ties.index(i) - (len(ties) - 1) / 2) * 9 if len(ties) > 1 else 0
            s.append(dot(px(d), y + off, color))
        y += ROW
    for label, det, fpr in TRANSFER_ROWS:
        s.append(text(LEFT - 12, y - 3, label, 10.5, INK2, anchor="end"))
        s.append(text(LEFT - 12, y + 10, f"at {fpr}", 9.5, MUTED, anchor="end"))
        s.append(open_dot(px(det), y, GRAY))
        y += ROW
    s.append("</svg>")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(s))


def fig_injection(path):
    """Scatter: detection vs FPR, L0 and L2 clouds on the companion's axes."""
    W, H, LEFT, TOP, BOT, RIGHT = 660, 380, 74, 88, 46, 168
    plot_w, plot_h = W - LEFT - RIGHT, H - TOP - BOT
    xmax = 12.0
    px = lambda v: LEFT + plot_w * v / xmax
    py = lambda v: H - BOT - plot_h * v / 100.0
    s = svg_open(W, H)
    s.append(text(16, 24, "Injection: the rung that stores the cause detects it",
                  13, INK, weight="600"))
    s.append(text(16, 42, "AgentDojo pipelines, successful-injection runs — the same corpus and axes",
                  11, INK2))
    s.append(text(16, 56, "as the companion's figure 3, one rung apart", 11, INK2))
    s += legend(16, 78, [("L2: content features on stored tool results", BLUE, False),
                         ("L0: per-run tool statistics", GRAY, True)])
    for v in (0, 4, 8, 12):
        s.append(f'<line x1="{px(v)}" y1="{TOP}" x2="{px(v)}" y2="{H - BOT}" '
                 f'stroke="{GRID}" stroke-width="1"/>')
        s.append(text(px(v), H - BOT + 16, f"{v}%", 10, MUTED, anchor="middle"))
    for v in (0, 25, 50, 75, 100):
        s.append(f'<line x1="{LEFT}" y1="{py(v)}" x2="{W - RIGHT}" y2="{py(v)}" '
                 f'stroke="{GRID}" stroke-width="1"/>')
        s.append(text(LEFT - 8, py(v) + 4, f"{v}%", 10, MUTED, anchor="end"))
    s.append(f'<line x1="{LEFT}" y1="{H - BOT}" x2="{W - RIGHT}" y2="{H - BOT}" '
             f'stroke="{AXIS}" stroke-width="1"/>')
    # chance reference: detection equal to false-positive rate
    s.append(f'<line x1="{px(0)}" y1="{py(0)}" x2="{px(xmax)}" y2="{py(xmax)}" '
             f'stroke="{MUTED}" stroke-width="1" stroke-dasharray="4 3"/>')
    s.append(text(px(xmax) + 8, py(xmax) + 4, "detection = FPR", 10, MUTED))
    s.append(text(px(xmax) + 8, py(xmax) + 18, "(chance level)", 10, MUTED))
    for det, fpr in AGENTDOJO_L0:
        s.append(open_dot(px(fpr), py(det), GRAY, 4))
    for det, fpr in AGENTDOJO_L2:
        s.append(dot(px(fpr), py(det), BLUE, 4))
    s.append(f'<text x="20" y="{TOP + plot_h / 2}" font-size="10" fill="{MUTED}" '
             f'text-anchor="middle" transform="rotate(-90 20 {TOP + plot_h / 2})">'
             f'detection on successful-injection runs</text>')
    s.append(text((LEFT + W - RIGHT) / 2, H - 8,
                  "false-positive rate on held-out benign runs", 10, MUTED, anchor="middle"))
    s.append("</svg>")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(s))


def fig_semantic_wall(path):
    """Paired dots: coverage of annotated error mass vs its noise floor."""
    W, PANEL_LEFT = 660, (188, 430)
    TOP, ROW, PW = 118, 34, 170
    rows = 4
    H = TOP + ROW * rows + 48
    xmax = 40.0
    s = svg_open(W, H)
    s.append(text(16, 24, "Most of the annotated error mass is invisible at every rung",
                  13, INK, weight="600"))
    s.append(text(16, 42, "TRAIL, held-out: share of human-annotated error locations a frozen",
                  11, INK2))
    s.append(text(16, 56, "content predicate covers, against the same predicate on non-annotated",
                  11, INK2))
    s.append(text(16, 70, "spans — only the scaffold-routed prompt-replay channel separates", 11, INK2))
    s += legend(16, 92, [("coverage at annotated locations", BLUE, False),
                         ("noise floor (non-annotated spans)", GRAY, False)])
    for (title, rows_data), x0 in zip(TRAIL_PANELS, PANEL_LEFT):
        px = lambda v: x0 + PW * v / xmax
        s.append(text(x0, TOP - 14, title, 11, INK2, weight="600"))
        for v in (0, 20, 40):
            s.append(f'<line x1="{px(v)}" y1="{TOP - 4}" x2="{px(v)}" '
                     f'y2="{TOP + ROW * rows - 10}" stroke="{GRID}" stroke-width="1"/>')
            s.append(text(px(v), TOP + ROW * rows + 6, f"{v}%", 10, MUTED, anchor="middle"))
        y = TOP + ROW // 2
        for label, cov, noise in rows_data:
            if x0 == PANEL_LEFT[0]:
                s.append(text(x0 - 12, y + 4, label, 10.5, INK2, anchor="end"))
            if noise is not None:
                lo, hi = sorted((px(cov), px(noise)))
                if hi - lo > 1:
                    s.append(f'<line x1="{lo}" y1="{y}" x2="{hi}" y2="{y}" '
                             f'stroke="{GRID}" stroke-width="1"/>')
                s.append(dot(px(noise), y, GRAY, 4))
            s.append(dot(px(cov), y, BLUE, 4))
            y += ROW
    s.append(text((PANEL_LEFT[0] + PANEL_LEFT[1] + PW) / 2, H - 8,
                  "share of annotated error mass covered", 10, MUTED, anchor="middle"))
    s.append("</svg>")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(s))


def fig_real_timelines(path):
    """(a) JSD strips: churn, real version boundaries, between users;
    (b) the frozen baseline's aging curve."""
    W = 660
    A_LEFT, A_RIGHT, A_TOP, A_ROW = 220, 24, 118, 44
    a_h = A_TOP + 3 * A_ROW + 40
    B_TOP = a_h + 46
    B_LEFT, B_RIGHT, B_PLOT_H = 220, 24, 110
    H = B_TOP + B_PLOT_H + 64
    xmax = 0.52
    px = lambda v: A_LEFT + (W - A_LEFT - A_RIGHT) * v / xmax
    s = svg_open(W, H)
    s.append(text(16, 24, "Real timelines: in-control churn dwarfs the version-drift line",
                  13, INK, weight="600"))
    s.append(text(16, 42, "SWE-chat Claude Code users, 400-record blocks. Real CLI updates (orange)",
                  11, INK2))
    s.append(text(16, 56, "sit inside the same users' no-change churn; only user identity separates",
                  11, INK2))
    s += legend(16, 78, [("one user, adjacent blocks (churn)", BLUE, False),
                         ("real CLI-version boundary", ORANGE, False)])
    s.append(text(16, 98, "(a) effect sizes, Jensen–Shannon divergence", 11, INK, weight="600"))

    # x grid for panel (a)
    for v in (0.0, 0.1, 0.2, 0.3, 0.4, 0.5):
        s.append(f'<line x1="{px(v)}" y1="{A_TOP - 6}" x2="{px(v)}" '
                 f'y2="{A_TOP + 3 * A_ROW - 12}" stroke="{GRID}" stroke-width="1"/>')
        s.append(text(px(v), A_TOP + 3 * A_ROW + 4, f"{v:.1f}", 10, MUTED, anchor="middle"))
    # the companion's detection line
    dl = px(DETECTION_LINE)
    s.append(f'<line x1="{dl}" y1="{A_TOP - 6}" x2="{dl}" '
             f'y2="{A_TOP + 3 * A_ROW - 12}" stroke="{INK2}" stroke-width="1" '
             f'stroke-dasharray="3 3"/>')
    s.append(text(dl + 4, A_TOP - 10, "JSD 0.02: batch-scale version drift detects (companion)",
                  9.5, INK2))

    rows_a = [
        ("58 users' no-change churn", WITHIN_ADJ, BLUE),
        ("19 real CLI updates", BOUNDARY_JSD, ORANGE),
    ]
    y = A_TOP + A_ROW // 2
    for label, values, color in rows_a:
        s.append(text(A_LEFT - 12, y + 4, label, 10.5, INK2, anchor="end"))
        for i, v in enumerate(values):
            off = (i % 3 - 1) * 7          # light beeswarm against overplot
            s.append(dot(px(v), y + off, color, 3.5))
        y += A_ROW
    # between-users row: quantile band (1,653 pairs)
    s.append(text(A_LEFT - 12, y - 3, "between users (1,653 pairs)", 10.5, INK2, anchor="end"))
    s.append(text(A_LEFT - 12, y + 10, "p10–p90, quartile box, median", 9.5, MUTED, anchor="end"))
    q = BETWEEN_Q
    s.append(f'<rect x="{px(q["p10"])}" y="{y - 5}" width="{px(q["p90"]) - px(q["p10"])}" '
             f'height="10" rx="4" fill="{GRID}"/>')
    s.append(f'<rect x="{px(q["q1"])}" y="{y - 8}" width="{px(q["q3"]) - px(q["q1"])}" '
             f'height="16" rx="4" fill="{GRAY}"/>')
    s.append(f'<line x1="{px(q["med"])}" y1="{y - 11}" x2="{px(q["med"])}" y2="{y + 11}" '
             f'stroke="{INK}" stroke-width="2"/>')

    # panel (b): aging curve
    s.append(text(16, B_TOP - 18, "(b) the frozen baseline ages: JSD of block k vs a user's first block",
                  11, INK, weight="600"))
    ymax_b = 0.25
    kmax = AGING[-1][0]
    bx = lambda k: B_LEFT + (W - B_LEFT - B_RIGHT) * (k - 1) / (kmax - 1)
    by = lambda v: B_TOP + B_PLOT_H - B_PLOT_H * v / ymax_b
    for v in (0.0, 0.1, 0.2):
        s.append(f'<line x1="{B_LEFT}" y1="{by(v)}" x2="{W - B_RIGHT}" y2="{by(v)}" '
                 f'stroke="{GRID}" stroke-width="1"/>')
        s.append(text(B_LEFT - 8, by(v) + 4, f"{v:.1f}", 10, MUTED, anchor="end"))
    pts = " ".join(f"{bx(k):.1f},{by(j):.1f}" for k, _, j, _ in AGING)
    s.append(f'<polyline points="{pts}" fill="none" stroke="{BLUE}" stroke-width="2"/>')
    for k, n, j, lag in AGING:
        s.append(dot(bx(k), by(j), BLUE, 3.5))
        if k in (1, 3, 5, 7, 9, 11):
            s.append(text(bx(k), B_TOP + B_PLOT_H + 16, f"{lag:.0f}d", 10, MUTED,
                          anchor="middle"))
    s.append(text(B_LEFT - 12, B_TOP + B_PLOT_H // 2, "JSD", 10, MUTED, anchor="end"))
    s.append(text((B_LEFT + W - B_RIGHT) / 2, B_TOP + B_PLOT_H + 34,
                  "median time lag from the first block (41 users at k=1, 9 at k=12)",
                  10, MUTED, anchor="middle"))
    s.append("</svg>")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(s))


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    fig_ladder(os.path.join(here, "fig1-rewardhack-ladder.svg"))
    fig_injection(os.path.join(here, "fig2-injection-l0-vs-l2.svg"))
    fig_semantic_wall(os.path.join(here, "fig3-semantic-wall.svg"))
    fig_real_timelines(os.path.join(here, "fig4-real-timelines.svg"))
    print("wrote fig1-rewardhack-ladder.svg, fig2-injection-l0-vs-l2.svg, "
          "fig3-semantic-wall.svg, fig4-real-timelines.svg")


if __name__ == "__main__":
    main()
