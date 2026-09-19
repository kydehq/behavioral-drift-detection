"""Fast equivalents of the detectors, for the follow-up's content rungs.

detectors.py stays untouched and citable (the L0 results were computed
with it); this module collects implementation-equivalent channels whose
agreement with the originals is asserted by unit tests. The first, the
O(window) ``FastDivergenceChannel``, lives in eval_l1_terminalwrench
where it was introduced; this module adds the O(1) variant that the L2
experiments need — tool-output token streams are an order of magnitude
longer than L1 command streams, and the E1/L1 window sweep already cost
two hours at O(window tokens in window) per event.

``IncrementalDivergenceChannel``: same JSD decomposition as
FastDivergenceChannel (per-token window terms plus a precomputed rest
term over the frozen baseline), but the two window sums are maintained
incrementally — a sliding window changes the count of at most two
tokens per event, so only those tokens' contributions are exchanged.
Floating-point error would random-walk over millions of adds and
subtracts, so the sums are rebuilt from the counts every ``resync``
events; the amortized cost stays O(1).

Equivalence standard (same as FastDivergenceChannel's docstring): the
terms are summed in a different order, so scores agree with
detectors.DivergenceChannel to floating-point tolerance rather than
bit-exactly, and alarm trajectories are asserted identical on synthetic
streams that cross resync boundaries.
"""

from __future__ import annotations

import math

from collections import deque
from dataclasses import dataclass, field
from typing import Optional

from .baseline import FrozenBaseline
from .records import CallRecord

_EPS = 1e-9  # the epsilon of detectors.kl_divergence


@dataclass
class IncrementalDivergenceChannel:
    """detectors.DivergenceChannel in amortized O(1) per event."""

    baseline: FrozenBaseline
    window: int = 50
    alpha: float = 0.1
    threshold: float = 0.15
    patience: int = 5
    resync: int = 4096          # rebuild the sums every this many events

    _buf: deque = field(default_factory=deque)
    _counts: dict[str, int] = field(default_factory=dict)
    _ema: Optional[float] = None
    _over: int = 0
    _since_resync: int = 0

    def __post_init__(self) -> None:
        self._q = self.baseline.tool_dist
        self._qrest = {
            t: qt * math.log2((qt + _EPS) / (0.5 * qt + _EPS))
            for t, qt in self._q.items()
        }
        self._rest_total = sum(self._qrest.values())
        self._sum_p = 0.0       # sum of _contrib(t)[0] over window support
        self._sum_q = 0.0       # sum of _contrib(t)[1] over window support

    def _contrib(self, tok: str, count: int) -> tuple[float, float]:
        """(p-term, q-correction) of one window token at the given count."""
        if count <= 0:
            return 0.0, 0.0
        p_t = count / self.window
        q_t = self._q.get(tok, 0.0)
        m_t = 0.5 * (p_t + q_t)
        p_term = p_t * math.log2((p_t + _EPS) / (m_t + _EPS))
        q_term = 0.0
        if q_t > 0.0:
            q_term = (q_t * math.log2((q_t + _EPS) / (m_t + _EPS))
                      - self._qrest[tok])
        return p_term, q_term

    def _exchange(self, tok: str, old_count: int, new_count: int) -> None:
        old_p, old_q = self._contrib(tok, old_count)
        new_p, new_q = self._contrib(tok, new_count)
        self._sum_p += new_p - old_p
        self._sum_q += new_q - old_q

    def _rebuild(self) -> None:
        self._sum_p = self._sum_q = 0.0
        for tok, count in self._counts.items():
            p_term, q_term = self._contrib(tok, count)
            self._sum_p += p_term
            self._sum_q += q_term
        self._since_resync = 0

    def update(self, rec: CallRecord) -> Optional[float]:
        """Feed one record; returns the smoothed score once the window is full."""
        tok = rec.tool
        old = self._counts.get(tok, 0)
        self._buf.append(tok)
        self._counts[tok] = old + 1
        self._exchange(tok, old, old + 1)

        if len(self._buf) > self.window:
            out = self._buf.popleft()
            old_out = self._counts[out]
            if old_out == 1:
                del self._counts[out]
            else:
                self._counts[out] = old_out - 1
            self._exchange(out, old_out, old_out - 1)

        if len(self._buf) < self.window:
            return None

        self._since_resync += 1
        if self._since_resync >= self.resync:
            self._rebuild()

        score = 0.5 * self._sum_p + 0.5 * (self._rest_total + self._sum_q)
        self._ema = score if self._ema is None else (
            self.alpha * score + (1 - self.alpha) * self._ema
        )
        self._over = self._over + 1 if self._ema > self.threshold else 0
        return self._ema

    @property
    def alarmed(self) -> bool:
        return self._over >= self.patience
