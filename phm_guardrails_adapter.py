"""phm_guardrails_adapter.py — PHM deterministic guardrail glue for DeepSeek agent loops.

Public glue only. The production rule engine (ActionFlowVerifier R1-R7) is
CLOSED SOURCE (see CLOSED_SOURCE_LIST.md). Any verifier object exposing

    verify(plan, [action]) -> {"verdict": "PASS"|"INTERCEPT", "rule": str|None, ...}

can be plugged in (duck-typed, dependency injection). A trivial DemoVerifier
is bundled below so the demo runs out of the box; it is NOT the production
rule engine.

Integration surface (verified against openai-agents SDK 0.23.1 source, 2026-10-07):
    from agents import Agent, function_tool
    from phm_guardrails_adapter import phm_tool_input_guardrail, DemoVerifier

    guardrail = phm_tool_input_guardrail(verifier=DemoVerifier(...), declared_plan=[...])
    tool = function_tool(fn, tool_input_guardrails=[guardrail])
    agent = Agent(name="x", model="deepseek-chat", tools=[tool])
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any, List, Mapping, Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

try:
    from agents.tool_guardrails import (  # type: ignore
        ToolGuardrailFunctionOutput,
        tool_input_guardrail,
    )
    SDK_AVAILABLE = True
except ImportError:  # closed-loop shape testing without the SDK installed
    SDK_AVAILABLE = False

    class ToolGuardrailFunctionOutput:  # minimal stand-in with identical factory surface
        def __init__(self, output_info=None, behavior=None):
            self.output_info = output_info
            self.behavior = behavior or {"type": "allow"}

        @classmethod
        def allow(cls, output_info=None):
            return cls(output_info=output_info, behavior={"type": "allow"})

        @classmethod
        def reject_content(cls, message, output_info=None):
            return cls(output_info=output_info, behavior={"type": "reject_content", "message": message})

        @classmethod
        def raise_exception(cls, output_info=None):
            return cls(output_info=output_info, behavior={"type": "raise_exception"})

    def tool_input_guardrail(func=None, *, name=None):  # decorator stand-in
        func._guardrail_name = name or func.__name__
        return func


DEFAULT_PLAN = [
    ("search", "*"), ("calculator", "*"), ("summarize", "*"),
]

_NET_KEYS = ("url", "endpoint", "host", "api_url", "base_url")


class DemoVerifier:
    """Trivial standalone verifier for the demo ONLY (not the production engine).

    Rules implemented here (demo grade):
      - PLAN_BREACH : action not in the declared plan
      - EGRESS      : net egress to a domain outside the whitelist
    The production engine (ActionFlowVerifier R1-R7, 100k-scenario 0 FN / 0 FP)
    is closed source; see CLOSED_SOURCE_LIST.md.
    """

    def __init__(self, whitelist_domains: tuple = ()):
        self.whitelist_domains = tuple(whitelist_domains)

    def verify(self, plan: List[Any], actions: List[Any]) -> dict:
        a = actions[0]
        if not a.planned and (a.op, a.resource) not in [(p.op, p.resource) for p in plan]:
            return {"verdict": "INTERCEPT", "rule": "DEMO_PLAN_BREACH",
                    "evidence": f"op={a.op} resource={a.resource} not in declared plan"}
        if a.resource.startswith("net://"):
            host = a.resource[len("net://"):].lower()
            if self.whitelist_domains and host not in [d.lower() for d in self.whitelist_domains]:
                return {"verdict": "INTERCEPT", "rule": "DEMO_EGRESS",
                        "evidence": f"domain {host} outside whitelist"}
        return {"verdict": "PASS", "rule": None, "evidence": ""}


class Action:
    """Minimal action shape (mirrors the closed engine's public action schema)."""

    def __init__(self, op: str, resource: str, payload_fp: str = "", planned: bool = False):
        self.op = op
        self.resource = resource
        self.payload_fp = payload_fp
        self.planned = planned


def _pending_action_from(tool_name: str, tool_arguments: str) -> Any:
    """Build a verifier Action from the SDK's tool context fields."""
    resource = tool_name
    args: Mapping[str, Any] = {}
    try:
        parsed = json.loads(tool_arguments) if tool_arguments else {}
        if isinstance(parsed, dict):
            args = parsed
    except (json.JSONDecodeError, TypeError):
        args = {}

    for key in _NET_KEYS:
        v = str(args.get(key, ""))
        if v:
            host = v.split("//", 1)[-1].split("/", 1)[0].split(":", 1)[0]
            resource = f"net://{host}"
            break
    else:
        for key in ("path", "file", "target", "resource"):
            v = str(args.get(key, ""))
            if v:
                resource = v
                break

    fp = str(args.get("content_hash", args.get("payload_fp", "")))[:64]
    # Action class follows the FACTUAL SHAPE of arguments, not the tool's name:
    # egress-ish arg present -> op='fetch' so EGRESS checks apply
    op = "fetch" if resource.startswith("net://") else tool_name
    return Action(op=op, resource=resource, payload_fp=fp, planned=False)


def phm_tool_input_guardrail(
    verifier: Any,
    declared_plan: Optional[List[Any]] = None,
    on_veto: str = "reject_content",  # "reject_content" | "raise_exception"
    name: str = "phm_deterministic_verifier",
):
    """Create a deterministic tool-input guardrail from a PHM verifier object.

    verifier      : object with .verify(plan, [action]) -> dict (rule internals injectable)
    declared_plan : list of (op, resource) tuples or Action objects
    on_veto       : "reject_content" keeps the run alive and feeds the veto reason
                    to the model; "raise_exception" halts hard
                    (verified: serial execution closes the veto race window,
                     concurrent execution leaves all calls racing — openai-agents
                     0.23.1, n=30 each, 2026-10-07)
    """
    plan = declared_plan or DEFAULT_PLAN
    plan_actions = [a if isinstance(a, Action) else Action(op=a[0], resource=a[1], planned=True)
                    for a in plan]

    def _guard(data: Any) -> ToolGuardrailFunctionOutput:
        tool_name = getattr(data.context, "tool_name", "") or "unknown_tool"
        tool_args = getattr(data.context, "tool_arguments", "") or "{}"
        pending = _pending_action_from(tool_name, tool_args)
        result = verifier.verify(plan_actions, [pending])

        if result.get("verdict") == "PASS":
            return ToolGuardrailFunctionOutput.allow(output_info={"phm": result})

        info = {"phm": result, "tool": tool_name}
        message = f"[PHM veto] rule {result.get('rule')}: {result.get('evidence')}"
        if on_veto == "raise_exception":
            return ToolGuardrailFunctionOutput.raise_exception(output_info=info)
        return ToolGuardrailFunctionOutput.reject_content(message, output_info=info)

    _guard.__name__ = name
    if SDK_AVAILABLE:
        return tool_input_guardrail(_guard, name=name)
    return tool_input_guardrail(_guard)
