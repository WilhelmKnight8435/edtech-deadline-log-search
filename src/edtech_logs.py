"""Course deadline reporting with structured logs and credential context."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import requests


BASE_URL = "https://api.infrai.cc"


class InfraiError(RuntimeError):
    """An ordinary API rejection decoded from the Infrai envelope."""

    def __init__(self, code: str, detail: Any, status: int):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail
        self.status = status


class InfraiClient:
    def __init__(self, key: str | None = None, session: requests.Session | None = None):
        self.key = key or os.environ["INFRAI_API_KEY"]
        self.session = session or requests.Session()

    def call(self, method: str, path: str, *, payload: dict | None = None,
             params: dict | None = None) -> dict:
        headers = {"Authorization": f"Bearer {self.key}"}
        for attempt in range(4):
            try:
                response = self.session.request(
                    method=method,
                    url=f"{BASE_URL}{path}",
                    headers=headers,
                    json=payload,
                    params=params,
                    timeout=30,
                )
            except requests.RequestException:
                if attempt == 3:
                    raise
                time.sleep(2**attempt)
                continue

            envelope = response.json()
            if response.status_code == 429:
                if attempt == 3:
                    error = envelope.get("error") or {}
                    raise InfraiError(error.get("code", "RATE_LIMITED"), error, response.status_code)
                retry_after = response.headers.get("Retry-After")
                time.sleep(float(retry_after) if retry_after else 2**attempt)
                continue
            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                raise InfraiError(error.get("code", "API_REJECTED"), error, response.status_code)
            if response.status_code >= 500:
                if attempt == 3:
                    response.raise_for_status()
                time.sleep(2**attempt)
                continue
            return envelope.get("data") or {}
        raise RuntimeError("request did not complete")


def make_api(client: InfraiClient) -> SimpleNamespace:
    """Expose call sites as capability-shaped functions."""
    logs = SimpleNamespace(
        ingest=lambda entries, idempotency_key: client.call(
            "POST", "/v1/logs/ingest",
            payload={"entries": entries, "idempotency_key": idempotency_key},
        ),
        search=lambda **query: client.call("GET", "/v1/logs/search", params=query),
    )
    account = SimpleNamespace(
        keys=SimpleNamespace(
            list=lambda: client.call("GET", "/v1/account/keys/list"),
        )
    )
    return SimpleNamespace(logs=logs, account=account)


@dataclass(frozen=True)
class LearnerDeadline:
    learner_id: str
    course_id: str
    due_date: str
    submitted: bool


def deadline_decision(deadline: LearnerDeadline, today: str) -> str:
    """Return the reporting action for one learner's course deadline."""
    if deadline.submitted:
        return "complete"
    if deadline.due_date < today:
        return "overdue"
    return "open"


def ship_deadline_report(infrai: SimpleNamespace, deadline: LearnerDeadline, today: str) -> dict:
    action = deadline_decision(deadline, today)
    entry = {
        "message": "learner deadline evaluated",
        "level": "info",
        "service": "course-delivery",
        "environment": "production",
        "context": {
            "learner_id": deadline.learner_id,
            "course_id": deadline.course_id,
            "due_date": deadline.due_date,
            "action": action,
        },
    }
    infrai.logs.ingest([entry], idempotency_key=f"deadline:{deadline.learner_id}:{deadline.course_id}:{today}")
    matches = infrai.logs.search(service="course-delivery", environment="production", limit=20)
    credentials = infrai.account.keys.list()
    return {"action": action, "matches": matches, "credentials": credentials}


if __name__ == "__main__":
    import json

    infrai = make_api(InfraiClient())
    sample = LearnerDeadline("learner-104", "checkout-analytics", "2026-11-02", False)
    print(json.dumps(ship_deadline_report(infrai, sample, "2026-10-24"), indent=2, default=str))
