"""Terminal Wrench trajectories -> boundary call record ledgers.

Source: github.com/few-sh/terminal-wrench, ``tasks/<task_id>/<model>/
{hack_trajectories,baseline_trajectories}/<label>/`` — per trajectory a
``metadata.json`` (classification ground truth) and
``trial/agent/trajectory.json`` (ATIF-v1.6: agent steps carrying
``tool_calls``). 331 reward-hackable terminal tasks, three models
(claude-opus-4.6, gemini-3.1-pro, gpt-5.4); the repo's own manifest
counts 3,632 hack and 2,352 baseline trajectories.

Only ``hack_trajectories`` and ``baseline_trajectories`` are converted:
``sanitized_trajectories`` and ``stripped_trajectories`` are derived
transformations of the hack runs (built for the source's monitoring
experiments), not independent agent behavior.

Mapping decisions (nothing the source does not provide is invented):

- One CallRecord per ``tool_calls`` entry of each agent step, in step
  order. For ``bash_command`` the tool is the leading token of the
  ``keystrokes`` string (``mkdir``, ``cat``, ``python3``, ...) — the
  same convention as the SWE-bench sweagent parser, and the choice that
  gives a tool *vocabulary*; the function name alone is near-constant.
  Other functions (``mark_task_complete``) keep their function name.
  The parameter hash covers the canonical JSON of the full arguments.
- ``ts`` is the step's real ISO timestamp (the source records one per
  step), plus 1 ms per within-step call so the ledger stays totally
  ordered. Deterministic from the source; no detector reads ``ts``.
- The source has no per-call status; ``status`` is always "ok" and
  error-rate detectors are out of scope for this corpus. The
  ``duration`` argument of ``bash_command`` is a configured wait, not a
  measurement; ``duration_ms`` stays 0.
- ``agent_id`` is the model directory name (the deployment identity);
  ``model`` carries the ATIF ``agent.model_name`` verbatim;
  ``model_version`` stays "" — the ATIF ``agent.version`` is the
  scaffold version (terminus-2 across the whole corpus), not a model
  version.
- ``goal_id`` = task id; ``run_id`` = "<task>/<tree>/<label>".

Ground truth goes to a labels sidecar per model, keyed by run_id, with
the source's ``classification`` verbatim (``baseline``,
``rewarded_serious_exploit``, ``rewarded_nonserious_hack``,
``attacker_legitimate_solve``, ``no_reward``). Which classes count as
hacked vs. clean is an experiment decision and lives in
``eval_terminalwrench``, not here.

CLI::

    python3 -m driftdetect.adapters.terminalwrench <terminal-wrench-repo>/tasks -o <outdir>

writes ``<outdir>/<model>.jsonl``, ``<model>.labels.json`` and a
``manifest.json`` with the sha256 of every output file — the
fingerprint a verdict names its input by.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os

from ..records import CallRecord, write_jsonl

TREES = ("baseline_trajectories", "hack_trajectories")
TS_FALLBACK = 1_760_000_000.0   # only if a step lacks a parsable timestamp


def _params_hash(args: dict) -> str:
    canon = json.dumps(args, sort_keys=True, default=str)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()[:12]


def _tool_name(call: dict) -> str:
    fn = call.get("function_name") or ""
    keystrokes = (call.get("arguments") or {}).get("keystrokes")
    if fn == "bash_command" and isinstance(keystrokes, str) and keystrokes.split():
        return keystrokes.split()[0]
    return fn


def _step_epoch(step: dict, step_index: int) -> float:
    raw = step.get("timestamp")
    if isinstance(raw, str):
        try:
            return datetime.datetime.fromisoformat(raw).timestamp()
        except ValueError:
            pass
    return TS_FALLBACK + step_index


def convert_trajectory(
    traj: dict, meta: dict, model_dir: str, tree: str, run_id: str
) -> tuple[list[CallRecord], dict]:
    """One ATIF trajectory + its metadata -> (records, label)."""
    if not isinstance(traj, dict) or not isinstance(traj.get("steps"), list):
        raise ValueError("not an ATIF trajectory")
    model_name = ((traj.get("agent") or {}).get("model_name")) or ""
    task_id = str(meta.get("task_id") or run_id.split("/", 1)[0])

    records: list[CallRecord] = []
    step_index = 0
    for step in traj["steps"]:
        if not isinstance(step, dict) or step.get("source") != "agent":
            continue
        epoch = _step_epoch(step, step_index)
        for k, call in enumerate(step.get("tool_calls") or []):
            tool = _tool_name(call)
            if not tool:
                continue
            records.append(CallRecord(
                ts=epoch + k * 0.001,
                run_id=run_id,
                agent_id=model_dir,
                model=model_name,
                model_version="",
                goal_id=task_id,
                step_index=step_index,
                tool=tool,
                params_hash=_params_hash(call.get("arguments") or {}),
                status="ok",
                duration_ms=0.0,
            ))
            step_index += 1

    label = {
        "task_id": task_id,
        "tree": tree,
        "classification": meta.get("classification"),
        "reward": meta.get("reward"),
        "exploit_attempted": meta.get("exploit_attempted"),
        "judged_serious_exploit": meta.get("judged_serious_exploit"),
        "judged_legitimate_solve": meta.get("judged_legitimate_solve"),
        "source_dataset": meta.get("source_dataset"),
        "episode_count": meta.get("episode_count"),
        "n_calls": len(records),
    }
    return records, label


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def convert_tree(tasks_dir: str, out_dir: str) -> dict:
    """Convert all tasks under tasks_dir, one ledger per model."""
    os.makedirs(out_dir, exist_ok=True)
    by_model: dict[str, list[CallRecord]] = {}
    labels_by_model: dict[str, dict[str, dict]] = {}
    n_skipped = 0

    for task_id in sorted(os.listdir(tasks_dir)):
        tdir = os.path.join(tasks_dir, task_id)
        if not os.path.isdir(tdir):
            continue
        for model_dir in sorted(os.listdir(tdir)):
            mdir = os.path.join(tdir, model_dir)
            if not os.path.isdir(mdir):
                continue
            for tree in TREES:
                trdir = os.path.join(mdir, tree)
                if not os.path.isdir(trdir):
                    continue
                for label_dir in sorted(os.listdir(trdir)):
                    meta_path = os.path.join(trdir, label_dir, "metadata.json")
                    traj_path = os.path.join(trdir, label_dir, "trial",
                                             "agent", "trajectory.json")
                    run_id = f"{task_id}/{tree}/{label_dir}"
                    try:
                        with open(meta_path, encoding="utf-8") as fh:
                            meta = json.load(fh)
                        with open(traj_path, encoding="utf-8") as fh:
                            traj = json.load(fh)
                        recs, label = convert_trajectory(
                            traj, meta, model_dir, tree, run_id)
                    except (OSError, ValueError, json.JSONDecodeError,
                            UnicodeDecodeError, KeyError, TypeError):
                        # one malformed trajectory must not kill the corpus
                        n_skipped += 1
                        continue
                    if not recs:
                        n_skipped += 1
                        continue
                    by_model.setdefault(model_dir, []).extend(recs)
                    labels_by_model.setdefault(model_dir, {})[run_id] = label

    manifest: dict = {"source": os.path.abspath(tasks_dir), "models": {},
                      "n_skipped": n_skipped}
    for model_dir in sorted(by_model):
        ledger_path = os.path.join(out_dir, f"{model_dir}.jsonl")
        labels_path = os.path.join(out_dir, f"{model_dir}.labels.json")
        n = write_jsonl(by_model[model_dir], ledger_path)
        with open(labels_path, "w", encoding="utf-8") as fh:
            json.dump(labels_by_model[model_dir], fh, sort_keys=True, indent=1)
        manifest["models"][model_dir] = {
            "ledger": os.path.basename(ledger_path),
            "labels": os.path.basename(labels_path),
            "n_runs": len(labels_by_model[model_dir]),
            "n_records": n,
            "sha256_ledger": _sha256_file(ledger_path),
            "sha256_labels": _sha256_file(labels_path),
        }

    manifest["n_runs_total"] = sum(m["n_runs"] for m in manifest["models"].values())
    manifest["n_records_total"] = sum(m["n_records"] for m in manifest["models"].values())
    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, sort_keys=True, indent=1)
    return manifest


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("tasks_dir", help="path to the terminal-wrench repo's tasks/ directory")
    ap.add_argument("-o", "--out", required=True, help="output directory for ledgers")
    args = ap.parse_args(argv)
    manifest = convert_tree(args.tasks_dir, args.out)
    print(
        f"{len(manifest['models'])} models, "
        f"{manifest['n_runs_total']} runs, "
        f"{manifest['n_records_total']} records "
        f"({manifest['n_skipped']} skipped) -> {args.out}"
    )


if __name__ == "__main__":
    main()
