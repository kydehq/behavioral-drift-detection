"""Real-timeline experiments on the SWE-chat ledgers (E5).

Every stream experiment in this tree so far carried the same honesty
note: run order was seeded shuffling, because no source had temporal
meaning. SWE-chat's sessions have real wall-clock timestamps from real
users, so the composed-timeline caveat can finally be *measured* instead
of disclosed. One deployment = one user's Claude Code use (agent_id);
sessions are the runs; the timeline is sessions in start-time order with
records in turn order inside each.

Three experiments, all on the claude-code ledger, all deterministic
except where a seed is named:

1. NULL STABILITY, REAL VS COMPOSED. Per user: the longest contiguous
   (in session start order) block of sessions sharing one CLI version,
   with at least --min-records records. The null hypothesis on a real
   timeline is "same user, same CLI version" — task mix, repository
   changes and model switches inside the block are ordinary usage, and
   a monitor that cannot tolerate them has no deployable FPR. Split
   50/25/25 at session boundaries (admission / calibration / null,
   companion protocol, thresholds = max in-control score x margin).
   The REAL arm keeps chronological order (one deterministic cell per
   user); the COMPOSED arm shuffles session order (--trials seeded
   cells per user) — the same records the companion's protocol would
   have seen. The difference between the two false-alarm rates is the
   measured size of the caveat.

2. REAL VERSION DRIFT. Users update their CLI mid-timeline (48 distinct
   versions in the corpus; the boundaries are read off the records, not
   constructed). Per boundary between two contiguous same-version
   session blocks (old >= --min-admission records, new >= --min-new):
   freeze the baseline on the first ~2/3 of the old block, calibrate on
   the rest, stream the new block (capped at --horizon-cap). CONTROL:
   the same protocol at a fake boundary placed at the session boundary
   nearest 60% of every large-enough single-version block — the
   detection rate a no-change split yields at matched geometry.

3. FINGERPRINT ACCOUNTING (no detector, plain JSD). Whether the
   per-deployment baseline premise holds on real deployments:
   within-user JSD between adjacent and lagged --block-size record
   blocks vs. between-user JSD at the same sample size, and an aging
   curve JSD(block 0, block k) with the median day lag per k.

Usage:
    python3 -m driftdetect.eval_swechat <ledger-dir> [--agent claude-code]
        [--window 50] [--margins 2.0,1.2] [--trials 10] [--seed 7]
        [--min-records 400] [--min-admission 300] [--min-new 150]
        [--horizon-cap 2000] [--block-size 400] [--out results.md]
"""

from __future__ import annotations

import argparse
import os
import random
import statistics

from .baseline import freeze_baseline, tool_distribution
from .detectors import CusumChannel, DivergenceChannel, js_divergence, run_two_regime
from .eval_swebench import calibrate
from .records import CallRecord, read_jsonl

CHANNELS = ("divergence", "cusum")


# ---------------------------------------------------------------------------
# Timeline loading
# ---------------------------------------------------------------------------

def load_timelines(ledger_dir: str, agent: str) -> dict[str, list[list[CallRecord]]]:
    """user_id -> sessions (record lists), chronological by first record ts.

    Sessions without a user id are dropped: a timeline is one identified
    deployment, and the corpus's unattributed sessions (1,625 of the
    claude-code ledger, 126,690 records) would otherwise merge an unknown
    number of different users into one pseudo-timeline whose "drift" is
    manufactured by the merge.
    """
    runs: dict[str, list[CallRecord]] = {}
    for rec in read_jsonl(os.path.join(ledger_dir, f"{agent}.jsonl")):
        runs.setdefault(rec.run_id, []).append(rec)
    by_user: dict[str, list[list[CallRecord]]] = {}
    for recs in runs.values():
        recs.sort(key=lambda r: r.step_index)
        if not recs[0].agent_id:
            continue
        by_user.setdefault(recs[0].agent_id, []).append(recs)
    for sessions in by_user.values():
        sessions.sort(key=lambda s: (s[0].ts, s[0].run_id))
    return by_user


