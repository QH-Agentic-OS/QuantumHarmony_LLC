#!/usr/bin/env python3
"""
Runtime profile layer binding (public plugin build).

Implements the merge between the live runtime (provenance service + plugin hooks
+ Mission Control) and the declarative runtime_profile manifest.

Core mechanic — bind, don't copy:

    L0 declaration ──hash──┐
    L1 version ────────────┤ declaration_ref
    L2 session ────────────┤ version_ref
    L3 route ──────────────┤ session_ref
    L4 action ─────────────┘ route_ref  + prev_action_hash

An action entry stays small (four refs, not four copied blocks) while the full
manifest remains reconstructible. Mutating any upper layer invalidates every
hash beneath it, which is the property the flat draft could not provide.

Two enforcement rules that the flat schema silently allowed to be broken:

  1. SOURCE CLASS. Every field is declared / measured / derived / referenced.
     A `declared` value is a claim the runtime cannot verify. Scoring a claim as
     evidence is the failure mode this whole toolkit exists to prevent, so the
     validator reports declared-coverage and measured-coverage separately.

  2. DERIVED WRITER. Nothing in L5 may be authored by the acting agent.
     bind_derived() raises if computed_by == the acting agent_id.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


# ── canonical hashing ────────────────────────────────────────────────────────


def canonical_hash(payload: dict) -> str:
    """Stable sha256 over sorted, separator-normalized JSON."""
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── source classification ────────────────────────────────────────────────────

DECLARED = "declared"  # operator claim; runtime cannot verify
MEASURED = "measured"  # runtime emitted it at the moment it happened
DERIVED = "derived"  # computed from measured + declared
REFERENCED = "referenced"  # hash pointer to another layer

# Which fields the CURRENT runtime can actually emit, and from where.
# Anything mapped to None has no emitter: it will be permanently null unless
# someone builds the collector. A manifest that is mostly null trains people
# to stop reading it, so this map is the honest scope of the merge.
EMITTERS: dict[str, str | None] = {
    # Public plugin build: only the emitters this plugin actually ships.
    # L0 declaration — human-authored; the hooks declare only the agent id
    "declaration.identity.agent_id": "plugin hooks (claude-code)",
    "declaration.identity.model_owner": None,
    "declaration.identity.accountable_operator": None,
    "declaration.legal.jurisdiction": None,
    "declaration.legal.applicable_frameworks": None,
    "declaration.legal.data_residency": None,
    "declaration.human_authority.emergency_stop_owner": None,
    "declaration.evidence_roots.provenance_location": "provenance_service (PROV_DB)",
    "declaration.evidence_roots.audit_location": None,
    # L1 version
    "version.build_inputs.instruction_hash": "plugin hooks: sha256 of the project's CLAUDE.md",
    "version.build_inputs.artifact_hash": None,
    "version.build_inputs.source_branch": None,
    "version.surface.mcp_tools": None,
    "version.surface.installed_tools": None,
    "version.surface.tool_interface": None,
    "version.assurance.invariant_checks": None,
    "version.assurance.risk_tier": None,
    "version.assurance.reviewer": None,
    # L2 session — from the hook payload
    "session.session_id": "hook payload session_id",
    "session.scope.workspace": "hook payload cwd",
    "session.scope.isolation_mode": None,
    "session.scope.human_owner": None,
    "session.effective_policy.network_policy": "dashboard: service origin",
    "session.effective_policy.tool_permissions": None,
    "session.effective_policy.approval_gates": None,
    "session.effective_policy.stop_conditions": None,
    "session.effective_policy.runner_type": None,
    "session.execution_location.placement": "plugin hooks (local)",
    "session.execution_location.connectivity": None,
    "session.execution_location.offline_authority": None,
    # L3 route — model id only; nothing in the public build polls route health
    "route.model.id": "hook payload model",
    "route.model.context_window": None,
    "route.inference.serving_provider": None,
    "route.inference.compute_operator": None,
    "route.inference.accelerator": None,
    "route.inference.physical_region": None,
    "route.health.capacity_state": None,
    "route.health.queue_depth": None,
    "route.health.error_rate": None,
    "route.health.last_verified": None,
    "route.economics.observed_latency": "provenance_service latency_ms",
    "route.economics.observed_cost": None,
    "route.fallback_route": None,
    # L4 action — emitted by the service (/log, /ingest/trajectory)
    "action.prov_id": "provenance_service /log and /ingest/trajectory",
    "action.parent_prov_id": "provenance_service /log and /ingest/trajectory",
    "action.body_sha256": "provenance_service /log and /ingest/trajectory",
    "action.prev_action_hash": "NEW — this module",
    "action.canonical_action.operation": "/log action_type or harness step type",
    "action.canonical_action.target": "/log target or harness tool target",
    "action.canonical_action.reversible": None,
    "action.canonical_action.systems_touched": None,
    "action.semantic_fingerprint": "NEW — this module",
    "action.atp_tags": "/log tags",
    "action.approval_receipt": None,
    "action.outcome": "/log status or harness step status",
    "action.evidence_location": None,
    # L5 derived — requires an assessor identity distinct from the acting agent
    "derived.observation.drift_classification": None,
    "derived.capability_drift.capabilities_added": "diff of two version records",
    "derived.candidate_action.promotion_status": None,
}

# Collisions in the flat draft and the layer that now owns each key.
COLLISION_MAP = {
    "model_owner": ("declaration.identity", ["top-level", "model"]),
    "accountable_operator": (
        "declaration.identity",
        ["top-level", "infrastructure_impact"],
    ),
    "jurisdiction": ("declaration.legal", ["top-level", "governance"]),
    "instruction_hash": ("version.build_inputs", ["top-level", "review_execution"]),
    "network_policy": ("session.effective_policy", ["top-level", "review_execution"]),
    "execution_location": ("session", ["top-level", "infrastructure_impact"]),
    "compute_operator": ("route.inference", ["top-level", "model"]),
    "serving_provider": (
        "route.inference",
        [
            "top-level:inference_provider",
            "model:api_provider",
            "inference_route:serving_provider",
        ],
    ),
    "physical_region": (
        "route.inference",
        ["model", "inference_route", "infrastructure_impact:compute_region"],
    ),
    "capacity_state": (
        "route.health",
        ["route_health", "inference_route", "artemis_execution"],
    ),
    "fallback_route": ("route", ["model", "route_health", "inference_route:fallback"]),
    "model": (
        "route.model",
        ["top-level block", "review_execution", "inference_route"],
    ),
    "evidence_location": (
        "action / derived.*",
        [
            "artemis_execution",
            "capability_drift",
            "governance:audit_location",
            "review_execution:evidence",
        ],
    ),
    "environment": ("derived.*", ["observation"]),
    "capability_drift": (
        "derived",
        ["peer field — is actually a diff of two version records, not a record itself"],
    ),
}


# ── layer records ────────────────────────────────────────────────────────────


@dataclass
class Layer:
    name: str
    body: dict[str, Any]
    parent_ref: str | None = None
    hash: str = field(init=False)

    def __post_init__(self):
        payload = {"layer": self.name, "body": self.body, "parent_ref": self.parent_ref}
        self.hash = canonical_hash(payload)

    def ref(self) -> dict[str, str]:
        return {f"{self.name}_ref": self.hash}


class ManifestBinder:
    """Builds one session-scoped hash chain and emits compact action records.

    The provenance service persists this identity in ``manifest_bindings``.
    This class remains the deterministic in-process builder; callers must carry
    ``manifest_binding_id`` across requests rather than infer a global latest
    layer.
    """

    LAYER_ORDER = ["declaration", "version", "session", "route"]

    def __init__(
        self, *, manifest_binding_id: str | None = None, session_id: str | None = None
    ):
        self.manifest_binding_id = manifest_binding_id
        self.session_id = session_id
        self.layers: dict[str, Layer] = {}
        self._prev_action_hash: str | None = None

    def bind(self, layer_name: str, body: dict) -> Layer:
        if layer_name not in self.LAYER_ORDER:
            raise ValueError(f"unknown layer {layer_name!r}")
        if (
            layer_name == "session"
            and self.session_id
            and body.get("session_id") != self.session_id
        ):
            raise ValueError(
                f"session layer id {body.get('session_id')!r} does not match "
                f"binder session_id {self.session_id!r}"
            )
        idx = self.LAYER_ORDER.index(layer_name)
        parent_ref = None
        if idx > 0:
            parent_name = self.LAYER_ORDER[idx - 1]
            parent = self.layers.get(parent_name)
            if parent is None:
                raise ValueError(
                    f"cannot bind {layer_name!r}: parent layer {parent_name!r} not bound. "
                    "Layers bind top-down; an unbound parent means the chain has no root."
                )
            parent_ref = parent.hash
        layer = Layer(
            name=layer_name, body={**body, "bound_at": now()}, parent_ref=parent_ref
        )
        self.layers[layer_name] = layer
        # Rebinding a layer invalidates everything below it.
        for stale in self.LAYER_ORDER[idx + 1 :]:
            self.layers.pop(stale, None)
        return layer

    def refs(self) -> dict[str, str]:
        out = {}
        for name in self.LAYER_ORDER:
            layer = self.layers.get(name)
            out[f"{name}_ref"] = layer.hash if layer else None
        return out

    def semantic_fingerprint(self, canonical_action: dict) -> str:
        """Hash of INTENT — operation + target + systems, excluding payload and time.
        Two runs of the same operation on the same target share a fingerprint even
        when their payloads and prov_ids differ. That is what makes drift detectable."""
        intent = {
            k: canonical_action.get(k)
            for k in (
                "runtime_family",
                "adapter",
                "executable",
                "operation",
                "target",
                "systems_touched",
            )
        }
        return canonical_hash(intent)

    def action_record(
        self,
        *,
        prov_id: str,
        parent_prov_id: str,
        canonical_action: dict,
        outcome: str = "accepted",
        status: str = "ok",
        atp_tags: list | None = None,
        approval_receipt: str | None = None,
        evidence_location: str | None = None,
    ) -> dict:
        missing = [n for n in self.LAYER_ORDER if n not in self.layers]
        if missing:
            raise ValueError(
                f"cannot emit action: unbound layers {missing}. "
                "An action whose context is unbound is an action nobody can attribute."
            )
        record = {
            "prov_id": prov_id,
            "parent_prov_id": parent_prov_id,
            "manifest_binding_id": self.manifest_binding_id,
            "ts": now(),
            "refs": self.refs(),
            "canonical_action": canonical_action,
            "semantic_fingerprint": self.semantic_fingerprint(canonical_action),
            "atp_tags": atp_tags or [],
            "approval_receipt": approval_receipt,
            "evidence_location": evidence_location,
            "outcome": outcome,
            "status": status,
            "prev_action_hash": self._prev_action_hash,
        }
        record["body_sha256"] = canonical_hash(record)
        self._prev_action_hash = record["body_sha256"]
        return record

    def bind_derived(
        self, *, computed_by: str, acting_agent_id: str, body: dict
    ) -> dict:
        """L5. Refuses to let the acting agent author its own assessment."""
        if computed_by == acting_agent_id:
            raise PermissionError(
                f"derived layer writer {computed_by!r} is the acting agent. "
                "An agent scoring its own competence or promoting its own candidate "
                "action defeats the validation boundary."
            )
        return {
            "computed_at": now(),
            "computed_by": computed_by,
            "inputs": self.refs(),
            **body,
        }


# ── validation / audit ───────────────────────────────────────────────────────


def verify_chain(action_records: list[dict]) -> dict:
    """Tamper-evidence check: each record's body_sha256 must recompute, and
    prev_action_hash must equal the preceding record's hash."""
    results = {"recomputed_ok": True, "linked_ok": True, "breaks": []}
    prev = None
    for i, rec in enumerate(action_records):
        claimed = rec.get("body_sha256")
        body = {k: v for k, v in rec.items() if k != "body_sha256"}
        if canonical_hash(body) != claimed:
            results["recomputed_ok"] = False
            results["breaks"].append({"index": i, "reason": "body_sha256 mismatch"})
        if rec.get("prev_action_hash") != prev:
            results["linked_ok"] = False
            results["breaks"].append(
                {"index": i, "reason": "prev_action_hash mismatch"}
            )
        prev = claimed
    return results


