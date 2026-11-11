"""Explainable arithmetic over user-owned measurements."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from liferesets.database import get_db
from liferesets.models import Goal, GoalMetric
from liferesets.security import Authenticated

router = APIRouter(prefix="/api/v1/insights", tags=["domain intelligence"])


def _metric_progress(metric) -> dict[str, object]:
    current = metric.current_value
    baseline = metric.baseline_value
    target = metric.target_value
    percentage: Decimal | None = None
    if current is not None and baseline is not None and target != baseline:
        percentage = (current - baseline) * Decimal("100") / (target - baseline)
    return {
        "name": metric.name,
        "unit": metric.unit,
        "baseline_value": str(baseline) if baseline is not None else None,
        "current_value": str(current) if current is not None else None,
        "target_value": str(target),
        "confidence": metric.confidence,
        "history_count": len(metric.measurements),
        "progress_percent": str(percentage.quantize(Decimal("0.01")))
        if percentage is not None
        else None,
        "source": metric.source,
        "interpretation": (
            "Arithmetic comparison only; no health, financial, "
            "or personal-worth judgment."
        ),
    }


@router.get("/progress")
def progress_insights(
    auth: Authenticated, db: Session = Depends(get_db)
) -> dict[str, object]:
    """Return raw metric comparisons while preserving units and provenance."""
    goals = db.scalars(
        select(Goal)
        .where(Goal.user_id == auth.user.id)
        .options(selectinload(Goal.metrics).selectinload(GoalMetric.measurements))
        .order_by(Goal.created_at, Goal.id)
    ).all()
    return {
        "goals": [
            {
                "goal_id": str(goal.id),
                "domain": goal.domain,
                "title": goal.title,
                "metrics": [_metric_progress(metric) for metric in goal.metrics],
            }
            for goal in goals
        ],
        "method": "(current - baseline) / (target - baseline) * 100",
        "interpretation": (
            "Progress values are unbounded arithmetic, not a prediction "
            "or recommendation."
        ),
    }
