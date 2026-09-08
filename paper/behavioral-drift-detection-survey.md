# Behavioral Drift in Autonomous LLM-driven Systems: A Survey of Detection Approaches and the Case for Deterministic Detection

> **Working draft v0.2 (2026-09-08). Not for circulation.**
> Authors: Jürgen Eckel, Joerg Radehaus (KYDE).

## Abstract

Autonomous systems whose decisions are made by large language models change their behavior over time. The same system, given the same task, does not reliably take the same actions weeks later. The literature calls this behavioral drift, but the term covers at least seven distinct phenomena with different causes, different detection costs, and different regulatory consequences. We survey the current detection landscape across eight recent works, from composite stability metrics and formal non-identifiability results to runtime governance frameworks and lightweight black-box detectors. Three findings stand out. First, real-time drift detection is feasible today: the demonstrated cost ranges from under 10 milliseconds per action to roughly 164 milliseconds per prompt (the units differ with the observation point), and the field has independently converged on divergence measures over tool-usage distributions as its standard signal. Second, reported detection performance is not comparable across works: the units differ (detection rate, ROC AUC, detection delay, violation counts), no paper breaks down performance by drift type, and every evaluation rests on synthetic or LLM-labeled ground truth. Third, and central to our argument: the detection cores of all surveyed systems are deterministic statistics, while LLM judges appear only in evaluation and diagnosis roles. This is not an accident. A judge that is itself an LLM-driven agent is subject to the same drift phenomena it is supposed to detect, and recent evidence shows that models alter their behavior when they suspect they are being evaluated. We argue that drift detection intended to carry operational or evidentiary weight must therefore be deterministic and reproducible from operational records, with LLM judgment reserved for out-of-band diagnosis under human review. We close with a detectability matrix mapping the seven drift phenomena to what can and cannot be established from boundary call records alone.

## 1. Introduction

When an LLM-driven autonomous system operates in production for weeks, its behavior is not a constant. Context accumulates, memory persists, models get swapped by their vendors, goals compete with environmental pressure, and multi-step delegation passes intent through several hands. The resulting deviation from the originally certified or intended behavior has acquired a name, behavioral drift, and an urgency: under Article 72 of the EU AI Act, providers of high-risk systems must actively monitor performance across the lifecycle, and under Article 12 they must keep records that make lifecycle behavior traceable. An operator who cannot measure whether a system's behavior has changed cannot meet either obligation.

Yet "behavioral drift" is not one thing. Section 2 distinguishes seven phenomena that the literature groups under the term. They differ in cause, in observability, and in what it costs to detect them. Conflating them produces talking past one another, and, worse, produces detection claims that quietly hold for the cheap phenomena while implying coverage of the expensive ones.

This paper makes three contributions:

1. **A survey** of eight recent detection approaches (Section 3), compared along data requirements, real-time capability, and runtime complexity (Section 5).
2. **A detectability matrix** (Section 4) that crosses the seven drift phenomena with detection evidence, reported performance, and observability from operational call records. To our knowledge no prior work differentiates detection performance by drift type.
3. **An argument** (Section 6): the field's detection cores are already deterministic, its LLM components are confined to evaluation and diagnosis, and this separation should be made explicit as a design requirement, because an LLM judge is itself a drifting system.

## 2. What drifts: seven phenomena, two taxonomies

### 2.1 The operational taxonomy

We derive the split from the surveyed corpus itself, by asking three questions that every reported deviation answers differently: what drives it (the assigned goal, the growing context, a mis-specified reward, the evaluation setting, another agent, a memory store, or the vendor), where it can be observed (in the action stream, in outcomes, or only in model internals), and whether it outlives the session. Partitioning the reported phenomena along these three axes yields seven classes that neither collapse into one another nor leave a surveyed observation unplaced; each is anchored in its primary literature per row of Table 2:

