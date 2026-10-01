from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

import yaml
import httpx2
from typesafe_sdk import Choice, Noul, RetryPolicy, Score, TypeSafeClient

from jevpad.config import Settings, require_live_key
from jevpad.evidence import append_record, code_revision, utc_now
from jevpad.modes import fixture_answers


FAULTS = {"timeout", "ratelimit", "auth", "malformed", "server"}


def load_yaml(source: Path) -> dict[str, Any]:
    return yaml.safe_load(source.read_text(encoding="utf-8"))


def build_questions(definitions: dict[str, Any]) -> dict[str, Any]:
    built: dict[str, Any] = {}
    for question_id, spec in definitions.items():
        kind = spec["type"]
        if kind == "choice":
            built[question_id] = Choice(instructions=spec["instructions"], criteria=spec["options"])
        elif kind == "noul":
            criteria = spec.get("criteria")
            if isinstance(criteria, str):
                criteria = {"true": criteria}
            built[question_id] = Noul(instructions=spec["instructions"], criteria=criteria)
        elif kind == "score":
            built[question_id] = Score(instructions=spec["instructions"], criteria=spec["levels"])
        else:
            raise ValueError(f"Unknown question type {kind!r} for {question_id}")
    return built


def public_questions(questions: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, question in questions.items():
        result[key] = question.model_dump(mode="json", exclude_none=True)
    return result


def normalize_answer(answer: Any) -> dict[str, Any]:
    if isinstance(answer, dict):
        return answer
    return answer.model_dump(mode="json", exclude_none=True)


def _gateway_metadata(response: Any) -> tuple[str, dict[str, Any]]:
    try:
        body = response.raw_http_response.json()
    except Exception:
        return "not exposed by SDK", {"cost": "not exposed by SDK", "marketCost": "not exposed by SDK"}
    metadata = body.get("provider_metadata") or body.get("providerMetadata") or {}
    gateway = metadata.get("gateway") or {}
    routing = gateway.get("routing") or {}
    provider = routing.get("finalProvider", "not exposed by SDK")
    costs = {
        "cost": gateway.get("cost", body.get("cost", "not exposed by SDK")),
        "marketCost": gateway.get("marketCost", body.get("marketCost", "not exposed by SDK")),
    }
    return provider, costs


def _raw_body(response: Any) -> dict[str, Any]:
    try:
        body = response.raw_http_response.json()
        return body if isinstance(body, dict) else {"body": body}
    except Exception:
        return {"unavailable": "raw response body not exposed by SDK"}


class AttemptTracker:
    """Count actual HTTP sends, including sends that never receive a response."""

    def __init__(self) -> None:
        self.statuses: list[int | str] = []

    def on_request(self, request: httpx2.Request) -> None:
        self.statuses.append("no response (transport error)")

    def on_response(self, response: httpx2.Response) -> None:
        if self.statuses:
            self.statuses[-1] = response.status_code


def _fault_transport(kind: str, counter: dict[str, int]) -> httpx2.MockTransport:
    def handler(request: httpx2.Request) -> httpx2.Response:
        counter["attempts"] += 1
        if kind == "timeout":
            raise httpx2.ReadTimeout("controlled injected timeout", request=request)
        status = {"ratelimit": 429, "auth": 401, "server": 503}.get(kind, 200)
        if kind == "malformed":
            return httpx2.Response(200, text="{not-json", request=request)
        return httpx2.Response(status, json={"error": {"message": f"controlled injected HTTP {status}"}}, request=request)
    return httpx2.MockTransport(handler)


def judge(
    *, settings: Settings, recipe: str, example_id: str, origin: str,
    state: Any, questions: dict[str, Any], mode: str,
    profile: str | None = None, injected_fault: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    run_id = uuid.uuid4().hex[:12]
    timestamp = utc_now()
    started = time.perf_counter()
    answers: dict[str, Any] = {}
    answered_model: str | None = None
    provider = "no answer"
    usage: dict[str, Any] = {}
    costs: dict[str, Any] = {}
    attempts = 0
    attempt_statuses: list[int | str] = []
    error_type: str | None = None
    error_message: str | None = None
    tracker: AttemptTracker | None = None
    fault = injected_fault or settings.fault
    if fault and fault not in FAULTS:
        raise ValueError(f"Unknown fault {fault!r}; choose one of: {', '.join(sorted(FAULTS))}")
    try:
        if mode == "fixture":
            answers = fixture_answers(recipe, example_id, profile)
            answered_model = "hand-written-fixture"
            provider = "none"
        elif mode == "live":
            if not fault:
                require_live_key(settings)
            client_kwargs: dict[str, Any] = {}
            tracker = AttemptTracker()
            http_kwargs: dict[str, Any] = {
                "event_hooks": {"request": [tracker.on_request], "response": [tracker.on_response]},
                "timeout": 30.0,
            }
            if fault:
                client_kwargs["base_url"] = "https://injected-fault.invalid"
                counter = {"attempts": 0}
                http_kwargs["transport"] = _fault_transport(fault, counter)
            elif settings.typesafe_base_url:
                client_kwargs["base_url"] = settings.typesafe_base_url
            client_kwargs["http_client"] = httpx2.Client(**http_kwargs)
            retry = RetryPolicy(
                max_retries=settings.jev_max_retries,
                timeout=settings.jev_retry_budget_s,
            )
            with TypeSafeClient(api_key=settings._typesafe_api_key or "injected-fault-placeholder", **client_kwargs) as client:
                extra_body = None
                if settings.pin_provider:
                    extra_body = {"providerOptions": {"gateway": {"only": [settings.pin_provider]}}}
                response = client.system_one(
                    state=state, questions=questions, model=settings.typesafe_model,
                    extra_body=extra_body, timeout=30.0, retry=retry,
                )
            attempts = len(tracker.statuses)
            attempt_statuses = tracker.statuses
            answers = {key: normalize_answer(value) for key, value in response.answers.items()}
            answered_model = response.model
            usage = response.usage.model_dump(mode="json", exclude_none=True)
            provider, costs = _gateway_metadata(response)
            raw_response = _raw_body(response)
        else:
            raise ValueError(f"Unsupported execution mode: {mode}")
    except Exception as exc:
        error_type = type(exc).__name__
        error_message = str(exc)
    if tracker is not None:
        attempts = len(tracker.statuses)
        attempt_statuses = tracker.statuses
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    record = {
        "run_id": run_id,
        "recipe": recipe,
        "example_id": example_id,
        "origin": origin,
        "mode": mode,
        "requested_model": settings.typesafe_model if mode == "live" else "none",
        "answered_model": answered_model,
        "final_provider": provider,
        "base_url_host": settings.base_host if mode == "live" else "none",
        "code_revision": code_revision(),
        "timestamp_utc": timestamp,
        "elapsed_ms": elapsed_ms,
        "usage_tokens": usage,
        "cost_fields": costs,
        "retries": {
            "policy": {
                "max_retries": settings.jev_max_retries,
                "total_budget_s": settings.jev_retry_budget_s,
                "retryable": "HTTP 408/429/5xx, connection and timeout errors",
            },
            "attempt_count": attempts,
            "attempt_statuses": attempt_statuses,
        },
        "questions": public_questions(questions),
        "answers": answers,
        "error_type": error_type,
        "error_message": error_message,
        "injected_fault": fault,
        "state": state,
        "raw_response": raw_response if mode == "live" and not error_type else None,
    }
    append_record(record)
    return answers, record