def version_of(session: list[CallRecord]) -> str:
    return session[0].model_version


def version_blocks(sessions: list[list[CallRecord]]) -> list[tuple[str, list[list[CallRecord]]]]:
    """Contiguous same-CLI-version session blocks, in timeline order."""
    blocks: list[tuple[str, list[list[CallRecord]]]] = []
    for sess in sessions:
        v = version_of(sess)
        if blocks and blocks[-1][0] == v:
            blocks[-1][1].append(sess)
        else:
            blocks.append((v, [sess]))
    return blocks


def n_records(sessions: list[list[CallRecord]]) -> int:
    return sum(len(s) for s in sessions)


def concat(sessions: list[list[CallRecord]]) -> list[CallRecord]:
    return [rec for sess in sessions for rec in sess]


def split_at_fractions(sessions: list[list[CallRecord]], fractions: tuple[float, ...]):
    """Split a session list at the session boundaries nearest the given
    cumulative record fractions; every part keeps whole sessions. Returns
    None when there are not enough session boundaries left for a cut."""
    total = n_records(sessions)
    cum, acc = [], 0
    for sess in sessions:
        acc += len(sess)
        cum.append(acc)
    cuts = []
    lo = 1
    for frac in fractions:
        if lo >= len(sessions):
            return None
        target = frac * total
        best = min(range(lo, len(sessions)),
                   key=lambda i: abs(cum[i - 1] - target))
        cuts.append(best)
        lo = best + 1
    parts, start = [], 0
    for c in cuts:
        parts.append(sessions[start:c])
        start = c
    parts.append(sessions[start:])
    return parts


# ---------------------------------------------------------------------------
# Experiment 1: null stability, real vs composed order
# ---------------------------------------------------------------------------

def longest_single_version_block(sessions, min_records_):
    """Longest contiguous same-version block; an empty version string is
    unknown and cannot vouch for "same version throughout"."""
    best = None
    for v, block in version_blocks(sessions):
        if not v:
            continue
        if n_records(block) >= min_records_ and (
                best is None or n_records(block) > n_records(best)):
            best = block
    return best


def null_cell(block, order, window, margin, horizon_cap):
    """One admission/calibration/null pass over a session order."""
    if len(order) < 3:
        return None
    parts = split_at_fractions(order, (0.5, 0.75))
    if parts is None:
        return None
    adm, cal, nul = parts
    admission, calibration = concat(adm), concat(cal)
    null_stream = concat(nul)[:horizon_cap]
    if len(calibration) <= window or len(null_stream) <= window:
        return None
    baseline = freeze_baseline(admission)
    div_thr, cusum_thr = calibrate(baseline, calibration, window, margin)
    alarms = {
        a.channel
        for a in run_two_regime(
            null_stream, baseline,
            DivergenceChannel(baseline, window=window, threshold=div_thr),
            CusumChannel(baseline, threshold=cusum_thr),
        )
    }
    return {
        "false_alarm": {ch: ch in alarms for ch in CHANNELS},
        "horizon": len(null_stream),
        "div_thr": div_thr,
    }


def experiment_null(timelines, window, margin, trials, seed,
                    min_records_, horizon_cap):
    rows = []
    for user in sorted(timelines):
        block = longest_single_version_block(timelines[user], min_records_)
        if block is None:
            continue
        real = null_cell(block, block, window, margin, horizon_cap)
        if real is None:
            continue
        composed = []
        for t in range(trials):
            rng = random.Random(seed + t)
            order = block[:]
            rng.shuffle(order)
            cell = null_cell(block, order, window, margin, horizon_cap)
            if cell:
                composed.append(cell)
        if not composed:
            continue
        rows.append({
            "user": user,
            "n_sessions": len(block),
            "n_records": n_records(block),
            "version": version_of(block[0]),
            "real_fp": real["false_alarm"],
            "real_horizon": real["horizon"],
            "composed_fp": {
                ch: sum(c["false_alarm"][ch] for c in composed) / len(composed)
                for ch in CHANNELS
            },
            "composed_cells": len(composed),
        })
    return rows