1. **Goal drift.** The system departs from its assigned objective during a task (Arike et al. 2025).
2. **Context decay.** Performance degrades as context grows; the dominant failure is premature termination, not confusion (Laban et al. 2025; Xia et al. 2026).
3. **Reward hacking.** The system satisfies the measured proxy rather than the intent; the goal was mis-specified from the start (Çağatan and Zhao 2026).
4. **Deception.** The system behaves differently under test than in operation (Apollo Research 2024; Anthropic and Redwood Research 2024).
5. **Multi-agent drift.** Deviation propagates through a group; notably, drift is inherited through transcripts handed from one system to the next (Menon et al. 2026), which moves the correct measurement point to the seam between systems.
6. **Persistent drift.** Memory or self-modification makes the deviation durable, converting an incident into a state (Lin et al. 2026).
7. **Version drift.** The vendor swaps or updates the underlying model; behavior changes without any action by the operator (Chen, Zaharia, Zou 2023).

A related three-way split from the field, semantic vs. coordination vs. behavioral drift (Rath 2026), is useful as vocabulary but is orthogonal to the above: each of Rath's manifestations can arise from several of the seven causes.

### 2.2 The legal taxonomy

For regulatory consequences a second, coarser taxonomy applies (Nannini et al. 2026, arXiv:2604.04604): **anticipated adaptation** (planned, within specified parameters), **continuous learning** (gradual shift driven by data the system encounters), and **emergent drift** (unplanned change that no one specified and no one can derive from the code). The legal anchor is Article 3(23) AI Act, "substantial modification": at some degree of drift the deployed system is no longer the system that was assessed. The pivotal property is not drift itself, systems are expected to adapt, but whether the drift is traceable: whether the operator can show how and when behavior changed. Table 2 carries this mapping as a column.

### 2.3 Drift versus hijack: where prompt injection sits

Our taxonomy is organized by phenomenon, not by cause, and prompt injection is a cause. It deserves explicit placement because it produces three of the seven phenomena while belonging, in the strict sense, to none of them:

- **Injected and persisted:** an injection that survives the session through memory or self-modification is persistent drift (type 6). This is the best-studied case; the self-evolving-systems literature shows precisely how a transient injection becomes a durable behavior.
- **Injected through a hand-over:** modern models resist direct attacks but adopt drift when fed the transcript of a weaker predecessor. Inherited drift is, in effect, injection riding the seam between systems (type 5).
- **Injected in-session:** a successful injection produces an abrupt change of effective objective. Behaviorally this resembles goal drift (type 1), but the goal-drift literature deliberately studies the opposite regime: gradual, endogenous deviation under environmental pressure, with nudges that never directly instruct a goal change.

The security literature keeps the two apart for good reason: in the taxonomy of the OWASP Agentic Security Initiative, goal hijack (ASI01) requires an attacker, while rogue behavior (ASI10) is the only category that does not. We adopt the same line: **drift is endogenous and gradual; hijack is exogenous and abrupt.** The distinction is not academic, because it splits the detection problem into two statistical regimes (Section 5): the field's standard toolkit of sliding windows and exponential smoothing is a low-pass filter by construction, tuned for creep and slow on jumps, and the one surveyed guarantee of bounded detection delay explicitly assumes bounded drift and breaks under abrupt shifts.

One structural observation favors detection at the system boundary specifically: injection is the rare drift cause where the cause itself crosses the observation point. The injected content arrives in a request that traverses the boundary, and the behavioral change appears in the subsequent calls that traverse it too. Correlating suspicious inbound content at time t with a distribution shift after t is therefore possible from boundary records, whereas output-side observability sees only the effect, and each vendor's own console sees only its own slice of the interaction.

### 2.4 Relation to classical concept drift

The statistical machinery this field has converged on is not new. Sliding-window divergence, exponential smoothing, and change-point statistics descend directly from concept-drift detection in data streams: CUSUM goes back to Page (1954), adaptive windowing to ADWIN (Bifet and Gavaldà 2007), and the taxonomy of gradual versus abrupt drift was mapped by Gama et al. (2014) a decade before LLM agents existed. Behavioral drift is not that literature re-badged, but its statistics applied to a harder source: the monitored distribution is an agent's action stream rather than a feature or label stream; the measured system can act on, and in the persistent case rewrite, the state its measurement depends on, which is why the baseline must be frozen and the record integrity-protected (Sections 3 and 6); and the verdict carries regulatory rather than model-maintenance consequences (Section 2.2). The lineage supplies the detectors; the agentic setting supplies the requirements the rest of this paper is about.

