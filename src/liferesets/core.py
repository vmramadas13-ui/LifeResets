"""Read-only THE CORE context and response adapter boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from liferesets.models import Evidence, Goal, Habit, Task

MAX_CONTEXT_RECORDS = 24
MAX_CONTEXT_CHARS = 6000
MAX_QUESTION_CHARS = 1000


@dataclass(frozen=True)
class CoreContext:
    """Bounded personal context with provenance attached to every record."""

    records: tuple[dict[str, str], ...]
    truncated: bool


class CoreAdapter(Protocol):
    """Provider interface; implementations receive context and cannot access tools."""

    def respond(self, question: str, context: CoreContext) -> str: ...


class ReadOnlyFallback:
    """Deterministic fallback used while no external model is configured."""

    def respond(self, question: str, context: CoreContext) -> str:
        del question
        if not context.records:
            return "I don't have any saved goals or actions to refer to yet."
        counts: dict[str, int] = {}
        for record in context.records:
            counts[record["kind"]] = counts.get(record["kind"], 0) + 1
        return (
            "Saved context: "
            + ", ".join(f"{count} {kind}" for kind, count in sorted(counts.items()))
            + "."
        )


def build_context(db: Session, user_id: UUID) -> CoreContext:
    """Read a bounded, credential-free snapshot from one account only."""
    records: list[dict[str, str]] = []
    queries = (
        ("goal", select(Goal).where(Goal.user_id == user_id).order_by(Goal.created_at)),
        ("task", select(Task).where(Task.user_id == user_id).order_by(Task.created_at)),
        (
            "habit",
            select(Habit).where(Habit.user_id == user_id).order_by(Habit.created_at),
        ),
        (
            "evidence",
            select(Evidence)
            .where(Evidence.user_id == user_id)
            .order_by(Evidence.captured_at),
        ),
    )
    for kind, query in queries:
        remaining = MAX_CONTEXT_RECORDS - len(records)
        if remaining <= 0:
            break
        for item in db.scalars(query.limit(remaining + 1)).all():
            if len(records) >= MAX_CONTEXT_RECORDS:
                break
            if kind == "goal":
                content = f"{item.title} [{item.domain}; {item.status}]"
                provenance = "user_created_goal"
            elif kind == "task":
                content = f"{item.title} [{item.status}]"
                provenance = "user_created_task"
            elif kind == "habit":
                content = f"{item.action}; cue: {item.cue}; frequency: {item.frequency}"
                provenance = "user_created_habit"
            else:
                content = item.summary
                provenance = f"{item.source}_evidence"
            records.append({"kind": kind, "content": content, "provenance": provenance})

    truncated = len(records) >= MAX_CONTEXT_RECORDS
    bounded: list[dict[str, str]] = []
    total = 0
    for record in records:
        size = len(record["content"])
        if total + size > MAX_CONTEXT_CHARS:
            truncated = True
            break
        bounded.append(record)
        total += size
    return CoreContext(records=tuple(bounded), truncated=truncated)


def answer_read_only(
    db: Session, user_id: UUID, question: str, adapter: CoreAdapter | None = None
) -> dict[str, object]:
    """Answer through an adapter boundary; no writes or tool/action capability."""
    cleaned_question = " ".join(question.split())[:MAX_QUESTION_CHARS]
    context = build_context(db, user_id)
    responder = adapter or ReadOnlyFallback()
    return {
        "answer": responder.respond(cleaned_question, context),
        "mode": "fallback" if adapter is None else "adapter",
        "provenance": [record["provenance"] for record in context.records],
        "context_records": len(context.records),
        "context_truncated": context.truncated,
        "read_only": True,
    }