# ---------------------------------------------------------------------------
# Experiment 2: real version drift + fake-boundary control
# ---------------------------------------------------------------------------

def boundary_trial(old_block, new_block, window, margin, horizon_cap):
    if len(old_block) < 2:
        return None
    parts = split_at_fractions(old_block, (2 / 3,))
    if parts is None:
        return None
    adm, cal = parts
    admission, calibration = concat(adm), concat(cal)
    stream = concat(new_block)[:horizon_cap]
    if len(calibration) <= window or len(stream) <= window:
        return None
    baseline = freeze_baseline(admission)
    div_thr, cusum_thr = calibrate(baseline, calibration, window, margin)
    alarms = {
        a.channel: a.event_index
        for a in run_two_regime(
            stream, baseline,
            DivergenceChannel(baseline, window=window, threshold=div_thr),
            CusumChannel(baseline, threshold=cusum_thr),
        )
    }
    return {
        "detected": {ch: ch in alarms for ch in CHANNELS},
        "delay": alarms,
        "jsd": js_divergence(tool_distribution(concat(old_block)),
                             tool_distribution(concat(new_block))),
        "horizon": len(stream),
    }


def experiment_version(timelines, window, margin,
                       min_admission, min_new, horizon_cap):
    real_rows, control_rows = [], []
    for user in sorted(timelines):
        blocks = version_blocks(timelines[user])
        # real boundaries: adjacent version blocks with enough mass; an
        # empty version string is *unknown*, not a verified change, so
        # neither side of a boundary (nor a control block) may carry one
        for (v_old, b_old), (v_new, b_new) in zip(blocks, blocks[1:]):
            if not v_old or not v_new:
                continue
            if n_records(b_old) < min_admission or n_records(b_new) < min_new:
                continue
            cell = boundary_trial(b_old, b_new, window, margin, horizon_cap)
            if cell is None:
                continue
            gap_days = (b_new[0][0].ts - b_old[-1][-1].ts) / 86400.0
            real_rows.append({
                "user": user, "old": v_old, "new": v_new,
                "n_old": n_records(b_old), "n_new": n_records(b_new),
                "gap_days": gap_days, **cell,
            })
        # control: fake boundary at ~60% of any single big block
        for v, block in blocks:
            if not v:
                continue
            if n_records(block) < min_admission + min_new or len(block) < 3:
                continue
            parts = split_at_fractions(block, (0.6,))
            if parts is None:
                continue
            fake_old, fake_new = parts
            if n_records(fake_old) < min_admission or n_records(fake_new) < min_new:
                continue
            cell = boundary_trial(fake_old, fake_new, window, margin, horizon_cap)
            if cell is None:
                continue
            control_rows.append({"user": user, "version": v, **cell})
    return real_rows, control_rows


# ---------------------------------------------------------------------------
# Experiment 3: fingerprint accounting (plain JSD, no detector)
# ---------------------------------------------------------------------------