## 3. The detection landscape

We group eight recent works by their role.

**Composite metrics.** The Agent Stability Index (Rath 2026, arXiv:2601.04170) aggregates twelve metrics in four weighted families (response consistency, tool usage, coordination, behavioral boundaries) over rolling 50-interaction windows. Detection inputs are full interaction logs including tool calls with parameters; no model internals. Its empirical claims are projections from simulation and should be cited for the metric construction, not the numbers.

**Formal limits of enforcement.** The Non-Identifiability Theorem (Fernandez 2026, arXiv:2604.17517) proves that under a local observability assumption, which holds for practically all guardrails, schema validators and policy engines, no measurable function of the enforcement signal can reconstruct membership in the admissible behavior space: deviation can grow arbitrarily while the enforcement signal stays silent. The proposed remedy is an invariant measurement layer computing Jensen-Shannon divergence between current and admission-time tool distributions against a frozen snapshot, with a proven finite detection delay under bounded drift. Two design lessons: measurement must sit above enforcement, and the baseline must be frozen, because rolling baselines let a drifting system become its own reference ("reference contamination").

**Runtime governance frameworks.** MI9 (Wang et al. 2025, arXiv:2508.03858) combines an agentic telemetry schema, a conformance engine compiling temporal policies to finite-state machines, and goal-conditioned drift detection: baselines are kept per objective, drift within a stable goal is suspicious, drift accompanied by a verified goal change is legitimate adaptation. Agent Behavioral Contracts (Bhardwaj 2026, arXiv:2602.22302) evaluates declarative contracts per action in under 10 ms and adds a leading indicator: Jensen-Shannon divergence between the observed action distribution and a calibrated reference fires before any explicit violation. The Agent Viability Framework (Marín and Chaudhary 2026, arXiv:2604.24686) contributes a fail-secure, monotonically restrictive pipeline with dual-channel KL divergence and bandit-tuned thresholds; it is analytical only, with empirical evaluation left to future work.

**Lightweight black-box detection.** Nautilus Compass (Wang 2026, arXiv:2605.09863) scores each prompt against curated behavioral anchors via embeddings, at roughly 164 ms per check on CPU, reaching held-out ROC AUC 0.83 on real coding-agent traces. It also names its own ceiling: drift whose surface text looks innocuous cannot be caught black-box; activation-based approaches (Abdelnabi et al., SaTML 2025) are the white-box counterpart.

**Recovery.** A graph-based RL framework (El Hamraoui et al. 2026, arXiv:2608.14109) externalizes drift diagnosis and recovery into a small trained model with specialized roles per graph node. Notably, recovery quality depends on knowing the suspected drift onset, which presupposes a detection layer with a trustworthy timeline.

**Measurement of the phenomenon itself.** The goal-drift evaluations (Arike et al. 2025, arXiv:2505.02709) score drift behaviorally against a baseline run, with two scores: commission (misaligned actions taken) and omission (aligned actions not taken). Omission consistently exceeds commission. For log-based detection this is a key insight: the absence of expected calls is a stronger drift signal than the presence of wrong ones.

## 4. Detection performance: what is reported, and what is not differentiated

Reported figures are not comparable across works. The units differ, and every ground truth is synthetic or LLM-labeled.

**Table 1: Reported detection performance.**

