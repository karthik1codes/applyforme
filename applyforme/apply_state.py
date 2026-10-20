"""Deterministic application state machine.

The applier used to drive the browser with a fixed ``for step in range(10)`` loop
and no memory of what it had already done.  A button that did not advance the
form was clicked again, the whole application was restarted on the next click,
and a retry could submit a form twice.

This module gives one application attempt an explicit state, a persistent
record, bounded retries, a global step budget, loop detection and a safe cancel
flag.  It is deliberately small and dependency-free so it can be exercised by
tests without a browser.
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable


class ApplyState(str, Enum):
    IDLE = "IDLE"
    JOB_SELECTED = "JOB_SELECTED"
    JOB_DETAILS_LOADED = "JOB_DETAILS_LOADED"
    PROFILE_READY = "PROFILE_READY"
    BROWSER_INITIALIZED = "BROWSER_INITIALIZED"
    NAVIGATING = "NAVIGATING"
    APPLICATION_PAGE_READY = "APPLICATION_PAGE_READY"
    FORM_DETECTED = "FORM_DETECTED"
    FORM_FILLING = "FORM_FILLING"
    FORM_VALIDATING = "FORM_VALIDATING"
    AWAITING_USER_REVIEW = "AWAITING_USER_REVIEW"
    SUBMISSION_IN_PROGRESS = "SUBMISSION_IN_PROGRESS"
    APPLICATION_SUBMITTED = "APPLICATION_SUBMITTED"
    APPLICATION_CONFIRMED = "APPLICATION_CONFIRMED"
    AUTHENTICATION_REQUIRED = "AUTHENTICATION_REQUIRED"
    HUMAN_INTERVENTION_REQUIRED = "HUMAN_INTERVENTION_REQUIRED"
    RETRY_PENDING = "RETRY_PENDING"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    ALREADY_SUBMITTED = "ALREADY_SUBMITTED"


TERMINAL = {
    ApplyState.APPLICATION_CONFIRMED,
    ApplyState.ALREADY_SUBMITTED,
    ApplyState.FAILED,
    ApplyState.CANCELLED,
}

# Preconditions are encoded in this graph.  The only transitions that need
# evidence beyond the graph are enforced in ``transition``.
_TRANSITIONS: dict[ApplyState, set[ApplyState]] = {
    ApplyState.IDLE: {ApplyState.JOB_SELECTED, ApplyState.ALREADY_SUBMITTED, ApplyState.FAILED, ApplyState.CANCELLED},
    ApplyState.JOB_SELECTED: {
        ApplyState.JOB_DETAILS_LOADED, ApplyState.PROFILE_READY, ApplyState.ALREADY_SUBMITTED,
        ApplyState.FAILED, ApplyState.CANCELLED,
    },
    ApplyState.JOB_DETAILS_LOADED: {
        ApplyState.PROFILE_READY, ApplyState.BROWSER_INITIALIZED, ApplyState.ALREADY_SUBMITTED,
        ApplyState.FAILED, ApplyState.CANCELLED,
    },
    ApplyState.PROFILE_READY: {
        ApplyState.BROWSER_INITIALIZED, ApplyState.NAVIGATING, ApplyState.ALREADY_SUBMITTED,
        ApplyState.FAILED, ApplyState.CANCELLED,
    },
    ApplyState.BROWSER_INITIALIZED: {
        ApplyState.NAVIGATING, ApplyState.APPLICATION_PAGE_READY, ApplyState.FORM_DETECTED,
        ApplyState.AUTHENTICATION_REQUIRED, ApplyState.HUMAN_INTERVENTION_REQUIRED,
        ApplyState.RETRY_PENDING, ApplyState.FAILED, ApplyState.CANCELLED,
    },
    ApplyState.NAVIGATING: {
        ApplyState.APPLICATION_PAGE_READY, ApplyState.AUTHENTICATION_REQUIRED,
        ApplyState.HUMAN_INTERVENTION_REQUIRED, ApplyState.RETRY_PENDING,
        ApplyState.FAILED, ApplyState.CANCELLED,
    },
    ApplyState.APPLICATION_PAGE_READY: {
        ApplyState.FORM_DETECTED, ApplyState.AUTHENTICATION_REQUIRED,
        ApplyState.HUMAN_INTERVENTION_REQUIRED, ApplyState.ALREADY_SUBMITTED,
        ApplyState.RETRY_PENDING, ApplyState.FAILED, ApplyState.CANCELLED,
    },
    ApplyState.FORM_DETECTED: {
        ApplyState.FORM_FILLING, ApplyState.NAVIGATING, ApplyState.AUTHENTICATION_REQUIRED,
        ApplyState.HUMAN_INTERVENTION_REQUIRED, ApplyState.RETRY_PENDING,
        ApplyState.FAILED, ApplyState.CANCELLED,
    },
    ApplyState.FORM_FILLING: {
        ApplyState.FORM_VALIDATING, ApplyState.FORM_DETECTED, ApplyState.NAVIGATING,
        ApplyState.AUTHENTICATION_REQUIRED, ApplyState.HUMAN_INTERVENTION_REQUIRED,
        ApplyState.RETRY_PENDING, ApplyState.FAILED, ApplyState.CANCELLED,
    },
    ApplyState.FORM_VALIDATING: {
        ApplyState.FORM_FILLING, ApplyState.AWAITING_USER_REVIEW, ApplyState.FORM_DETECTED,
        ApplyState.SUBMISSION_IN_PROGRESS, ApplyState.ALREADY_SUBMITTED, ApplyState.NAVIGATING,
        ApplyState.AUTHENTICATION_REQUIRED, ApplyState.HUMAN_INTERVENTION_REQUIRED,
        ApplyState.RETRY_PENDING, ApplyState.FAILED, ApplyState.CANCELLED,
    },
    ApplyState.AWAITING_USER_REVIEW: {
        ApplyState.SUBMISSION_IN_PROGRESS, ApplyState.FORM_FILLING, ApplyState.FORM_VALIDATING,
        ApplyState.NAVIGATING, ApplyState.APPLICATION_PAGE_READY, ApplyState.HUMAN_INTERVENTION_REQUIRED,
        ApplyState.CANCELLED, ApplyState.FAILED, ApplyState.RETRY_PENDING,
        ApplyState.ALREADY_SUBMITTED,
    },
    ApplyState.SUBMISSION_IN_PROGRESS: {
        ApplyState.APPLICATION_SUBMITTED, ApplyState.APPLICATION_CONFIRMED,
        ApplyState.AWAITING_USER_REVIEW, ApplyState.FORM_VALIDATING,
        ApplyState.HUMAN_INTERVENTION_REQUIRED,
        ApplyState.FAILED, ApplyState.CANCELLED,
    },
    ApplyState.APPLICATION_SUBMITTED: {ApplyState.APPLICATION_CONFIRMED, ApplyState.FAILED},
    ApplyState.APPLICATION_CONFIRMED: set(),
    ApplyState.AUTHENTICATION_REQUIRED: {
        ApplyState.NAVIGATING, ApplyState.APPLICATION_PAGE_READY, ApplyState.FORM_DETECTED,
        ApplyState.SUBMISSION_IN_PROGRESS, ApplyState.CANCELLED, ApplyState.FAILED,
    },
    ApplyState.HUMAN_INTERVENTION_REQUIRED: {
        ApplyState.FORM_FILLING, ApplyState.FORM_VALIDATING, ApplyState.AWAITING_USER_REVIEW,
        ApplyState.SUBMISSION_IN_PROGRESS, ApplyState.NAVIGATING, ApplyState.APPLICATION_PAGE_READY,
        ApplyState.CANCELLED, ApplyState.FAILED,
    },
    ApplyState.RETRY_PENDING: {
        ApplyState.BROWSER_INITIALIZED, ApplyState.NAVIGATING, ApplyState.APPLICATION_PAGE_READY,
        ApplyState.FORM_DETECTED, ApplyState.FORM_FILLING, ApplyState.FORM_VALIDATING,
        ApplyState.AWAITING_USER_REVIEW, ApplyState.SUBMISSION_IN_PROGRESS,
        ApplyState.HUMAN_INTERVENTION_REQUIRED, ApplyState.CANCELLED, ApplyState.FAILED,
    },
    ApplyState.FAILED: set(),
    ApplyState.CANCELLED: set(),
    ApplyState.ALREADY_SUBMITTED: set(),
}

# A UI-friendly mapping to the dashboard's job status vocabulary.
STATE_TO_JOB_STATUS = {
    ApplyState.FORM_FILLING: "in_progress",
    ApplyState.AWAITING_USER_REVIEW: "awaiting_review",
    ApplyState.APPLICATION_CONFIRMED: "applied",
    ApplyState.APPLICATION_SUBMITTED: "applied",
    ApplyState.ALREADY_SUBMITTED: "applied",
    ApplyState.AUTHENTICATION_REQUIRED: "blocked",
    ApplyState.HUMAN_INTERVENTION_REQUIRED: "manual",
    ApplyState.FAILED: "failed",
    ApplyState.CANCELLED: "cancelled",
}


class ApplyStateError(RuntimeError):
    """A transition or budget was violated."""


class LoopDetected(ApplyStateError):
    """The browser kept showing the same state/action."""


class BudgetExceeded(ApplyStateError):
    """Step or retry budget exhausted."""


class Cancelled(ApplyStateError):
    """The user cancelled this application."""


class _MemoryStore:
    """Fallback for callers that do not pass a Store (tests / dry helpers)."""

    def __init__(self) -> None:
        self.rows: dict[str, dict[str, Any]] = {}

    def apply_session(self, job_id: str) -> dict[str, Any] | None:
        return self.rows.get(job_id)

    def save_apply_session(self, job_id: str, **fields: Any) -> None:
        self.rows.setdefault(job_id, {}).update(fields)

    def add_apply_step(self, *args: Any, **kwargs: Any) -> None:
        return None

    def add_event(self, *args: Any, **kwargs: Any) -> None:
        return None

    def is_apply_cancelled(self, job_id: str) -> bool:
        return bool(self.rows.get(job_id, {}).get("cancel_requested"))

    def apply_submit_authorized(self, job_id: str, after: str | None = None) -> bool:
        value = self.rows.get(job_id, {}).get("submit_authorized_at")
        if not value:
            return False
        return after is None or str(value) >= after

    def submission_recorded(self, job_id: str) -> bool:
        row = self.rows.get(job_id) or {}
        return bool(row.get("submitted_at"))


@dataclass
class Transition:
    from_state: ApplyState
    to_state: ApplyState
    result: str
    detail: str
    signature: str
    at: float


class ApplyStateMachine:
    """One application attempt, persisted per job."""

    def __init__(
        self,
        store: Any | None,
        job_id: str,
        *,
        owner: str = "local",
        max_steps: int = 80,
        max_state_retries: int = 3,
        max_retries: int = 8,
        max_identical: int = 3,
        submit_authorized_after: str | None = None,
        clock: Callable[[], float] = time.time,
        sleeper: Callable[[float], None] = time.sleep,
        backoff_base: float = 0.4,
        backoff_cap: float = 8.0,
        rng: random.Random | None = None,
    ) -> None:
        self.store = store if store is not None else _MemoryStore()
        self.job_id = job_id
        self.owner = owner
        # A prepare run must ignore an authorization left by an earlier run.
        # An explicit submit (or one arriving while this run is waiting) is
        # newer than this floor and is honoured.
        self.submit_authorized_after = submit_authorized_after
        self.max_steps = max_steps
        self.max_state_retries = max_state_retries
        self.max_retries = max_retries
        self.max_identical = max_identical
        self._clock = clock
        self._sleeper = sleeper
        self._backoff_base = backoff_base
        self._backoff_cap = backoff_cap
        self._rng = rng or random.Random()

        row = self.store.apply_session(job_id) or {}
        self.state = _as_state(row.get("state")) or ApplyState.IDLE
        self.step_count = int(row.get("step_count") or 0)
        self.state_attempts = int(row.get("state_attempts") or 0)
        self.retry_count = int(row.get("retry_count") or 0)
        self.last_signature = row.get("last_signature") or ""
        self.duplicate_signature_count = int(row.get("duplicate_signature_count") or 0)
        self.last_error = row.get("last_error") or ""
        self.transitions: list[Transition] = []
        self._started = False

    # ---------------------------------------------------------------- state
    @property
    def terminal(self) -> bool:
        return self.state in TERMINAL

    @property
    def remaining_steps(self) -> int:
        return max(0, self.max_steps - self.step_count)

    def start(self) -> "ApplyStateMachine":
        """Load persisted progress and begin a new attempt without losing it."""
        if self.terminal:
            return self
        if self.state is ApplyState.IDLE:
            self.transition(ApplyState.JOB_SELECTED, result="started", detail="application requested")
        self._started = True
        return self

    def resume(self) -> "ApplyStateMachine":
        """Re-enter a non-terminal persisted state after a browser restart."""
        if self.terminal:
            return self
        if self.state not in (ApplyState.IDLE, ApplyState.JOB_SELECTED, ApplyState.BROWSER_INITIALIZED):
            # A fresh browser is a precondition for every browser phase.  This
            # is the one deliberate graph bypass: resuming must not be blocked
            # by the phase the previous process stopped in.
            self.transition(
                ApplyState.BROWSER_INITIALIZED,
                result="resumed",
                detail=f"browser restarted from {self.state.value}",
                force=True,
            )
        return self

    # ------------------------------------------------------------ transition
    def transition(
        self,
        to: ApplyState | str,
        *,
        result: str = "ok",
        detail: str = "",
        signature: str = "",
        evidence: dict[str, Any] | None = None,
        force: bool = False,
    ) -> None:
        self.check_cancel()
        target = _as_state(to)
        if target is None:
            raise ApplyStateError(f"unknown state {to!r}")

        if target == self.state:
            self.state_attempts += 1
            if self.state_attempts > self.max_state_retries:
                self._fail(
                    f"retry budget exhausted in {target.value}",
                    detail=detail or "same state re-entered too many times",
                )
        else:
            if not force and target not in _TRANSITIONS.get(self.state, set()):
                raise ApplyStateError(f"illegal transition {self.state.value} -> {target.value}")
            self.state_attempts = 0

        if target in (ApplyState.APPLICATION_SUBMITTED, ApplyState.APPLICATION_CONFIRMED):
            self._require_submission_evidence(target, evidence)

        self.step_count += 1
        if self.step_count > self.max_steps:
            self._fail("global step budget exhausted", detail=f"budget={self.max_steps}")

        previous = self.state
        self.state = target
        self.last_error = "" if target not in (ApplyState.FAILED, ApplyState.RETRY_PENDING) else self.last_error
        tr = Transition(previous, target, result, detail, signature, self._clock())
        self.transitions.append(tr)
        self._persist()
        self._record(tr)

        if target is ApplyState.CANCELLED:
            raise Cancelled(detail or "cancelled by user")

    def _require_submission_evidence(self, target: ApplyState, evidence: dict[str, Any] | None) -> None:
        ev = evidence or {}
        confirmation = str(ev.get("confirmation") or "").strip()
        if not confirmation:
            raise ApplyStateError(
                f"cannot enter {target.value} without observable confirmation evidence"
            )
        if ev.get("errors"):
            raise ApplyStateError(
                f"cannot enter {target.value} while validation errors are present"
            )

    def _fail(self, reason: str, *, detail: str = "") -> None:
        previous = self.state
        self.last_error = reason
        self.state = ApplyState.FAILED
        self.step_count += 1
        self._persist()
        self._record(Transition(previous, ApplyState.FAILED, "failed", detail or reason, "", self._clock()))
        raise BudgetExceeded(detail or reason)

    # ---------------------------------------------------------- loop guards
    def observe(self, signature: str) -> None:
        """Record an observation before acting; detect a stuck page."""
        if not signature:
            return
        if signature == self.last_signature:
            self.duplicate_signature_count += 1
            if self.duplicate_signature_count + 1 >= self.max_identical:
                previous = self.state
                detail = (
                    f"the same page/action was observed {self.duplicate_signature_count + 1} times "
                    f"({signature[:160]})"
                )
                self.last_error = "browser loop detected"
                self.state = ApplyState.FAILED
                self.step_count += 1
                self._persist()
                self._record(Transition(previous, ApplyState.FAILED, "loop", detail, signature, self._clock()))
                raise LoopDetected(detail)
        else:
            self.last_signature = signature
            self.duplicate_signature_count = 0
        self._persist()

    def reset_observation(self) -> None:
        self.last_signature = ""
        self.duplicate_signature_count = 0
        self._persist()

    def retry(self, reason: str, *, backoff: bool = True) -> float:
        """Bounded retry with exponential backoff + jitter; returns the sleep time."""
        self.check_cancel()
        self.retry_count += 1
        self.last_error = reason
        if self.retry_count > self.max_retries:
            self._fail("retry budget exhausted", detail=reason)
        delay = 0.0
        if backoff:
            raw = min(self._backoff_cap, self._backoff_base * (2 ** (self.retry_count - 1)))
            delay = raw * self._rng.uniform(0.5, 1.5)
        self._persist()
        self.transition(ApplyState.RETRY_PENDING, result="retry", detail=reason)
        if delay:
            self._sleep_cancellable(delay)
        return delay

    def _sleep_cancellable(self, seconds: float) -> None:
        end = self._clock() + seconds
        while self._clock() < end:
            self.check_cancel()
            self._sleeper(min(0.25, max(0.0, end - self._clock())))

    # ------------------------------------------------------------- cancel
    def check_cancel(self) -> None:
        if self.store.is_apply_cancelled(self.job_id):
            if self.state not in (ApplyState.CANCELLED,) and self.state not in TERMINAL:
                self.state = ApplyState.CANCELLED
                self.step_count += 1
                self._persist()
                self._record(Transition(self.state, ApplyState.CANCELLED, "cancelled", "cancelled by user", "", self._clock()))
            raise Cancelled("cancelled by user")

    # ---------------------------------------------------------- submission
    def submission_already_recorded(self) -> bool:
        return bool(self.store.submission_recorded(self.job_id))

    def authorized_for_submission(self) -> bool:
        return bool(
            self.store.apply_submit_authorized(
                self.job_id, after=self.submit_authorized_after
            )
        )

    def confirm_submission(self, note: str, *, strong: bool = True) -> None:
        evidence = {"confirmation": note, "errors": False}
        self.transition(ApplyState.SUBMISSION_IN_PROGRESS, result="submit", detail="explicit authorization")
        self.transition(ApplyState.APPLICATION_SUBMITTED, result="submitted", detail=note, evidence=evidence)
        if strong:
            self.transition(ApplyState.APPLICATION_CONFIRMED, result="confirmed", detail=note, evidence=evidence)
        if hasattr(self.store, "record_submission_confirmed"):
            self.store.record_submission_confirmed(self.job_id, note)

    # ------------------------------------------------------------ persist
    def _persist(self) -> None:
        self.store.save_apply_session(
            self.job_id,
            state=self.state.value,
            step_count=self.step_count,
            state_attempts=self.state_attempts,
            retry_count=self.retry_count,
            last_signature=self.last_signature,
            duplicate_signature_count=self.duplicate_signature_count,
            last_error=self.last_error,
        )

    def _record(self, tr: Transition) -> None:
        try:
            self.store.add_apply_step(
                self.job_id,
                state=tr.to_state.value,
                result=tr.result,
                detail=tr.detail,
                signature=tr.signature,
            )
        except TypeError:
            # Older/fake stores may not accept keyword arguments.
            self.store.add_apply_step(self.job_id, tr.to_state.value, tr.result, tr.detail, tr.signature)

    def snapshot(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "state": self.state.value,
            "step_count": self.step_count,
            "state_attempts": self.state_attempts,
            "retry_count": self.retry_count,
            "last_error": self.last_error,
            "terminal": self.terminal,
        }


def _as_state(value: Any) -> ApplyState | None:
    if isinstance(value, ApplyState):
        return value
    try:
        return ApplyState(str(value))
    except ValueError:
        return None