def experiment_fingerprint(timelines, block_size):
    streams = {u: concat(timelines[u]) for u in sorted(timelines)}
    users2 = [u for u, s in streams.items() if len(s) >= 2 * block_size]
    users4 = [u for u, s in streams.items() if len(s) >= 4 * block_size]

    def dist(recs):
        return tool_distribution(recs)

    within_adjacent = [
        js_divergence(dist(streams[u][:block_size]),
                      dist(streams[u][block_size:2 * block_size]))
        for u in users2
    ]
    within_lagged = [
        js_divergence(dist(streams[u][:block_size]),
                      dist(streams[u][-block_size:]))
        for u in users4
    ]
    between = [
        js_divergence(dist(streams[a][:block_size]),
                      dist(streams[b][:block_size]))
        for i, a in enumerate(users2)
        for b in users2[i + 1:]
    ]

    # aging curve: JSD(block 0, block k) and day lag, median across users
    aging: dict[int, list[tuple[float, float]]] = {}
    for u, s in streams.items():
        n_blocks = len(s) // block_size
        if n_blocks < 3:
            continue
        b0 = s[:block_size]
        d0 = dist(b0)
        t0 = statistics.median(r.ts for r in b0)
        for k in range(1, n_blocks):
            blk = s[k * block_size:(k + 1) * block_size]
            lag_days = (statistics.median(r.ts for r in blk) - t0) / 86400.0
            aging.setdefault(k, []).append((js_divergence(d0, dist(blk)), lag_days))

    def q(values):
        vs = sorted(values)
        return {
            "n": len(vs),
            "median": statistics.median(vs) if vs else None,
            "q1": vs[len(vs) // 4] if vs else None,
            "q3": vs[(3 * len(vs)) // 4] if vs else None,
        }

    return {
        "block_size": block_size,
        "within_adjacent": q(within_adjacent),
        "within_lagged": q(within_lagged),
        "between_users": q(between),
        "aging": {
            k: {
                "n": len(cells),
                "median_jsd": statistics.median(j for j, _ in cells),
                "median_lag_days": statistics.median(l for _, l in cells),
            }
            for k, cells in sorted(aging.items())
        },
    }


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _pct(x: float) -> str:
    return f"{x:.0%}"


def render_markdown(agent, args, null_by_margin, version_by_margin, fingerprint,
                    n_users_total) -> str:
    lines = [
        "# Real-timeline experiments on SWE-chat (E5)",
        "",
        f"Ledger agent `{agent}`, {n_users_total} users total; divergence window "
        f"{args.window}, margins {', '.join(str(m) for m in args.margins)}, "
        f"{args.trials} composed trials (seed base {args.seed}), "
        f"min block {args.min_records} records, version boundaries at "
        f">= {args.min_admission} old / >= {args.min_new} new records, "
        f"streams capped at {args.horizon_cap} events.",
        "",
        "Real wall-clock session order; the composed arm re-shuffles the same",
        "sessions under the companion protocol. See module docstring.",
    ]

    for margin in args.margins:
        rows = null_by_margin[margin]
        lines += [
            "",
            f"## Null stability, real vs composed order (margin {margin})",
            "",
            "One cell per user: longest contiguous same-CLI-version session",
            "block, 50/25/25 chronological split; alarms on the null quarter",
            "are false positives. Composed = session order shuffled.",
            "",
            "| arm | users | FP div | FP cusum | median horizon |",
            "|---|---|---|---|---|",
        ]
        if rows:
            n = len(rows)
            real_div = sum(r["real_fp"]["divergence"] for r in rows) / n
            real_cus = sum(r["real_fp"]["cusum"] for r in rows) / n
            comp_div = sum(r["composed_fp"]["divergence"] for r in rows) / n
            comp_cus = sum(r["composed_fp"]["cusum"] for r in rows) / n
            med_h = int(statistics.median(r["real_horizon"] for r in rows))
            lines.append(f"| real (chronological) | {n} | {_pct(real_div)} "
                         f"| {_pct(real_cus)} | {med_h} |")
            lines.append(f"| composed (shuffled x{args.trials}) | {n} | "
                         f"{_pct(comp_div)} | {_pct(comp_cus)} | {med_h} |")

    for margin in args.margins:
        real_rows, control_rows = version_by_margin[margin]
        lines += [
            "",
            f"## Real CLI version drift (margin {margin})",
            "",
            "Boundaries read off the records: baseline on ~2/3 of the old",
            "version block, calibration on the rest, the new version block",
            "streamed. Control = identical protocol at a fake boundary at",
            "~60% of single-version blocks.",
            "",
            "| arm | boundaries | det div | det cusum | median JSD | median delay div | median delay cusum |",
            "|---|---|---|---|---|---|---|",
        ]
        for name, rows in (("real version change", real_rows),
                           ("control (no change)", control_rows)):
            if not rows:
                lines.append(f"| {name} | 0 | — | — | — | — | — |")
                continue
            n = len(rows)
            det = {ch: sum(r["detected"][ch] for r in rows) / n for ch in CHANNELS}
            jmed = statistics.median(r["jsd"] for r in rows)

            def med_delay(ch):
                ds = [r["delay"][ch] for r in rows if ch in r["delay"]]
                return int(statistics.median(ds)) if ds else "—"

            lines.append(
                f"| {name} | {n} | {_pct(det['divergence'])} | {_pct(det['cusum'])} "
                f"| {jmed:.3f} | {med_delay('divergence')} | {med_delay('cusum')} |")
        if real_rows:
            lines += [
                "",
                "Per-boundary rows (real changes), sorted by JSD:",
                "",
                "| user | old -> new | n old / new | gap days | JSD | div | cusum |",
                "|---|---|---|---|---|---|---|",
            ]
            for r in sorted(real_rows, key=lambda r: -r["jsd"]):
                lines.append(
                    f"| {r['user'][:8]} | {r['old']} -> {r['new']} "
                    f"| {r['n_old']} / {r['n_new']} | {r['gap_days']:.1f} "
                    f"| {r['jsd']:.3f} "
                    f"| {'x' if r['detected']['divergence'] else '.'} "
                    f"| {'x' if r['detected']['cusum'] else '.'} |")

    fp = fingerprint
    lines += [
        "",
        f"## Fingerprint accounting (JSD over {fp['block_size']}-record blocks)",
        "",
        "| comparison | n | median | q1 | q3 |",
        "|---|---|---|---|---|",
    ]
    for key, label in (("within_adjacent", "within user, adjacent blocks"),
                       ("within_lagged", "within user, first vs last block"),
                       ("between_users", "between users, first blocks")):
        s = fp[key]
        if s["n"]:
            lines.append(f"| {label} | {s['n']} | {s['median']:.3f} "
                         f"| {s['q1']:.3f} | {s['q3']:.3f} |")
    lines += [
        "",
        "Aging curve (JSD of block k vs block 0, median across users):",
        "",
        "| k | users | median JSD | median lag days |",
        "|---|---|---|---|",
    ]
    for k, cell in fp["aging"].items():
        if k > 12:
            break
        lines.append(f"| {k} | {cell['n']} | {cell['median_jsd']:.3f} "
                     f"| {cell['median_lag_days']:.1f} |")
    return "\n".join(lines) + "\n"


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("ledger_dir")
    ap.add_argument("--agent", default="claude-code")
    ap.add_argument("--window", type=int, default=50)
    ap.add_argument("--margins", default="2.0,1.2",
                    type=lambda s: [float(x) for x in s.split(",")])
    ap.add_argument("--trials", type=int, default=10)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--min-records", type=int, default=400)
    ap.add_argument("--min-admission", type=int, default=300)
    ap.add_argument("--min-new", type=int, default=150)
    ap.add_argument("--horizon-cap", type=int, default=2000)
    ap.add_argument("--block-size", type=int, default=400)
    ap.add_argument("--out")
    args = ap.parse_args(argv)

    timelines = load_timelines(args.ledger_dir, args.agent)

    null_by_margin = {
        m: experiment_null(timelines, args.window, m, args.trials, args.seed,
                           args.min_records, args.horizon_cap)
        for m in args.margins
    }
    version_by_margin = {
        m: experiment_version(timelines, args.window, m,
                              args.min_admission, args.min_new, args.horizon_cap)
        for m in args.margins
    }
    fingerprint = experiment_fingerprint(timelines, args.block_size)

    md = render_markdown(args.agent, args, null_by_margin, version_by_margin,
                         fingerprint, len(timelines))
    print(md)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(md)
        print(f"written: {args.out}")


if __name__ == "__main__":
    main()