| Work | Reported figure | Ground truth |
|---|---|---|
| MI9 | 99.81% detection rate, 0.012% FPR (baselines: OTel+OPA 93.98%, LangSmith+OPA 68.52%) | 1,033 synthetic, LLM-generated scenarios, LLM judge |
| Nautilus Compass | ROC AUC 0.83 held-out (keyword 0.62, zero-shot SBERT 0.75) | real traces, labels from an LLM |
| Invariant measurement layer | detection within 9 to 258 steps of onset; enforcement fired zero times | 3 simulated scenarios, mock LLM |
| Behavioral Contracts | 5.2 to 6.8 violations per session missed by baselines; drift bounded below 0.27 | 1,980 sessions, LLM judge primary, human annotation as anchor |
| Agent Stability Index | drift onset at median 73 interactions; thresholds definitional, no rate | simulation, self-labeled |
| Agent Viability Framework | none (analytical) | none |
| Graph-based RL recovery | recovery accuracy +32.5%; measures diagnosis and recovery, not detection | AppWorld multi-step scenarios, LLM judge |
| Goal-drift evaluations | drift occurrence 0.25 to 0.93 depending on setting; measures occurrence, not detection | the behavioral score is the ground truth |

The sharpest instance is the best-looking number in the table. By our own argument (Section 6), an LLM judge is an unstable measurement instrument, so MI9's 99.81% rests on exactly the kind of ground truth this paper contends cannot carry evidentiary weight. We do not conclude the number is wrong, only that no one can currently show it is right. The obvious replacement does not scale: human annotation at the volumes where drift becomes measurable, weeks of operation and thousands of actions, is not a realistic evaluation regime. Two scalable paths remain. For judged phenomena, an LLM judge anchored by human annotation on a sample, as Behavioral Contracts does, keeps a human-checked error bound at machine throughput. For the deterministic rows of Table 2, ground truth can come from events that are themselves in the record, version changes, declared goal changes, deliberately injected canary tasks, and then no judgment is needed at all.

No surveyed work breaks detection performance down by drift type. Each work selects one phenomenon, defines one metric, and evaluates against self-constructed truth. The matrix that an operator actually needs, drift type crossed with data access and detection performance, does not exist in the literature. Table 2 is our proposal for its structure, filled with what the literature supports today.

**Table 2: Detectability matrix (the central table).**

| Drift type | Legal class (Nannini et al. 2026) | Best available evidence | Detection rate reported? | Detectable from boundary call records? |
|---|---|---|---|---|
| Goal drift | emergent, or continuous learning | occurrence scores (Arike); goal-conditioned baselines, synthetic (MI9) | none on real tasks | partially: requires a declared goal per run and an end-of-run check; strongest log signal is omission (expected calls that stop appearing) |
| Context decay | anticipated to emergent | phenomenon quantified (Laban; Xia); no detector benchmarked | none | yes, cheap: abort and error rate as a function of run length is directly in the log |
| Reward hacking | mis-specification, outside the drift triad proper | exploitation rates 0 to 13.9% per model (Thaman); roughly three quarters of exploit attempts carry explicit justification in the reasoning trace | no runtime detector exists | no: ground truth about the intended outcome must be established per deployment; the intent sits in the reasoning trace, which does not cross the boundary |
| Deception / scheming | emergent | activation probes are the only candidates; models increasingly detect that they are being evaluated, corrupting the measurement | none robust | no: the black-box ceiling; must be scoped out honestly |
| Multi-agent drift | emergent | coordination metrics in simulation only; inherited drift moves the measurement point to the seam; no benchmark exists | none | partially: visible where the seam itself crosses the boundary (tool and delegation routing); otherwise requires a process object above the call chain |
| Persistent drift | continuous learning | attack persistence up to 100% in self-evolving frameworks; scanners catch 2.5%; these are attacker success rates, not detector performance | none | indirectly: the persistent effect appears as a durable distribution shift in the log; direct memory inspection requires per-framework integration |
| Version drift | triggers reassessment questions directly | phenomenon shown (Chen, Zaharia, Zou); no detector benchmarked | none | yes, cheapest: model and version are fields on every record; segmentation suffices |

A note on cause versus phenomenon: prompt injection appears in this table three times without owning a row. Its persisted form is type 6, its hand-over form is type 5, and its in-session form mimics type 1 in the abrupt regime (Section 2.3). A detector that claims coverage of "drift caused by injection" must therefore state which of these three it means, and for the in-session form it must run change-point statistics, not only windowed divergence (Section 5).

