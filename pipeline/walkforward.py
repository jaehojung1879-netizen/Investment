"""Time-ordered validation — folds, purging, embargo, and a sealed holdout.

Three rules, each of which exists because breaking it is the standard way a
backtest lies:

1. **No random splits.** A shuffled split lets a model train on Thursday to
   predict Wednesday. Every split here is a time cut, and ``assert_ordered``
   refuses a fold whose blocks are out of order.

2. **Purge and embargo.** A signal on date T with a 126-day horizon has an
   outcome that only resolves at T+126. If T sits in train and T+40 sits in
   test, the two observations overlap in real time and the "out-of-sample" test
   is partly in-sample. The gap between blocks is therefore at least the
   horizon, plus an embargo.

3. **The test block decides nothing.** Hyperparameters, thresholds, feature
   sets and calibration curves are all chosen inside train/validation. If the
   test result changed any of them, the number stops being out-of-sample —
   which is why ``nested_folds`` exposes an inner validation split and the outer
   test is only ever scored.

On top of the folds sits ``HoldoutGuard``: the most recent slice of history is
sealed off entirely during development. Nothing reads it until a model is
final. Because a guard that merely asks nicely is no guard, it raises on
access while sealed.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


class HoldoutViolation(RuntimeError):
    """Raised when sealed final-holdout data is touched during development."""


@dataclass(frozen=True)
class Fold:
    """One outer fold. Blocks are inclusive date ranges."""

    index: int
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    validation_start: pd.Timestamp
    validation_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp
    embargo_days: int
    mode: str

    def to_dict(self) -> dict:
        fmt = lambda d: pd.Timestamp(d).strftime("%Y-%m-%d")  # noqa: E731
        return {
            "fold": self.index, "mode": self.mode, "embargoDays": self.embargo_days,
            "trainStart": fmt(self.train_start), "trainEnd": fmt(self.train_end),
            "validationStart": fmt(self.validation_start), "validationEnd": fmt(self.validation_end),
            "testStart": fmt(self.test_start), "testEnd": fmt(self.test_end),
        }

    def slice(self, frame: pd.DataFrame, block: str, date_column: str = "date") -> pd.DataFrame:
        starts = {"train": self.train_start, "validation": self.validation_start,
                  "test": self.test_start}
        ends = {"train": self.train_end, "validation": self.validation_end,
                "test": self.test_end}
        if block not in starts:
            raise KeyError(f"unknown block {block!r}")
        dates = pd.to_datetime(frame[date_column])
        return frame.loc[(dates >= starts[block]) & (dates <= ends[block])]


def assert_ordered(fold: Fold, horizon_days: int) -> None:
    """Fail loudly on any fold whose blocks could leak into each other."""
    if not (fold.train_start <= fold.train_end < fold.validation_start
            <= fold.validation_end < fold.test_start <= fold.test_end):
        raise ValueError(f"fold {fold.index} blocks are not strictly time-ordered")
    required = pd.Timedelta(days=int(horizon_days) + int(fold.embargo_days))
    if fold.validation_start - fold.train_end < required:
        raise ValueError(f"fold {fold.index}: train->validation gap below horizon+embargo")
    if fold.test_start - fold.validation_end < required:
        raise ValueError(f"fold {fold.index}: validation->test gap below horizon+embargo")


def make_folds(dates, *, train_years: float = 3.0, validation_years: float = 1.0,
               test_years: float = 1.0, horizon_days: int = 126,
               embargo_days: int = 21, mode: str = "expanding",
               max_folds: int | None = None) -> list[Fold]:
    """Chained train -> validation -> test blocks marching forward in time.

    ``expanding`` keeps every earlier year in train (more data, assumes the
    distant past still informs today). ``rolling`` drops the oldest year each
    step (less data, adapts faster to a changed market). Both are offered
    because which is right is an empirical question the fold-stability
    diagnostics are meant to answer, not a preference to hardcode.
    """
    stamps = pd.DatetimeIndex(sorted(pd.DatetimeIndex(dates).normalize().unique()))
    if not len(stamps):
        return []
    gap = pd.Timedelta(days=int(horizon_days) + int(embargo_days))
    train_span = pd.Timedelta(days=int(round(train_years * 365.25)))
    val_span = pd.Timedelta(days=int(round(validation_years * 365.25)))
    test_span = pd.Timedelta(days=int(round(test_years * 365.25)))

    origin = stamps[0]
    final = stamps[-1]
    folds: list[Fold] = []
    index = 0
    train_end = origin + train_span
    while True:
        validation_start = train_end + gap
        validation_end = validation_start + val_span
        test_start = validation_end + gap
        test_end = min(test_start + test_span, final)
        if test_start > final or test_end <= test_start:
            break
        train_start = origin if mode == "expanding" else max(origin, train_end - train_span)
        fold = Fold(index=index, train_start=train_start, train_end=train_end,
                    validation_start=validation_start, validation_end=validation_end,
                    test_start=test_start, test_end=test_end,
                    embargo_days=int(embargo_days), mode=mode)
        assert_ordered(fold, horizon_days)
        # A fold with an empty block teaches nothing and would silently skew the
        # aggregate; drop it rather than average over a hole.
        if all(len(stamps[(stamps >= s) & (stamps <= e)]) > 0 for s, e in (
                (fold.train_start, fold.train_end),
                (fold.validation_start, fold.validation_end),
                (fold.test_start, fold.test_end))):
            folds.append(fold)
            index += 1
            if max_folds and len(folds) >= max_folds:
                break
        train_end = train_end + test_span
        if train_end >= final:
            break
    return folds


def nested_folds(dates, **kwargs) -> list[Fold]:
    """Alias making the nesting explicit at call sites.

    Every fold already carries its own inner validation block, so model
    selection happens strictly inside ``train``+``validation`` and the outer
    ``test`` block is only ever scored. That is the nested procedure; the name
    just says so out loud.
    """
    return make_folds(dates, **kwargs)


# --------------------------------------------------------------------------- #
# Final untouched holdout
# --------------------------------------------------------------------------- #
@dataclass
class HoldoutGuard:
    """The last slice of history, sealed until the model is frozen.

    Walk-forward folds still let a researcher iterate: try a feature, look at
    the aggregated test score, try another. Do that fifty times and the
    aggregate test score is a validation score wearing a disguise. The holdout
    is the antidote — it is scored exactly once, after everything else is
    decided, and its number is the one worth believing.
    """

    start: pd.Timestamp
    sealed: bool = True
    accesses: list[str] = field(default_factory=list)

    @classmethod
    def from_config(cls, cfg: dict | None) -> "HoldoutGuard":
        cfg = cfg or {}
        return cls(start=pd.Timestamp(cfg.get("finalHoldoutStart", "2023-01-01")).normalize())

    def development(self, frame: pd.DataFrame, date_column: str = "date") -> pd.DataFrame:
        """Everything before the holdout — the only data development may see."""
        dates = pd.to_datetime(frame[date_column])
        return frame.loc[dates < self.start]

    def holdout(self, frame: pd.DataFrame, date_column: str = "date",
                reason: str = "final_evaluation") -> pd.DataFrame:
        if self.sealed:
            raise HoldoutViolation(
                f"final holdout from {self.start.date()} is sealed; "
                f"unseal() only after the model is frozen (requested for {reason!r})")
        self.accesses.append(reason)
        dates = pd.to_datetime(frame[date_column])
        return frame.loc[dates >= self.start]

    def unseal(self, reason: str = "model_frozen") -> "HoldoutGuard":
        self.sealed = False
        self.accesses.append(f"unsealed:{reason}")
        return self

    def to_dict(self) -> dict:
        return {
            "finalHoldoutStart": self.start.strftime("%Y-%m-%d"),
            "sealedDuringDevelopment": True,
            "unsealed": not self.sealed,
            "accessLog": list(self.accesses),
            "policyKo": "최종 홀드아웃은 모델 확정 전까지 파라미터·임계값 튜닝에 사용하지 않습니다.",
        }


def split_summary(folds: list[Fold], guard: HoldoutGuard | None = None) -> dict:
    return {
        "method": "NESTED_WALK_FORWARD",
        "randomSplitUsed": False,
        "folds": [f.to_dict() for f in folds],
        "foldCount": len(folds),
        "mode": folds[0].mode if folds else None,
        "embargoDays": folds[0].embargo_days if folds else None,
        "finalHoldout": guard.to_dict() if guard else None,
    }