def emitter_audit() -> dict:
    """What fraction of the manifest can the runtime actually populate today?"""
    by_layer: dict[str, dict[str, list]] = {}
    for path, emitter in EMITTERS.items():
        layer = path.split(".")[0]
        slot = by_layer.setdefault(layer, {"has_emitter": [], "no_emitter": []})
        slot["has_emitter" if emitter else "no_emitter"].append(path)
    summary = {}
    for layer, slot in by_layer.items():
        total = len(slot["has_emitter"]) + len(slot["no_emitter"])
        summary[layer] = {
            "covered": len(slot["has_emitter"]),
            "total": total,
            "pct": round(100 * len(slot["has_emitter"]) / total),
            "gaps": slot["no_emitter"],
        }
    return summary


if __name__ == "__main__":
    print("═" * 74)
    print("RUNTIME PROFILE — LAYER BIND SELF-TEST")
    print("═" * 74)

    b = ManifestBinder(
        manifest_binding_id="binding-self-test",
        session_id="b434ded8-45e5-42e7-9c75-1faaf2c074d4",
    )

    d = b.bind(
        "declaration",
        {
            "identity": {
                "agent_id": "example-agent",
                "model_owner": "example-model-owner",
                "accountable_operator": "example-operator",
            },
            "legal": {"jurisdiction": "US-NY", "data_residency": "US"},
            "evidence_roots": {"provenance_location": "provenance.db"},
        },
    )
    v = b.bind(
        "version",
        {
            "component_id": "atp-mission-control",
            "build_inputs": {
                "instruction_hash": "sha256:a1b2c3",
                "source_branch": "dev",
            },
            "surface": {"mcp_tools": 12},
        },
    )
    s = b.bind(
        "session",
        {
            "session_id": "b434ded8-45e5-42e7-9c75-1faaf2c074d4",
            "scope": {
                "workspace": "/workspace/example",
                "isolation_mode": "bypassPermissions",
            },
            "execution_location": {"placement": "local"},
        },
    )
    r = b.bind(
        "route",
        {
            "model": {"id": "claude-sonnet-5"},
            "inference": {
                "serving_provider": "example-provider",
                "physical_region": "local",
            },
            "health": {"capacity_state": "nominal", "last_verified": now()},
        },
    )

    for layer in (d, v, s, r):
        parent = (layer.parent_ref or "—")[:12]
        print(f"  {layer.name:<12} {layer.hash[:16]}…  parent={parent}")

    print("\n── actions (hash-chained) ──")
    records = []
    for op, target in [
        ("read", "src/config.ts"),
        ("write", "dist/bundle.js"),
        ("tool_call", "atp_response"),
    ]:
        rec = b.action_record(
            prov_id=f"prov-{op}",
            parent_prov_id="e562e81c",
            canonical_action={
                "runtime_family": "python",
                "adapter": "mcp",
                "executable": "example-tool",
                "operation": op,
                "target": target,
                "systems_touched": ["fs"],
                "reversible": op != "write",
            },
            atp_tags=["Review", "Execute"],
        )
        records.append(rec)
        print(
            f"  {op:<10} fp={rec['semantic_fingerprint'][:12]}… "
            f"hash={rec['body_sha256'][:12]}… prev={(rec['prev_action_hash'] or '—')[:12]}"
        )

    print("\n── tamper-evidence ──")
    print(" ", verify_chain(records))
    tampered = json.loads(json.dumps(records))
    tampered[1]["canonical_action"]["target"] = "/etc/passwd"
    bad = verify_chain(tampered)
    print("  after mutating action[1].target:")
    print(
        f"    recomputed_ok={bad['recomputed_ok']} linked_ok={bad['linked_ok']} "
        f"breaks={len(bad['breaks'])}"
    )

    print("\n── derived-writer gate ──")
    try:
        b.bind_derived(
            computed_by="example-agent",
            acting_agent_id="example-agent",
            body={"observation": {"drift_classification": "none"}},
        )
        print("  FAIL: self-authored assessment was allowed")
    except PermissionError as e:
        print(f"  blocked: {str(e)[:88]}…")
    ok = b.bind_derived(
        computed_by="independent-auditor",
        acting_agent_id="example-agent",
        body={"observation": {"drift_classification": "none"}},
    )
    print(
        f"  allowed for independent-auditor, inputs bound to {len([x for x in ok['inputs'].values() if x])} layers"
    )

    print("\n── rebind invalidation ──")
    before = len(b.layers)
    b.bind(
        "session",
        {
            "session_id": "b434ded8-45e5-42e7-9c75-1faaf2c074d4",
            "scope": {"workspace": "/updated-scope"},
        },
    )
    print(
        f"  rebound session -> layers held: {before} → {len(b.layers)} "
        f"(route dropped, must re-resolve)"
    )

    print("\n── emitter coverage (what the runtime can populate TODAY) ──")
    for layer, stat in emitter_audit().items():
        bar = "█" * (stat["pct"] // 10) + "░" * (10 - stat["pct"] // 10)
        print(
            f"  {layer:<12} {bar} {stat['covered']:>2}/{stat['total']:<2} {stat['pct']:>3}%"
        )

    print("\n── collisions resolved ──")
    for key, (owner, dupes) in list(COLLISION_MAP.items())[:6]:
        print(f"  {key:<22} -> {owner:<26} (was in {len(dupes)})")
    print(f"  … {len(COLLISION_MAP)} total")