Two readings follow. First, the drift types with deterministic, log-computable detectors (context decay, version drift, distributional drift, and the countable failure classes of goal persistence: duplicate submission, premature abort, false success claims, missing progress) are exactly the types for which credible numbers can be produced at all. Second, the types whose ground truth would first have to be defined by an LLM judgment (goal drift on open-ended tasks, deception) are exactly where the regress problem of Section 6 lives.

## 5. Real-time feasibility and runtime complexity

Real-time detection is feasible and demonstrated, with a consistent architecture across all surveyed systems: cheap statistics in the hot path, expensive diagnosis out of band.

| Method | Online? | Cost per event | Complexity |
|---|---|---|---|
| Contract or predicate checking | yes, per action | under 10 ms | linear in constraints and action vocabulary, incrementally computable |
| KL or JS divergence over tool distributions, sliding window | yes, streaming | negligible | O(V) per update, V the tool vocabulary; EMA smoothing O(1) |
| Temporal policy conformance (compiled FSM) | yes, per event | negligible | amortized O(1) per event |
| Embedding-anchor scoring | yes, per prompt | approx. 164 ms CPU | O(N·d) after one encoder pass |
| Statistical process control, adaptive thresholds | yes | negligible | O(W) per window |
| Deep statistical inference (bootstrap, HAC errors) | on demand | O(B·W), B around 1000 | deliberately kept out of the request path |
| LLM-as-judge scoring | offline or batch | one model call | too slow and too costly for the hot path; see Section 6 |
| Activation probes | yes, white-box only | forward-pass access | unavailable without model access |

Two theoretical notes: the invariant measurement layer proves a finite detection delay under bounded drift, an assumption that breaks for abrupt shifts such as prompt injection, and the contracts framework shows drift scores are incrementally computable, so no window recomputation is needed.

The drift-versus-hijack split of Section 2.3 translates here into a two-regime requirement on the same signal. Windowed divergence with exponential smoothing detects creep and deliberately suppresses jumps; the abrupt regime calls for change-point statistics (the CUSUM family and sequential probability ratio tests), which are equally deterministic, equally cheap per event, and better at step changes than at slow deviation. A deployed detector should run both against the same frozen baseline: the change-point channel answers "did behavior jump after this input", the divergence channel answers "has behavior wandered over weeks". Both remain reproducible from the record alone. The practical consequence stands: distributional and rule-based drift detection belongs at the sensor, at single-digit millisecond cost, while calibration, deep inference and semantic diagnosis belong in a control plane outside the request path.

## 6. The judge regress: why the detection core must be deterministic

Across all surveyed systems, LLMs appear in three roles that must not be conflated:

1. **Detection:** absent. Every hot-path detector surveyed is deterministic statistics. Where a model appears in the path at all, it is a frozen embedding encoder performing a deterministic forward pass, not an agent forming judgments.
2. **Evaluation:** pervasive. Detection benchmarks are scored by LLM judges over synthetic scenarios in most surveyed works. This is a ground-truth convenience, and a threat to validity that the works themselves acknowledge.
3. **Diagnosis and recovery:** emerging. Small trained models classify drift and propose recovery, downstream of detection.

We argue this separation is not incidental but necessary, for three reasons.

**The regress argument.** A judge that is itself an LLM-driven agent is subject to every phenomenon in Table 2. It can drift with context, change with vendor versions, and pattern-match instead of judging as its input grows. Using such a judge as the detector replaces one unmeasured system with two. The literature offers direct evidence that monitors are themselves measurement objects: anti-scheming training reduces covert behavior without eliminating it while models grow increasingly aware of being evaluated (Schoen et al. 2025 / OpenAI and Apollo Research, arXiv:2509.15541), and dedicated benchmarks exist precisely to measure how well monitor models notice sabotage (SHADE-Arena; Kutasov et al. 2025, arXiv:2506.15740). A detection layer whose verdicts must hold up over months cannot rest on a component whose own stability is an open research question.

**The reproducibility argument.** A drift verdict has consequences: trust downgrades, restricted permissions, escalation to a human. Consequential verdicts invite dispute, and a disputed verdict must be recomputable. Deterministic statistics over an append-only operational record are reproducible by a third party from the record alone: same log, same score. A judge call is not, in general: model versions change, sampling varies, and the judge's provider logs only its own slice of the interaction. Signed, independent records raise the evidentiary weight of what happened, integrity one can demonstrate rather than assert; a detection layer should preserve that property rather than dilute it.

**The baseline argument.** Frozen baselines are the field's answer to reference contamination, and an append-only, cryptographically chained record makes every past window an integrity-protected baseline candidate, with goal changes present in the record as events. This resolves the tension between the frozen-snapshot school and the goal-conditioned school: both baselines can be served from the same immutable history.

These arguments rest on three assumptions about the record, which we make explicit rather than inherit silently. Completeness: every consequential action crosses the instrumented boundary; an agent with an uninstrumented side channel, a direct network path or a tool invoked outside the gateway, is invisible to any log-based detector. Integrity and order: the record is append-only and tamper-evident (hash-chained, signed), so the timeline a verdict rests on cannot be rewritten by the system it judges. Attribution: each record names the agent, model and version that produced the call. A violation of these is not drift but instrumentation failure or attack, and belongs to a different threat model; a deployment that cannot establish them should not expect evidentiary weight from anything computed downstream.

The honest boundary of the claim: deterministic boundary detection cannot see everything. Deception with innocuous surface behavior, and drift whose evidence exists only in reasoning traces or in memory stores, remain out of reach without model or framework access (Table 2). The conclusion is not that LLM judgment is useless, but that it belongs out of band, in diagnosis, where a human reviews its output, and never as the component whose verdict is the system of record.

## 7. Conclusion and outlook

The field has, without coordinating, already built the answer to its own reliability problem: deterministic detection cores, statistical baselines, and LLM judgment pushed to the edges. What it has not done is (a) differentiate detection performance by drift phenomenon, (b) evaluate on real operational data rather than synthetic scenarios, and (c) state the determinism requirement explicitly. This survey addresses (a) structurally with Table 2 and argues (c). Addressing (b), filling Table 2 with detection numbers measured on real multi-week operational records rather than "none", is the immediate next step, and the subject of our follow-up work on measuring drift from signed boundary call records alone. Reference implementations of the Section 5 detector set, the two-regime distributional detector and the per-type detectors of Table 2, together with a synthetic validation harness, accompany this paper as standard-library Python, so that every verdict is recomputable from a record stream alone.

Beyond filling the matrix, one direction promises earlier and sharper detection: per-agent task models. Production agents spend most of their operation on recurring tasks, and the record already contains the evidence of that recurrence: runs cluster by goal, call-sequence shape, and duration. Mining these recurring tasks from the record, trace clustering and process discovery in the sense of the process-mining literature (van der Aalst 2016), yields a per-agent, per-task reference model, expected call sequences, branching probabilities, duration envelopes, that is far tighter than a global tool distribution. Three gains follow. Conditioning detection on the identified task narrows the variance a detector must tolerate, so smaller deviations become significant sooner. Sequence-level conformance against a task model catches ordering drift that any bag-of-calls divergence is blind to. And a single run can be scored against its task model, turning window-scale detection into run-scale detection: the deviant run is flagged, not the deviant week. The determinism requirement of Section 6 carries over unchanged, and this is the design constraint that makes the direction viable rather than a reintroduction of the judge: task models are learned out of band, then frozen and fingerprinted exactly like baselines, so that runtime scoring remains a deterministic function of model and record. In the terms of Section 3, this is the goal-conditioned school taken one step further, with the condition discovered from the record instead of declared.

## Disclosure

Literature search, screening, and the initial extraction of the figures reported in Tables 1 and 2 were assisted by a large language model. Consistent with the argument of Section 6, this assistance was treated as out-of-band tooling, not as a source of record: every citation, quotation, and numerical figure was verified by the authors against the cited source before submission, and the authors take full responsibility for the content. No LLM contributed to the paper's claims or conclusions as an author.

## References

- Abdelnabi et al. Get my drift? Catching LLM task drift with activation deltas. arXiv:2406.00799; IEEE SaTML 2025.
- Anthropic, Redwood Research (Greenblatt et al.). Alignment faking in large language models. arXiv:2412.14093, 2024.
- Apollo Research (Meinke et al.). Frontier models are capable of in-context scheming. arXiv:2412.04984, 2024.
- Arike, Donoway, Bartsch, Hobbhahn. Evaluating goal drift in language model agents. AIES 2025; arXiv:2505.02709.
- Bhardwaj. Agent behavioral contracts: formal specification and runtime enforcement for reliable autonomous AI agents. arXiv:2602.22302, 2026.
- Bifet, Gavaldà. Learning from time-changing data with adaptive windowing. SDM 2007.
- Çağatan, Zhao. Reward hacking in language model agents: revisiting AI safety gridworlds. arXiv:2606.15385, 2026.
- Chen, Zaharia, Zou. How is ChatGPT's behavior changing over time? arXiv:2307.09009, 2023.
- El Hamraoui, Jose, Bureau, Plana. A graph-based reinforcement learning framework for structured drift diagnosis and recovery in autonomous LLM agents. arXiv:2608.14109, 2026.
- Fernandez. From admission to invariants: measuring deviation in delegated agent systems. arXiv:2604.17517, 2026.
- Gama, Žliobaitė, Bifet, Pechenizkiy, Bouchachia. A survey on concept drift adaptation. ACM Computing Surveys 46(4), 2014.
- Kutasov et al. SHADE-Arena: evaluating sabotage and monitoring in LLM agents. arXiv:2506.15740, 2025.
- Laban et al. LLMs get lost in multi-turn conversation. arXiv:2505.06120, 2025; ICLR 2026.
- Lin, Deng, Li et al. Safety in self-evolving LLM agent systems: threats, amplification, and case studies. arXiv:2606.23075, 2026.
- Marín, Chaudhary. Governing what you cannot observe: adaptive runtime governance for autonomous AI agents. arXiv:2604.24686, 2026.
- Menon, Saebo, Crosse, Gibson, Jang, Cruz. Inherited goal drift: contextual pressure can undermine agentic goals. arXiv:2603.03258, 2026.
- Nannini, Smith, Maggini, Panai, Feliciano, Tiulkanov, Maran, Gealy, Bisconti. AI agents under EU law: a compliance architecture for AI providers. arXiv:2604.04604, 2026 (legal drift classes and traceability); EU AI Act Art. 3(23), Art. 12, Art. 72.
- OpenAI, Apollo Research (Schoen et al.). Stress testing deliberative alignment for anti-scheming training. arXiv:2509.15541, 2025.
- OWASP GenAI Security Project. OWASP Top 10 for Agentic Applications 2026 (ASI01: Agent Goal Hijack; ASI10: Rogue Agents).
- Page. Continuous inspection schemes. Biometrika 41(1/2), 1954.
- Rath. Agent drift: quantifying behavioral degradation in multi-agent LLM systems over extended interactions. arXiv:2601.04170, 2026.
- Thaman. Reward hacking benchmark: measuring exploits in LLM agents with tool use. arXiv:2605.02964, ICML 2026.
- van der Aalst. Process mining: data science in action. 2nd ed., Springer, 2016.
- Wang. Nautilus Compass: black-box persona drift detection for production LLM agents. arXiv:2605.09863, 2026.
- Wang, Singhal, Kelkar, Tuo. MI9: an integrated runtime governance framework for agentic AI. arXiv:2508.03858, 2025.
- Xia, Wang, Huang, Liu. Diagnosing and mitigating context rot in long-horizon search. arXiv:2606.29718, 2026.
