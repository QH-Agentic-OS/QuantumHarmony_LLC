#!/usr/bin/env python3
"""
Transport-independent provenance store for ATP Mission Control.

This module owns every rule the provenance system enforces — manifest layer
ordering, session-scoped bindings, action chaining, redaction — and knows
nothing about HTTP or MCP. Two front-ends sit on top of it:

    provenance_core.ProvenanceStore
        ├── provenance_service.py   HTTP  (dashboard, proxy, curl)
        └── provenance_mcp.py       MCP   (agents, stdio / streamable HTTP)

Every public method returns ``(status, payload)`` where ``status`` is an HTTP
status code. The HTTP front-end sends it as the response code; the MCP
front-end turns non-2xx into an actionable error string. Keeping the code in
the return value — rather than raising — means both transports agree on
*which* rule was violated (422 incomplete manifest vs. 409 chain conflict),
which is the distinction callers actually branch on.

Nothing here prints. stdout is the JSON-RPC channel for an MCP stdio server,
so a stray ``print()`` in shared code would corrupt the protocol stream. The
HTTP front-end does its own logging from the returned payload.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from manifest import COLLISION_MAP, canonical_hash
import trajectory as harness_capture

# NOTE: the FastMCP server instance deliberately lives in provenance_mcp.py, not
# here. provenance_service.py and the test suites import this module, so an
# `import mcp` at this level would make the SDK a hard dependency of the HTTP
# path that never uses it.
DEFAULT_DB_PATH = os.environ.get("PROV_DB", "provenance.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_logs (
  prov_id        TEXT PRIMARY KEY,
  parent_prov_id TEXT,
  ts             TEXT NOT NULL,
  agent_id       TEXT,
  actor          TEXT,
  model          TEXT,
  kind           TEXT,
  phase          TEXT,
  action_type    TEXT,
  target         TEXT,
  result         TEXT,
  status         TEXT,
  input_json     TEXT,
  output_json    TEXT,
  error          TEXT,
  latency_ms     INTEGER,
  tags_json      TEXT,
  payload_summary TEXT,
  body_sha256    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_parent ON agent_logs(parent_prov_id);

CREATE TABLE IF NOT EXISTS manifest_layers (
  layer_hash  TEXT PRIMARY KEY,
  layer_name  TEXT NOT NULL,
  parent_ref  TEXT,
  manifest_binding_id TEXT,
  bound_at    TEXT NOT NULL,
  body_json   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_layer_name ON manifest_layers(layer_name);

CREATE TABLE IF NOT EXISTS manifest_bindings (
  manifest_binding_id TEXT PRIMARY KEY,
  session_id          TEXT NOT NULL,
  declaration_ref     TEXT,
  version_ref         TEXT,
  session_ref         TEXT,
  route_ref           TEXT,
  created_at          TEXT NOT NULL,
  updated_at          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS action_refs (
  prov_id         TEXT PRIMARY KEY,
  manifest_binding_id TEXT,
  declaration_ref TEXT,
  version_ref     TEXT,
  session_ref     TEXT,
  route_ref       TEXT,
  prev_action_hash TEXT,
  semantic_fingerprint TEXT,
  sequence_no     INTEGER
);

CREATE TABLE IF NOT EXISTS trajectory_chunks (
  trajectory_id       TEXT NOT NULL,
  chunk_no            INTEGER NOT NULL,
  parent_prov_id      TEXT NOT NULL,
  manifest_binding_id TEXT NOT NULL,
  harness             TEXT NOT NULL,
  start_offset        INTEGER NOT NULL,
  end_offset          INTEGER NOT NULL,
  chunk_sha256        TEXT NOT NULL,
  prior_chain_sha256  TEXT,
  chain_sha256        TEXT NOT NULL,
  first_step_index    INTEGER,
  step_count          INTEGER NOT NULL,
  ingested_at         TEXT NOT NULL,
  PRIMARY KEY (trajectory_id, chunk_no)
);

CREATE TABLE IF NOT EXISTS agent_steps (
  prov_id            TEXT PRIMARY KEY,
  parent_prov_id     TEXT NOT NULL,
  trajectory_id      TEXT NOT NULL,
  chunk_no           INTEGER NOT NULL,
  parent_agent_ref   TEXT,
  step_index         INTEGER NOT NULL,
  source             TEXT,
  step_type          TEXT NOT NULL,
  status             TEXT,
  created_at         TEXT,
  started_at         TEXT,
  completed_at       TEXT,
  duration_ms        INTEGER,
  content_sha256     TEXT,
  content_bytes      INTEGER,
  thinking_present   INTEGER NOT NULL,
  thinking_sha256    TEXT,
  truncated_fields_json TEXT NOT NULL,
  tool_use_id        TEXT,
  capture_method     TEXT NOT NULL,
  source_offset      INTEGER NOT NULL,
  UNIQUE (trajectory_id, step_index)
);
CREATE INDEX IF NOT EXISTS idx_step_parent ON agent_steps(parent_prov_id);

CREATE TABLE IF NOT EXISTS step_tool_calls (
  prov_id      TEXT NOT NULL,
  call_index   INTEGER NOT NULL,
  tool_name    TEXT NOT NULL,
  tool_use_id  TEXT,
  args_json    TEXT NOT NULL,
  args_sha256  TEXT NOT NULL,
  PRIMARY KEY (prov_id, call_index)
);

CREATE TABLE IF NOT EXISTS step_artifacts (
  prov_id        TEXT NOT NULL,
  artifact_index INTEGER NOT NULL,
  kind           TEXT NOT NULL,
  root_sha256    TEXT,
  rel_path       TEXT,
  path_sha256    TEXT,
  lines_total    INTEGER,
  bytes_total    INTEGER,
  lines_from     INTEGER,
  lines_to       INTEGER,
  content_truncated INTEGER NOT NULL,
  PRIMARY KEY (prov_id, artifact_index)
);

CREATE TABLE IF NOT EXISTS capture_policies (
  manifest_binding_id     TEXT PRIMARY KEY,
  require_harness_capture INTEGER NOT NULL,
  set_at                  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS provenance_operations (
  operation TEXT NOT NULL,
  owner_json TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  request_json TEXT NOT NULL,
  receipt_json TEXT NOT NULL,
  PRIMARY KEY (operation, owner_json, idempotency_key)
);
"""

LAYER_ORDER = ["declaration", "version", "session", "route"]
REF_KEYS = [f"{name}_ref" for name in LAYER_ORDER]

REDACT_KEYS = {
    "api_key",
    "apikey",
    "token",
    "secret",
    "password",
    "authorization",
    "credential",
    "access_token",
    "refresh_token",
}
ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._~:/@-]{0,127}$")
HASH_PATTERN = re.compile(r"^[a-f0-9]{64}$")
SECRET_TEXT = re.compile(
    r"(?i)(?:bearer\s+|-----BEGIN [A-Z ]*PRIVATE KEY-----|\b(?:sk-|ghp_|github_pat_|xox[baprs]-|AKIA)[A-Za-z0-9_-]{8,}|"
    r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+|(?:password|secret|api[_-]?key|access[_-]?token)\s*[:=])"
)


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def valid_id(value: Any) -> bool:
    return (
        isinstance(value, str)
        and ID_PATTERN.fullmatch(value) is not None
        and not SECRET_TEXT.search(value)
    )


def valid_owner(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == {"principal_id", "tenant_id", "session_id"}
        and all(valid_id(v) for v in value.values())
    )


def valid_auth_receipt(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == {"request_id", "receipt_id", "record_hash"}
        and valid_id(value["request_id"])
        and valid_id(value["receipt_id"])
        and isinstance(value["record_hash"], str)
        and HASH_PATTERN.fullmatch(value["record_hash"]) is not None
    )


def sanitized(value: Any, depth: int = 0) -> Any:
    """Bound and redact known credential-shaped data before hashing or storage.

    Arbitrary opaque secrets cannot be recognized reliably; v1 producers must
    submit only policy-approved metadata and digests, never raw request bodies.
    """
    if depth > 8:
        raise ValueError("invalid_request")
    if isinstance(value, dict):
        if len(value) > 100 or any(
            not isinstance(k, str) or len(k) > 128 for k in value
        ):
            raise ValueError("invalid_request")
        result = {}
        for key, item in value.items():
            normalized = re.sub(r"[^a-z0-9]", "", key.lower())
            secret = normalized in {
                re.sub(r"[^a-z0-9]", "", k) for k in REDACT_KEYS
            } or any(
                marker in normalized
                for marker in (
                    "privatekey",
                    "clientsecret",
                    "authorization",
                    "password",
                    "credential",
                )
            )
            result[key] = "***REDACTED***" if secret else sanitized(item, depth + 1)
        return result
    if isinstance(value, list):
        if len(value) > 100:
            raise ValueError("invalid_request")
        return [sanitized(item, depth + 1) for item in value]
    if isinstance(value, str):
        if len(value) > 4096 or any(ord(c) < 32 and c not in "\n\t" for c in value):
            raise ValueError("invalid_request")
        return "***REDACTED***" if SECRET_TEXT.search(value) else value
    if value is None or type(value) in (bool, int):
        return value
    if isinstance(value, float) and value == value and abs(value) != float("inf"):
        return value
    raise ValueError("invalid_request")


FINGERPRINT_KEYS = (
    "runtime_family",
    "adapter",
    "executable",
    "operation",
    "target",
    "systems_touched",
)


# ── primitives ───────────────────────────────────────────────────────────────
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def redact(obj: Any) -> Any:
    """Skill requirement: never log secrets."""
    return sanitized(obj)


def body_hash(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def file_hash(path: str) -> str | None:
    try:
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def binding_refs(row) -> dict:
    return {key: row[key] for key in REF_KEYS}


def complete_refs(refs: dict) -> bool:
    return all(refs.get(key) for key in REF_KEYS)


def _scalar(value: Any) -> Any:
    """Column projection of a bounded value: digests collapse to their sha256."""
    if isinstance(value, dict) and "sha256" in value:
        return value["sha256"]
    return value


def semantic_fingerprint_of(canonical_action: dict) -> str:
    """Hash only intent fields — payload and timestamp are deliberately excluded
    so repeated runs of the same operation share a fingerprint. Same
    fingerprint + different outcome is the drift signal."""
    return canonical_hash({key: canonical_action.get(key) for key in FINGERPRINT_KEYS})


def get_collision_map() -> dict:
    """Fields that existed in several places in the original flat draft, and
    which layer now owns each one canonically."""
    return {k: {"owner": v[0], "was_in": v[1]} for k, v in COLLISION_MAP.items()}


def get_runtime_metadata() -> dict:
    """What this runtime can attest about its own build, for the L1 version layer."""
    root = os.path.dirname(os.path.abspath(__file__))
    instruction_path = os.path.join(root, ".agents", "instructions.md")
    return {
        "component_id": "atp-mission-control",
        "build_inputs": {
            # The repo keeps the dashboard beside this file; the plugin keeps
            # it in ../ui.
            "artifact_hash": file_hash(os.path.join(root, "app.js"))
            or file_hash(os.path.join(root, os.pardir, "ui", "app.js")),
            "instruction_hash": file_hash(instruction_path),
            "source_branch": os.environ.get("CIRCLE_BRANCH")
            or os.environ.get("GIT_BRANCH"),
        },
        "surface": {
            "installed_tools": ["python-stdlib", "sqlite"],
            "tool_interface": "provenance-service-http",
        },
    }


# ── store ────────────────────────────────────────────────────────────────────


class ProvenanceStore:
    """SQLite-backed provenance store. One instance per database path.

    The path is held on the instance rather than read from a module global so
    the HTTP handler, the MCP server, and the tests can each point at a
    different database without stepping on each other.
    """

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path

    # ── connection ───────────────────────────────────────────
    def initialize(self) -> None:
        """Initialize a fresh ledger; existing upgrades require the backed-up CLI."""
        from provenance_schema import SchemaError, inspect_schema, upgrade_connection

        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("BEGIN IMMEDIATE")
            report = inspect_schema(conn, SCHEMA, allow_empty=True)
            if not report["ready"] and report["missing"] != ["empty ledger"]:
                raise SchemaError(
                    "existing ledger requires provenance_schema.py upgrade with --backup"
                )
            upgrade_connection(conn, SCHEMA, allow_empty=True)
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def require_ready(self) -> None:
        """Read-only startup gate with an operator-visible selected ledger."""
        from provenance_schema import SchemaError

        try:
            if not Path(self.db_path).is_file():
                raise SchemaError(
                    "selected ledger is missing or not a file; no database was created"
                )
            conn = self.connect(readonly=True)
            conn.close()
        except sqlite3.Error as error:
            reason = (
                str(error) if isinstance(error, SchemaError) else type(error).__name__
            )
            raise SchemaError(
                f"Ledger {Path(self.db_path).absolute()}: {reason}; "
                "use provenance_schema.py check --db <absolute-path>; "
                "PROV_DB must be exported (.env.local is not loaded)"
            ) from None

    def connect(self, *, readonly: bool = False) -> sqlite3.Connection:
        """Open an existing initialized ledger; missing paths never create a DB."""
        uri = Path(self.db_path).absolute().as_uri() + (
            "?mode=ro" if readonly else "?mode=rw"
        )
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        try:
            from provenance_schema import require_ready

            require_ready(conn, SCHEMA)
            if readonly:
                conn.execute("PRAGMA query_only = ON")
            return conn
        except BaseException:
            conn.close()
            raise

    def validate_ref_chain(
        self, conn, refs: dict
    ) -> tuple[bool, str | None, str | None]:
        """Validate exact L0→L3 linkage and return the owning binding ID."""
        if not complete_refs(refs):
            return False, None, "all four manifest refs are required"
        rows = {}
        for name in LAYER_ORDER:
            ref = refs[f"{name}_ref"]
            row = conn.execute(
                "SELECT layer_name,parent_ref,manifest_binding_id FROM manifest_layers WHERE layer_hash = ?",
                (ref,),
            ).fetchone()
            if not row:
                return False, None, f"{name}_ref not found"
            if row["layer_name"] != name:
                return False, None, f"{name}_ref points to {row['layer_name']} layer"
            rows[name] = row
        expected_parent = None
        for name in LAYER_ORDER:
            if rows[name]["parent_ref"] != expected_parent:
                return False, None, f"{name}_ref has invalid parent_ref"
            expected_parent = refs[f"{name}_ref"]
        binding_ids = {rows[name]["manifest_binding_id"] for name in LAYER_ORDER}
        if len(binding_ids) != 1 or None in binding_ids:
            return False, None, "manifest refs do not belong to one persisted binding"
        return True, binding_ids.pop(), None

    # ── reads ────────────────────────────────────────────────
    def health(self) -> tuple[int, dict]:
        conn = None
        try:
            conn = self.connect(readonly=True)
            conn.execute(
                "SELECT owner_json,canonical_body_json,receipt_json FROM agent_logs LIMIT 0"
            )
            count = conn.execute("SELECT COUNT(*) AS c FROM agent_logs").fetchone()["c"]
        except sqlite3.Error:
            return 503, {
                "status": "error",
                "service": "atp-provenance",
                "error": "provenance_unavailable",
            }
        finally:
            if conn is not None:
                conn.close()
        return 200, {
            "status": "ok",
            "service": "atp-provenance",
            "entries": count,
            "ts": now_iso(),
        }

    def manifest_layers(
        self,
        layer: str | None = None,
        manifest_binding_id: str | None = None,
        limit: int = 40,
    ) -> tuple[int, list]:
        conn = self.connect(readonly=True)
        try:
            if layer and manifest_binding_id:
                rows = conn.execute(
                    """SELECT * FROM manifest_layers
                       WHERE layer_name = ? AND manifest_binding_id = ?
                         AND manifest_binding_id IN (SELECT manifest_binding_id FROM manifest_bindings WHERE owner_json IS NULL)
                       ORDER BY bound_at DESC""",
                    (layer, manifest_binding_id),
                ).fetchall()
            elif manifest_binding_id:
                rows = conn.execute(
                    """SELECT * FROM manifest_layers
                       WHERE manifest_binding_id = ?
                         AND manifest_binding_id IN (SELECT manifest_binding_id FROM manifest_bindings WHERE owner_json IS NULL)
                       ORDER BY bound_at DESC""",
                    (manifest_binding_id,),
                ).fetchall()
            elif layer:
                rows = conn.execute(
                    "SELECT * FROM manifest_layers WHERE layer_name = ? AND (manifest_binding_id IS NULL OR manifest_binding_id IN (SELECT manifest_binding_id FROM manifest_bindings WHERE owner_json IS NULL)) AND NOT EXISTS (SELECT 1 FROM manifest_bindings AS owned WHERE owned.owner_json IS NOT NULL AND manifest_layers.layer_hash IN (owned.declaration_ref,owned.version_ref,owned.session_ref,owned.route_ref)) ORDER BY bound_at DESC",
                    (layer,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM manifest_layers WHERE (manifest_binding_id IS NULL OR manifest_binding_id IN (SELECT manifest_binding_id FROM manifest_bindings WHERE owner_json IS NULL)) AND NOT EXISTS (SELECT 1 FROM manifest_bindings AS owned WHERE owned.owner_json IS NOT NULL AND manifest_layers.layer_hash IN (owned.declaration_ref,owned.version_ref,owned.session_ref,owned.route_ref)) ORDER BY bound_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        finally:
            conn.close()
        return 200, [
            {
                "layer_hash": r["layer_hash"],
                "layer_name": r["layer_name"],
                "manifest_binding_id": r["manifest_binding_id"],
                "parent_ref": r["parent_ref"],
                "bound_at": r["bound_at"],
                "body": json.loads(r["body_json"]),
            }
            for r in rows
        ]

    def manifest_bindings(
        self, manifest_binding_id: str | None = None, limit: int = 40
    ) -> tuple[int, list]:
        conn = self.connect(readonly=True)
        try:
            if manifest_binding_id:
                rows = conn.execute(
                    "SELECT * FROM manifest_bindings WHERE manifest_binding_id = ? AND owner_json IS NULL",
                    (manifest_binding_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM manifest_bindings WHERE owner_json IS NULL ORDER BY updated_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        finally:
            conn.close()
        return 200, [
            {
                "manifest_binding_id": r["manifest_binding_id"],
                "session_id": r["session_id"],
                "refs": binding_refs(r),
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
            }
            for r in rows
        ]

    def chain(self, parent_prov_id: str | None) -> tuple[int, Any]:
        """Walk-back export of one ATP transaction: the root plus its children,
        ordered root-first then by manifest sequence number."""
        if not parent_prov_id:
            return 400, {"error": "parent_prov_id required"}
        conn = self.connect(readonly=True)
        try:
            rows = conn.execute(
                """SELECT al.*, ar.manifest_binding_id,
                          ar.declaration_ref, ar.version_ref, ar.session_ref, ar.route_ref,
                          ar.prev_action_hash, ar.semantic_fingerprint, ar.sequence_no,
                          st.capture_method, st.trajectory_id, st.step_index
                   FROM agent_logs al
                   LEFT JOIN action_refs ar ON ar.prov_id = al.prov_id
                   LEFT JOIN agent_steps st ON st.prov_id = al.prov_id
                   WHERE (al.prov_id = ? OR al.parent_prov_id = ?) AND al.owner_json IS NULL
                   ORDER BY CASE WHEN al.parent_prov_id IS NULL THEN 0 ELSE 1 END,
                            ar.sequence_no ASC, al.rowid ASC""",
                (parent_prov_id, parent_prov_id),
            ).fetchall()
        finally:
            conn.close()
        out = []
        for r in rows:
            entry = {
                "prov_id": r["prov_id"],
                "parent_prov_id": r["parent_prov_id"],
                "ts": r["ts"],
                "agent_id": r["agent_id"] or r["actor"],
                "kind": r["kind"]
                or ("atp_prompt" if r["parent_prov_id"] is None else "agent_action"),
                "body_sha256": r["body_sha256"],
            }
            if r["manifest_binding_id"]:
                entry["manifest_binding_id"] = r["manifest_binding_id"]
            refs = {key: r[key] for key in REF_KEYS}
            if any(refs.values()):
                entry["refs"] = refs
                entry["prev_action_hash"] = r["prev_action_hash"]
                entry["semantic_fingerprint"] = r["semantic_fingerprint"]
                entry["sequence_no"] = r["sequence_no"]
            for key, col in (
                ("action_type", "action_type"),
                ("target", "target"),
                ("result", "result"),
                ("payload_summary", "payload_summary"),
                ("actor", "actor"),
                ("model", "model"),
                ("phase", "phase"),
                ("status", "status"),
                ("error", "error"),
            ):
                if r[col]:
                    entry[key] = r[col]
            if r["latency_ms"] is not None:
                entry["latency_ms"] = r["latency_ms"]
            if r["input_json"]:
                entry["input"] = json.loads(r["input_json"])
            if r["output_json"]:
                entry["output"] = json.loads(r["output_json"])
            if r["tags_json"]:
                tags = json.loads(r["tags_json"])
                if tags:
                    entry["tags"] = tags
            if r["parent_prov_id"] is None and r["payload_summary"]:
                entry["atp_context"] = r["payload_summary"]
            if r["parent_prov_id"] is not None:
                # Who produced the row: the harness transcript, or the agent itself.
                entry["capture_method"] = r["capture_method"] or "self_reported"
                if r["trajectory_id"]:
                    entry["trajectory_id"] = r["trajectory_id"]
                    entry["step_index"] = r["step_index"]
            out.append(entry)
        return 200, out

    def verify_chain(self, parent_prov_id: str | None) -> tuple[int, Any]:
        """Check hash-link and sequence integrity across one transaction's actions.

        Verifies three properties, per manifest binding, over the children of
        ``parent_prov_id``:

          1. the first action in a binding has ``prev_action_hash = null``
          2. every later action's ``prev_action_hash`` equals the previous
             action's ``body_sha256`` (tampering with one row breaks the tail)
          3. ``sequence_no`` runs 1..n with no gaps and no forks

        This legacy endpoint does NOT recompute content hashes. Historical
        canonical bodies were not persisted, and no evidence is backfilled.
        The owned v1 verifier separately recomputes its original committed
        canonical bodies; this compatibility endpoint attests linkage only.
        """
        status, entries = self.chain(parent_prov_id)
        if status != 200:
            return status, entries
        if not entries:
            return 404, {
                "error": "no chain found",
                "reason": f"no root or child rows for parent_prov_id {parent_prov_id!r}",
                "hint": "mint a root first, or check the prov_id",
            }

        root = [e for e in entries if e["parent_prov_id"] is None]
        actions = [e for e in entries if e["parent_prov_id"] is not None]
        problems: list[dict] = []
        if not root:
            problems.append({"kind": "missing_root", "detail": "minted root is absent"})
        by_binding: dict[str | None, list] = {}
        for entry in actions:
            by_binding.setdefault(entry.get("manifest_binding_id"), []).append(entry)

        for binding_id, group in by_binding.items():
            if binding_id is None:
                problems.append(
                    {
                        "kind": "unbound_action",
                        "prov_ids": [e["prov_id"] for e in group],
                        "detail": "actions have no manifest binding; they are unattributable",
                    }
                )
                continue
            previous_hash = None
            for position, entry in enumerate(group, start=1):
                if entry.get("sequence_no") != position:
                    problems.append(
                        {
                            "kind": "sequence_gap",
                            "prov_id": entry["prov_id"],
                            "expected_sequence_no": position,
                            "found_sequence_no": entry.get("sequence_no"),
                            "manifest_binding_id": binding_id,
                        }
                    )
                if entry.get("prev_action_hash") != previous_hash:
                    problems.append(
                        {
                            "kind": "broken_link",
                            "prov_id": entry["prov_id"],
                            "expected_prev_action_hash": previous_hash,
                            "found_prev_action_hash": entry.get("prev_action_hash"),
                            "manifest_binding_id": binding_id,
                        }
                    )
                if not complete_refs(entry.get("refs") or {}):
                    problems.append(
                        {
                            "kind": "incomplete_manifest",
                            "prov_id": entry["prov_id"],
                            "detail": "action is missing one or more of the four manifest refs",
                            "manifest_binding_id": binding_id,
                        }
                    )
                previous_hash = entry["body_sha256"]

        capture = self._verify_capture(parent_prov_id, problems)
        capture_counts: dict[str, int] = {}
        for entry in actions:
            method = entry.get("capture_method", "self_reported")
            capture_counts[method] = capture_counts.get(method, 0) + 1

        return 200, {
            "parent_prov_id": parent_prov_id,
            "verified": not problems,
            "root_present": bool(root),
            "capture_methods": capture_counts,
            "trajectories": capture,
            "action_count": len(actions),
            "bindings": sorted(b for b in by_binding if b is not None),
            "checks": [
                "prev_action_hash linkage",
                "sequence_no continuity",
                "manifest ref completeness",
                "trajectory step_index continuity",
                "trajectory chunk chain continuity",
                "step source offsets inside recorded chunks",
            ],
            "not_checked": [
                "body_sha256 recomputation (legacy endpoint checks linkage only)",
                (
                    "chunk_sha256 against the original transcript bytes (Prove does not keep them; "
                    + "recompute with trajectory.py chain on the producer's copy)"
                ),
            ],
            "problems": problems,
        }

    def _verify_capture(self, parent_prov_id: str, problems: list) -> dict:
        """Per-trajectory completeness: no step gaps, an unbroken chunk chain,
        and every step located inside a chunk Prove actually consumed."""
        conn = self.connect(readonly=True)
        try:
            chunks = conn.execute(
                "SELECT * FROM trajectory_chunks WHERE parent_prov_id=? ORDER BY trajectory_id, chunk_no",
                (parent_prov_id,),
            ).fetchall()
            steps = conn.execute(
                "SELECT prov_id,trajectory_id,chunk_no,step_index,source_offset FROM agent_steps WHERE parent_prov_id=?",
                (parent_prov_id,),
            ).fetchall()
            # The exported actions for captured steps: a log row and its refs.
            actions = {
                row[0]
                for row in conn.execute(
                    """SELECT al.prov_id FROM agent_logs al JOIN action_refs ar ON ar.prov_id=al.prov_id
                       WHERE al.parent_prov_id=? AND al.kind='agent_step'""",
                    (parent_prov_id,),
                )
            }
        finally:
            conn.close()
        step_ids = {step["prov_id"] for step in steps}
        for step in steps:
            if step["prov_id"] not in actions:
                problems.append({
                    "kind": "step_action_missing",
                    "prov_id": step["prov_id"],
                    "trajectory_id": step["trajectory_id"],
                    "step_index": step["step_index"],
                })
        for prov_id in sorted(actions - step_ids):
            problems.append({"kind": "action_step_missing", "prov_id": prov_id})
        summary: dict[str, dict] = {}
        by_chunk = {}
        for chunk in chunks:
            tid = chunk["trajectory_id"]
            info = summary.setdefault(tid, {"chunks": 0, "steps": 0, "consumed_bytes": 0, "chain_sha256": None})
            expected_prior = info["chain_sha256"]
            expected_start = info["consumed_bytes"]
            if chunk["chunk_no"] != info["chunks"] + 1 or chunk["start_offset"] != expected_start or chunk["prior_chain_sha256"] != expected_prior:
                problems.append({"kind": "chunk_chain_break", "trajectory_id": tid, "chunk_no": chunk["chunk_no"]})
            recomputed = hashlib.sha256(((chunk["prior_chain_sha256"] or "") + chunk["chunk_sha256"]).encode()).hexdigest()
            if recomputed != chunk["chain_sha256"]:
                problems.append({"kind": "chunk_hash_mismatch", "trajectory_id": tid, "chunk_no": chunk["chunk_no"]})
            info.update(chunks=info["chunks"] + 1, consumed_bytes=chunk["end_offset"], chain_sha256=chunk["chain_sha256"])
            by_chunk[(tid, chunk["chunk_no"])] = chunk
        indexes: dict[str, list] = {}
        present: dict[tuple, set] = {}
        for step in steps:
            tid = step["trajectory_id"]
            indexes.setdefault(tid, []).append(step["step_index"])
            present.setdefault((tid, step["chunk_no"]), set()).add(step["step_index"])
            chunk = by_chunk.get((tid, step["chunk_no"]))
            if not chunk or not chunk["start_offset"] <= step["source_offset"] < chunk["end_offset"]:
                problems.append({"kind": "step_outside_chunk", "prov_id": step["prov_id"], "trajectory_id": tid})
        # Each chunk records which steps it produced. Check them against the
        # rows that survive, so deleting the last steps (or every step of a
        # chunk) shows as missing instead of a shorter, intact-looking capture.
        for (tid, chunk_no), chunk in by_chunk.items():
            count = chunk["step_count"] or 0
            if not count:
                continue
            have = present.get((tid, chunk_no), set())
            if chunk["harness"] == "trajectory_json":
                # Producer-numbered steps need not be contiguous; the count must hold.
                if len(have) != count:
                    problems.append({
                        "kind": "chunk_steps_missing",
                        "trajectory_id": tid,
                        "chunk_no": chunk_no,
                        "missing_count": count - len(have),
                    })
                continue
            first = chunk["first_step_index"]
            if first is None:
                problems.append({"kind": "chunk_step_range_unknown", "trajectory_id": tid, "chunk_no": chunk_no})
                continue
            expected = set(range(first, first + count))
            lost = sorted(expected - have)
            if lost:
                problems.append({
                    "kind": "chunk_steps_missing",
                    "trajectory_id": tid,
                    "chunk_no": chunk_no,
                    "missing_step_indexes": lost[:50],
                    "missing_count": len(lost),
                })
            extra = sorted(have - expected)
            if extra:
                problems.append({
                    "kind": "step_outside_chunk_range",
                    "trajectory_id": tid,
                    "chunk_no": chunk_no,
                    "step_indexes": extra[:50],
                })
        for tid, found in indexes.items():
            summary.setdefault(tid, {"chunks": 0, "steps": 0, "consumed_bytes": 0, "chain_sha256": None})
            summary[tid]["steps"] = len(found)
            missing = sorted(set(range(0, max(found) + 1)) - set(found))
            if missing:
                problems.append({
                    "kind": "step_index_gap",
                    "trajectory_id": tid,
                    "missing_step_indexes": missing[:50],
                    "missing_count": len(missing),
                })
        return summary

    # ── writes ───────────────────────────────────────────────
    @staticmethod
    def _legacy_payload(payload):
        if not isinstance(payload, dict):
            return 422, {"error": "invalid_request"}
        for alias in ("parent_id", "agent"):
            if alias in payload:
                return 422, {"error": "unsupported field: " + alias}
        if "ts" in payload and not isinstance(payload["ts"], str):
            return 422, {"error": "ts must be a string"}
        for key in (
            "prov_id",
            "parent_prov_id",
            "manifest_binding_id",
            "session_id",
            "agent_id",
            "actor",
        ):
            if payload.get(key) is not None and not valid_id(payload[key]):
                return 422, {"error": "invalid_request"}
        if any(key in payload for key in ("owner", "auth_receipt")):
            return 422, {"error": "invalid_request"}
        try:
            sanitized(payload)
        except (ValueError, TypeError, OverflowError):
            return 422, {"error": "invalid_request"}
        return None

    def mint(self, payload: dict) -> tuple[int, dict]:
        """Legacy one-shot root mint. Idempotent owned mint uses /v1/mint."""
        error = self._legacy_payload(payload)
        if error:
            return error
        value = sanitized(payload)
        prov_id, ts = str(uuid.uuid4()), now_iso()
        context = value.get("atp_context") or value.get("context") or "ATP prompt"
        if not isinstance(context, str):
            return 422, {"error": "invalid_request"}
        agent_id = value.get("agent_id", "unknown")
        actor = value.get("actor") or agent_id
        record = {
            "prov_id": prov_id,
            "parent_prov_id": None,
            "ts": ts,
            "agent_id": agent_id,
            "actor": actor,
            "model": value.get("model"),
            "kind": "atp_prompt",
            "phase": "atp_prompt",
            "atp_context": context,
            "input": value.get("input"),
            "output": value.get("output"),
            "tags": value.get("tags") or [],
            "latency_ms": value.get("latency_ms"),
            "error": value.get("error"),
        }
        receipt = {
            "prov_id": prov_id,
            "ts": ts,
            "atp_context": context,
            "agent_id": agent_id,
            "actor": actor,
            "model": value.get("model"),
        }
        conn = self.connect()
        try:
            with conn:
                conn.execute(
                    """INSERT INTO agent_logs(prov_id,parent_prov_id,ts,agent_id,actor,model,kind,phase,status,result,
                       input_json,output_json,error,latency_ms,tags_json,payload_summary,body_sha256,canonical_body_json,receipt_json)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        prov_id,
                        None,
                        ts,
                        agent_id,
                        actor,
                        value.get("model"),
                        "atp_prompt",
                        "atp_prompt",
                        "ok",
                        "accepted",
                        canonical_json(record["input"]),
                        canonical_json(record["output"]),
                        record["error"],
                        record["latency_ms"],
                        canonical_json(record["tags"]),
                        context,
                        body_hash(record),
                        canonical_json(record),
                        canonical_json(receipt),
                    ),
                )
        finally:
            conn.close()
        return 200, receipt

    def _bind_layer(self, conn, payload):
        error = self._legacy_payload(payload)
        if error:
            return error
        name, binding_id, session_id = (
            payload.get("layer"),
            payload.get("manifest_binding_id"),
            payload.get("session_id"),
        )
        if name not in LAYER_ORDER:
            return 400, {"error": "invalid layer"}
        if not binding_id or not isinstance(payload.get("body", {}), dict):
            return 422, {"error": "invalid_request"}
        body = sanitized(payload.get("body", {}))
        body.pop("bound_at", None)
        parent_ref = payload.get("parent_ref")
        if parent_ref is not None and (
            not isinstance(parent_ref, str) or not HASH_PATTERN.fullmatch(parent_ref)
        ):
            return 422, {"error": "invalid_request"}
        idx = LAYER_ORDER.index(name)
        binding = conn.execute(
            "SELECT * FROM manifest_bindings WHERE manifest_binding_id=?", (binding_id,)
        ).fetchone()
        if binding and binding["owner_json"] is not None:
            return 404, {"error": "not_found"}
        if not binding:
            if name != "declaration" or not session_id:
                return 422, {
                    "error": "binding must begin with declaration and session_id"
                }
            if parent_ref is not None:
                return 409, {"error": "parent_ref does not match binding head"}
        elif session_id and binding["session_id"] != session_id:
            return 422, {"error": "session_id does not match persisted binding"}
        if name == "session" and body.get("session_id") != binding["session_id"]:
            return 422, {"error": "session layer must use the binding session_id"}
        expected_parent = None if idx == 0 else binding[f"{LAYER_ORDER[idx - 1]}_ref"]
        if idx > 0 and not expected_parent:
            return 422, {"error": "binding predecessor missing"}
        if parent_ref != expected_parent:
            return 409, {"error": "parent_ref does not match binding head"}
        if binding and binding[f"{name}_ref"]:
            prior = conn.execute(
                "SELECT * FROM manifest_layers WHERE layer_hash=?",
                (binding[f"{name}_ref"],),
            ).fetchone()
            if prior:
                old_body = json.loads(prior["body_json"])
                old_body.pop("bound_at", None)
                if old_body == body and prior["parent_ref"] == parent_ref:
                    return 200, {
                        "layer": name,
                        "layer_hash": prior["layer_hash"],
                        "manifest_binding_id": binding_id,
                        "session_id": binding["session_id"],
                        "parent_ref": parent_ref,
                        "bound_at": prior["bound_at"],
                        "refs": binding_refs(binding),
                    }
        bound_at = now_iso()
        if not binding:
            conn.execute(
                "INSERT INTO manifest_bindings(manifest_binding_id,session_id,created_at,updated_at) VALUES(?,?,?,?)",
                (binding_id, session_id, bound_at, bound_at),
            )
        layer_body = {**body, "bound_at": bound_at}
        layer_hash = canonical_hash(
            {"layer": name, "body": layer_body, "parent_ref": parent_ref}
        )
        conn.execute(
            "INSERT INTO manifest_layers(layer_hash,layer_name,parent_ref,manifest_binding_id,bound_at,body_json) VALUES(?,?,?,?,?,?)",
            (
                layer_hash,
                name,
                parent_ref,
                binding_id,
                bound_at,
                canonical_json(layer_body),
            ),
        )
        updates = [f"{name}_ref=?", "updated_at=?"] + [
            f"{stale}_ref=NULL" for stale in LAYER_ORDER[idx + 1 :]
        ]
        conn.execute(
            "UPDATE manifest_bindings SET "
            + ", ".join(updates)
            + " WHERE manifest_binding_id=?",
            (layer_hash, bound_at, binding_id),
        )
        binding = conn.execute(
            "SELECT * FROM manifest_bindings WHERE manifest_binding_id=?", (binding_id,)
        ).fetchone()
        return 200, {
            "layer": name,
            "layer_hash": layer_hash,
            "manifest_binding_id": binding_id,
            "session_id": binding["session_id"],
            "parent_ref": parent_ref,
            "bound_at": bound_at,
            "refs": binding_refs(binding),
        }

    def bind_layer(self, payload: dict) -> tuple[int, dict]:
        """One explicit legacy layer update; exact retries preserve descendants."""
        conn = self.connect()
        try:
            with conn:
                conn.execute("BEGIN IMMEDIATE")
                return self._bind_layer(conn, payload)
        finally:
            conn.close()

    def bind_chain(
        self,
        manifest_binding_id: str,
        session_id: str,
        declaration: dict,
        version: dict,
        session: dict | None = None,
        route: dict | None = None,
    ) -> tuple[int, dict]:
        """Bind the complete legacy chain atomically; failures roll back all layers."""
        if not isinstance(session or {}, dict):
            return 422, {"error": "invalid_request"}
        layers = [
            ("declaration", declaration),
            ("version", version),
            ("session", {**(session or {}), "session_id": session_id}),
            ("route", route if route is not None else {}),
        ]
        conn = self.connect()
        try:
            with conn:
                conn.execute("BEGIN IMMEDIATE")
                parent_ref, bound = None, []
                for name, body in layers:
                    status, result = self._bind_layer(
                        conn,
                        {
                            "layer": name,
                            "body": body,
                            "parent_ref": parent_ref,
                            "manifest_binding_id": manifest_binding_id,
                            "session_id": session_id,
                        },
                    )
                    if status != 200:
                        conn.rollback()
                        return status, {
                            **result,
                            "failed_layer": name,
                            "layers_bound": [],
                        }
                    bound.append(result)
                    parent_ref = result["layer_hash"]
                result = {
                    "manifest_binding_id": manifest_binding_id,
                    "session_id": session_id,
                    "refs": bound[-1]["refs"],
                    "layers": [
                        {
                            "layer": b["layer"],
                            "layer_hash": b["layer_hash"],
                            "bound_at": b["bound_at"],
                        }
                        for b in bound
                    ],
                }
            return 200, result
        finally:
            conn.close()

    @staticmethod
    def _legacy_action_record(
        payload, prov_id, ts, binding_id, refs, previous_hash, sequence_no
    ):
        value = sanitized(payload)
        action = value.get("canonical_action") or {}
        fingerprint = value.get("semantic_fingerprint") or (
            semantic_fingerprint_of(action)
            if isinstance(action, dict) and action
            else None
        )
        summary = (
            value.get("payload_summary")
            or (
                value.get("output", {}).get("summary")
                if isinstance(value.get("output"), dict)
                else None
            )
            or ""
        )
        return {
            "prov_id": prov_id,
            "parent_prov_id": value["parent_prov_id"],
            "ts": ts,
            "agent_id": value.get("agent_id") or value.get("actor"),
            "actor": value.get("actor"),
            "model": value.get("model"),
            "kind": value.get("kind", "agent_action"),
            "phase": value.get("phase"),
            "action_type": value.get("action_type"),
            "target": value.get("target"),
            "status": value.get("status", "ok"),
            "result": value.get("result", "accepted"),
            "input": value.get("input"),
            "output": value.get("output"),
            "error": value.get("error"),
            "latency_ms": value.get("latency_ms"),
            "tags": value.get("tags") or [],
            "summary": summary,
            "manifest_binding_id": binding_id,
            "refs": refs,
            "canonical_action": action or None,
            "semantic_fingerprint": fingerprint,
            "prev_action_hash": previous_hash,
            "sequence_no": sequence_no,
        }

    def log_action(self, payload: dict) -> tuple[int, dict]:
        """Immutable legacy append with exact-ID replay; never overwrites roots."""
        error = self._legacy_payload(payload)
        if error:
            return error
        parent, prov_id = payload.get("parent_prov_id"), payload.get("prov_id")
        if not parent:
            return (
                (409, {"error": "prov_id already exists"})
                if prov_id
                else (422, {"error": "parent_prov_id required"})
            )
        refs = payload.get("refs") or {}
        if not isinstance(refs, dict):
            return 422, {"error": "invalid_request"}
        prov_id = prov_id or str(uuid.uuid4())
        conn = self.connect()
        try:
            with conn:
                conn.execute("BEGIN IMMEDIATE")
                root = conn.execute(
                    "SELECT * FROM agent_logs WHERE prov_id=? AND parent_prov_id IS NULL AND kind='atp_prompt' AND owner_json IS NULL",
                    (parent,),
                ).fetchone()
                if not root:
                    return 404, {"error": "parent root not found"}
                existing = conn.execute(
                    "SELECT * FROM agent_logs WHERE prov_id=?", (prov_id,)
                ).fetchone()
                historic = None
                if existing:
                    try:
                        historic = json.loads(existing["canonical_body_json"])
                        if (
                            existing["owner_json"] is not None
                            or not isinstance(historic, dict)
                            or historic.get("parent_prov_id") != parent
                            or body_hash(historic) != existing["body_sha256"]
                        ):
                            return 409, {"error": "prov_id already exists"}
                    except (ValueError, TypeError):
                        return 409, {"error": "prov_id already exists"}
                binding_id = payload.get("manifest_binding_id")
                if binding_id:
                    binding = conn.execute(
                        "SELECT * FROM manifest_bindings WHERE manifest_binding_id=? AND owner_json IS NULL",
                        (binding_id,),
                    ).fetchone()
                    if not binding:
                        return 422, {"error": "manifest_binding_id not found"}
                    if (
                        payload.get("session_id")
                        and payload["session_id"] != binding["session_id"]
                    ):
                        return 422, {
                            "error": "session_id does not match persisted binding"
                        }
                    resolved = (
                        {key: historic.get("refs", {}).get(key) for key in REF_KEYS}
                        if historic
                        and historic.get("manifest_binding_id") == binding_id
                        else binding_refs(binding)
                    )
                    if not complete_refs(resolved):
                        return 422, {"error": "manifest binding is incomplete"}
                    if refs and refs != resolved:
                        return 409, {
                            "error": "supplied refs do not match persisted binding"
                        }
                    refs = resolved
                elif complete_refs(refs):
                    valid, binding_id, reason = self.validate_ref_chain(conn, refs)
                    if not valid:
                        return 422, {"error": "invalid manifest refs"}
                    binding = conn.execute(
                        "SELECT * FROM manifest_bindings WHERE manifest_binding_id=? AND owner_json IS NULL",
                        (binding_id,),
                    ).fetchone()
                    if (
                        not binding
                        or payload.get("session_id")
                        and payload["session_id"] != binding["session_id"]
                    ):
                        return 422, {"error": "invalid manifest refs"}
                else:
                    return 422, {
                        "error": "manifest context required for child log",
                        "reason": "provide manifest_binding_id or all four refs",
                    }
                if not historic and self._requires_harness_capture(conn, binding_id):
                    return 422, {
                        "error": "harness capture required for this binding",
                        "reason": "self-reported /log entries are refused; send the transcript to /ingest/trajectory",
                    }
                if historic:
                    previous_hash, sequence_no = (
                        historic.get("prev_action_hash"),
                        historic.get("sequence_no"),
                    )
                    ts = payload.get("ts", historic["ts"])
                else:
                    previous = conn.execute(
                        """SELECT al.body_sha256,ar.sequence_no FROM agent_logs al JOIN action_refs ar ON ar.prov_id=al.prov_id
                                               WHERE al.parent_prov_id=? AND ar.manifest_binding_id=? ORDER BY ar.sequence_no DESC LIMIT 1""",
                        (parent, binding_id),
                    ).fetchone()
                    previous_hash = previous["body_sha256"] if previous else None
                    sequence_no = (previous["sequence_no"] or 0) + 1 if previous else 1
                    ts = payload.get("ts") or now_iso()
                if (
                    payload.get("prev_action_hash") is not None
                    and payload["prev_action_hash"] != previous_hash
                ):
                    return 409, {
                        "error": "prev_action_hash does not match binding chain head"
                    }
                record = self._legacy_action_record(
                    payload, prov_id, ts, binding_id, refs, previous_hash, sequence_no
                )
                digest = body_hash(record)
                receipt = {
                    "prov_id": prov_id,
                    "parent_prov_id": parent,
                    "ts": ts,
                    "manifest_binding_id": binding_id,
                    "refs": refs,
                    "prev_action_hash": previous_hash,
                    "sequence_no": sequence_no,
                    "semantic_fingerprint": record["semantic_fingerprint"],
                    "body_sha256": digest,
                    "layers_bound": 4,
                }
                if existing:
                    if record != historic:
                        return 409, {"error": "prov_id already exists"}
                    try:
                        original = json.loads(existing["receipt_json"])
                        if original != receipt:
                            return 409, {"error": "prov_id already exists"}
                    except (ValueError, TypeError):
                        return 409, {"error": "prov_id already exists"}
                    return 200, original
                conn.execute(
                    """INSERT INTO agent_logs(prov_id,parent_prov_id,ts,agent_id,actor,model,kind,phase,action_type,target,
                       result,status,input_json,output_json,error,latency_ms,tags_json,payload_summary,body_sha256,canonical_body_json,receipt_json)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        prov_id,
                        parent,
                        ts,
                        record["agent_id"],
                        record["actor"],
                        record["model"],
                        record["kind"],
                        record["phase"],
                        record["action_type"],
                        record["target"],
                        record["result"],
                        record["status"],
                        canonical_json(record["input"]),
                        canonical_json(record["output"]),
                        record["error"],
                        record["latency_ms"],
                        canonical_json(record["tags"]),
                        record["summary"],
                        digest,
                        canonical_json(record),
                        canonical_json(receipt),
                    ),
                )
                conn.execute(
                    """INSERT INTO action_refs(prov_id,manifest_binding_id,declaration_ref,version_ref,session_ref,route_ref,
                                prev_action_hash,semantic_fingerprint,sequence_no) VALUES(?,?,?,?,?,?,?,?,?)""",
                    (
                        prov_id,
                        binding_id,
                        *(refs[key] for key in REF_KEYS),
                        previous_hash,
                        record["semantic_fingerprint"],
                        sequence_no,
                    ),
                )
            return 200, receipt
        finally:
            conn.close()

    # ── harness step capture ─────────────────────────────────
    # Prove reads the harness's own transcript instead of trusting a summary
    # the agent chose to write. See STEP_CAPTURE.md.
    INGEST_MAX_CHUNK = 1536 * 1024
    INGEST_MAX_STEPS = 500
    # A single record too large for a chunk is sent as length + digest only.
    INGEST_MAX_OVERSIZED = 1 << 30

    @staticmethod
    def _requires_harness_capture(conn, binding_id) -> bool:
        if not binding_id:
            return False
        row = conn.execute(
            "SELECT require_harness_capture FROM capture_policies WHERE manifest_binding_id=?",
            (binding_id,),
        ).fetchone()
        return bool(row and row[0])

    def set_capture_policy(self, payload: dict) -> tuple[int, dict]:
        """Monotonic per-binding switch: once harness capture is required it stays required."""
        if (
            not isinstance(payload, dict)
            or set(payload) != {"manifest_binding_id", "require_harness_capture"}
            or not valid_id(payload["manifest_binding_id"])
            or not isinstance(payload["require_harness_capture"], bool)
        ):
            return 422, {"error": "invalid_request"}
        if not payload["require_harness_capture"]:
            return 422, {"error": "capture policy cannot be relaxed"}
        binding_id = payload["manifest_binding_id"]
        conn = self.connect()
        try:
            with conn:
                conn.execute("BEGIN IMMEDIATE")
                if not conn.execute(
                    "SELECT 1 FROM manifest_bindings WHERE manifest_binding_id=? AND owner_json IS NULL",
                    (binding_id,),
                ).fetchone():
                    return 404, {"error": "manifest_binding_id not found"}
                existing = conn.execute(
                    "SELECT set_at FROM capture_policies WHERE manifest_binding_id=?",
                    (binding_id,),
                ).fetchone()
                set_at = existing["set_at"] if existing else now_iso()
                if not existing:
                    conn.execute(
                        "INSERT INTO capture_policies(manifest_binding_id,require_harness_capture,set_at) VALUES(?,?,?)",
                        (binding_id, 1, set_at),
                    )
            return 200, {
                "manifest_binding_id": binding_id,
                "require_harness_capture": True,
                "set_at": set_at,
            }
        finally:
            conn.close()

    def ingest_trajectory(self, payload: dict) -> tuple[int, dict]:
        """Append one transcript chunk; every complete record becomes a chained child step.

        Chunks must continue the trajectory exactly: ``offset`` equals the bytes
        already consumed and ``prior_chain_sha256`` equals the stored chain
        head, otherwise 409 with the expected values. Raw chunk bytes are never
        stored, only their sha256 folded into ``chain_sha256``.
        """
        allowed = {
            "parent_prov_id", "manifest_binding_id", "trajectory_id", "harness",
            "offset", "chunk", "prior_chain_sha256", "workspace_root", "agent_id",
            "model", "session_id", "parent_agent_ref", "oversized_record",
        }
        required = {"parent_prov_id", "manifest_binding_id", "trajectory_id", "harness", "offset", "chunk"}
        if not isinstance(payload, dict) or not required <= payload.keys() or not payload.keys() <= allowed:
            return 422, {"error": "invalid_request"}
        parent, binding_id = payload["parent_prov_id"], payload["manifest_binding_id"]
        trajectory_id, harness = payload["trajectory_id"], payload["harness"]
        offset, chunk_text = payload["offset"], payload["chunk"]
        prior = payload.get("prior_chain_sha256")
        root_dir = payload.get("workspace_root")
        if (
            any(not valid_id(v) for v in (parent, binding_id, trajectory_id))
            or harness not in harness_capture.HARNESSES
            or type(offset) is not int or offset < 0
            or not isinstance(chunk_text, str)
            or prior is not None and (not isinstance(prior, str) or not HASH_PATTERN.fullmatch(prior))
            or root_dir is not None and (not isinstance(root_dir, str) or len(root_dir) > 1024)
            or any(
                payload.get(k) is not None and not valid_id(payload[k])
                for k in ("agent_id", "session_id", "parent_agent_ref")
            )
            or payload.get("model") is not None and not isinstance(payload["model"], str)
        ):
            return 422, {"error": "invalid_request"}
        oversized = payload.get("oversized_record")
        if oversized is not None:
            # One JSONL record larger than a chunk: Prove records where it is,
            # how long it is and its sha256, so capture continues past it and
            # the chain still folds in the same bytes the producer read.
            if (
                harness != "claude_code_jsonl"
                or chunk_text != ""
                or not isinstance(oversized, dict)
                or set(oversized) != {"bytes", "sha256"}
                or type(oversized["bytes"]) is not int
                or not 0 < oversized["bytes"] <= self.INGEST_MAX_OVERSIZED
                or not isinstance(oversized["sha256"], str)
                or not HASH_PATTERN.fullmatch(oversized["sha256"])
            ):
                return 422, {"error": "invalid_request"}
            chunk, records, consumed = b"", [], oversized["bytes"]
        else:
            chunk = chunk_text.encode("utf-8")
            if len(chunk) > self.INGEST_MAX_CHUNK:
                return 413, {"error": "chunk too large", "max_bytes": self.INGEST_MAX_CHUNK}
            try:
                records, consumed = harness_capture.split_records(harness, chunk)
            except (ValueError, UnicodeError):
                return 422, {"error": "malformed transcript record"}
        if len(records) > self.INGEST_MAX_STEPS:
            return 413, {"error": "too many records in one chunk", "max_steps": self.INGEST_MAX_STEPS}
        agent_id = payload.get("agent_id") or "harness"
        conn = self.connect()
        try:
            with conn:
                conn.execute("BEGIN IMMEDIATE")
                root = conn.execute(
                    "SELECT 1 FROM agent_logs WHERE prov_id=? AND parent_prov_id IS NULL AND kind='atp_prompt' AND owner_json IS NULL",
                    (parent,),
                ).fetchone()
                if not root:
                    return 404, {"error": "parent root not found"}
                binding = conn.execute(
                    "SELECT * FROM manifest_bindings WHERE manifest_binding_id=? AND owner_json IS NULL",
                    (binding_id,),
                ).fetchone()
                if not binding:
                    return 422, {"error": "manifest_binding_id not found"}
                if payload.get("session_id") and payload["session_id"] != binding["session_id"]:
                    return 422, {"error": "session_id does not match persisted binding"}
                refs = binding_refs(binding)
                if not complete_refs(refs):
                    return 422, {"error": "manifest binding is incomplete"}
                head = conn.execute(
                    "SELECT * FROM trajectory_chunks WHERE trajectory_id=? ORDER BY chunk_no DESC LIMIT 1",
                    (trajectory_id,),
                ).fetchone()
                if head and (
                    head["parent_prov_id"] != parent
                    or head["manifest_binding_id"] != binding_id
                    or head["harness"] != harness
                ):
                    return 409, {"error": "trajectory_id belongs to another root, binding or harness"}
                expected_offset = head["end_offset"] if head else 0
                expected_chain = head["chain_sha256"] if head else None
                if offset != expected_offset or prior != expected_chain:
                    return 409, {
                        "error": "chunk does not continue the trajectory",
                        "expected_offset": expected_offset,
                        "expected_prior_chain_sha256": expected_chain,
                    }
                if oversized is None and (consumed == 0 or not records):
                    return 200, {
                        "trajectory_id": trajectory_id,
                        "steps": 0,
                        "consumed_to": offset,
                        "chain_sha256": expected_chain,
                    }
                chunk_no = head["chunk_no"] + 1 if head else 1
                next_index = (
                    head["first_step_index"] + head["step_count"]
                    if head and head["first_step_index"] is not None
                    else 0
                )
                if oversized is not None:
                    steps = [harness_capture.oversized_step(next_index, consumed, oversized["sha256"])]
                    chunk_sha = oversized["sha256"]
                else:
                    try:
                        steps = harness_capture.normalize(harness, records, root_dir, next_index)
                    except (ValueError, TypeError, AttributeError):
                        return 422, {"error": "malformed transcript record"}
                    chunk_sha = hashlib.sha256(chunk[:consumed]).hexdigest()
                chain = hashlib.sha256(((prior or "") + chunk_sha).encode()).hexdigest()
                ingested_at = now_iso()
                previous = conn.execute(
                    """SELECT al.body_sha256,ar.sequence_no FROM agent_logs al JOIN action_refs ar ON ar.prov_id=al.prov_id
                       WHERE al.parent_prov_id=? AND ar.manifest_binding_id=? ORDER BY ar.sequence_no DESC LIMIT 1""",
                    (parent, binding_id),
                ).fetchone()
                previous_hash = previous["body_sha256"] if previous else None
                sequence_no = (previous["sequence_no"] or 0) if previous else 0
                prov_ids = []
                for step in steps:
                    if conn.execute(
                        "SELECT 1 FROM agent_steps WHERE trajectory_id=? AND step_index=?",
                        (trajectory_id, step["step_index"]),
                    ).fetchone():
                        conn.rollback()
                        return 409, {"error": "duplicate step_index", "step_index": step["step_index"]}
                    sequence_no += 1
                    prov_id = str(uuid.uuid4())
                    absolute_offset = offset + step["source_offset"]
                    step_body = {
                        **step,
                        "trajectory_id": trajectory_id,
                        "chunk_no": chunk_no,
                        "source_offset": absolute_offset,
                        "capture_method": "harness_transcript",
                        "harness": harness,
                        "parent_agent_ref": payload.get("parent_agent_ref"),
                    }
                    first_call = step["tool_calls"][0]["tool_name"] if step["tool_calls"] else None
                    target = first_call or next(
                        (a.get("rel_path") for a in step["artifacts"] if a.get("rel_path")), None
                    ) or step["step_type"]
                    action = {
                        "runtime_family": harness,
                        "adapter": "trajectory_ingest",
                        "executable": first_call,
                        "operation": step["step_type"],
                        "target": target if isinstance(target, str) else None,
                        "systems_touched": sorted(
                            {c["tool_name"] for c in step["tool_calls"] if isinstance(c["tool_name"], str)}
                        ),
                    }
                    record = self._legacy_action_record(
                        {
                            "parent_prov_id": parent,
                            "agent_id": agent_id,
                            "actor": agent_id,
                            "model": payload.get("model"),
                            "kind": "agent_step",
                            "phase": "step",
                            "action_type": step["step_type"],
                            "target": target if isinstance(target, str) else "step",
                            "status": "error" if step["status"] == "error" else "ok",
                            "payload_summary": harness_capture.describe(step),
                            "input": {"step": step_body},
                            "tags": ["harness_capture", harness],
                            "canonical_action": action,
                        },
                        prov_id,
                        ingested_at,
                        binding_id,
                        refs,
                        previous_hash,
                        sequence_no,
                    )
                    digest = body_hash(record)
                    clean = record["input"]["step"]  # sanitized: secrets redacted
                    receipt = {
                        "prov_id": prov_id,
                        "parent_prov_id": parent,
                        "ts": ingested_at,
                        "manifest_binding_id": binding_id,
                        "refs": refs,
                        "prev_action_hash": previous_hash,
                        "sequence_no": sequence_no,
                        "semantic_fingerprint": record["semantic_fingerprint"],
                        "body_sha256": digest,
                        "layers_bound": 4,
                        "trajectory_id": trajectory_id,
                        "step_index": step["step_index"],
                    }
                    conn.execute(
                        """INSERT INTO agent_logs(prov_id,parent_prov_id,ts,agent_id,actor,model,kind,phase,action_type,target,
                           result,status,input_json,output_json,error,latency_ms,tags_json,payload_summary,body_sha256,canonical_body_json,receipt_json)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            prov_id, parent, ingested_at, record["agent_id"], record["actor"], record["model"],
                            record["kind"], record["phase"], record["action_type"], record["target"],
                            record["result"], record["status"], canonical_json(record["input"]),
                            canonical_json(record["output"]), record["error"], step["duration_ms"],
                            canonical_json(record["tags"]), record["summary"], digest,
                            canonical_json(record), canonical_json(receipt),
                        ),
                    )
                    conn.execute(
                        """INSERT INTO action_refs(prov_id,manifest_binding_id,declaration_ref,version_ref,session_ref,route_ref,
                                    prev_action_hash,semantic_fingerprint,sequence_no) VALUES(?,?,?,?,?,?,?,?,?)""",
                        (prov_id, binding_id, *(refs[key] for key in REF_KEYS), previous_hash,
                         record["semantic_fingerprint"], sequence_no),
                    )
                    conn.execute(
                        """INSERT INTO agent_steps(prov_id,parent_prov_id,trajectory_id,chunk_no,parent_agent_ref,step_index,source,
                           step_type,status,created_at,started_at,completed_at,duration_ms,content_sha256,content_bytes,
                           thinking_present,thinking_sha256,truncated_fields_json,tool_use_id,capture_method,source_offset)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            prov_id, parent, trajectory_id, chunk_no, payload.get("parent_agent_ref"),
                            clean["step_index"], _scalar(clean["source"]), _scalar(clean["step_type"]),
                            _scalar(clean["status"]), _scalar(clean["created_at"]), clean["started_at"],
                            clean["completed_at"], clean["duration_ms"], clean["content_sha256"],
                            clean["content_bytes"], int(clean["thinking_present"]), clean["thinking_sha256"],
                            canonical_json(clean["truncated_fields"]), _scalar(clean["tool_use_id"]),
                            "harness_transcript", absolute_offset,
                        ),
                    )
                    for call in clean["tool_calls"]:
                        conn.execute(
                            "INSERT INTO step_tool_calls(prov_id,call_index,tool_name,tool_use_id,args_json,args_sha256) VALUES(?,?,?,?,?,?)",
                            (prov_id, call["call_index"], _scalar(call["tool_name"]) or "unknown",
                             _scalar(call.get("tool_use_id")), canonical_json(call["args"]), call["args_sha256"]),
                        )
                    for n, artifact in enumerate(clean["artifacts"]):
                        conn.execute(
                            """INSERT INTO step_artifacts(prov_id,artifact_index,kind,root_sha256,rel_path,path_sha256,
                               lines_total,bytes_total,lines_from,lines_to,content_truncated) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                            (prov_id, n, artifact["kind"], artifact.get("root_sha256"),
                             _scalar(artifact.get("rel_path")), artifact.get("path_sha256"),
                             artifact.get("lines_total"), artifact.get("bytes_total"),
                             artifact.get("lines_from"), artifact.get("lines_to"),
                             int(bool(artifact.get("content_truncated")))),
                        )
                    previous_hash = digest
                    prov_ids.append(prov_id)
                indexes = [s["step_index"] for s in steps]
                conn.execute(
                    """INSERT INTO trajectory_chunks(trajectory_id,chunk_no,parent_prov_id,manifest_binding_id,harness,start_offset,
                       end_offset,chunk_sha256,prior_chain_sha256,chain_sha256,first_step_index,step_count,ingested_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (trajectory_id, chunk_no, parent, binding_id, harness, offset, offset + consumed,
                     chunk_sha, prior, chain,
                     min(indexes) if harness == "trajectory_json" else next_index, len(steps), ingested_at),
                )
            return 200, {
                "trajectory_id": trajectory_id,
                "chunk_no": chunk_no,
                "steps": len(prov_ids),
                "first_prov_id": prov_ids[0],
                "last_prov_id": prov_ids[-1],
                "start_offset": offset,
                "consumed_to": offset + consumed,
                "chunk_sha256": chunk_sha,
                "chain_sha256": chain,
            }
        finally:
            conn.close()

    # The v1 API is for an authenticated service producer. Its owner tuple is
    # supplied by that producer after authentication/authorization, never by an
    # unauthenticated public client. Receipt references are evidence references,
    # not a claim that this store verifies Authstructure signatures.
    def _owned_request(self, operation: str, payload: Any) -> dict:
        common = {"owner", "idempotency_key", "auth_receipt"}
        required = {
            "mint": {"atp_context"},
            "bind": {"parent_prov_id", "manifest_binding_id", *LAYER_ORDER},
            "log": {
                "prov_id",
                "parent_prov_id",
                "manifest_binding_id",
                "phase",
                "action_type",
                "target",
            },
        }[operation]
        optional = (
            {"status", "result", "payload_summary", "metadata"}
            if operation == "log"
            else set()
        )
        if (
            not isinstance(payload, dict)
            or not common | required <= payload.keys()
            or not payload.keys() <= common | required | optional
            or not valid_owner(payload.get("owner"))
            or not valid_id(payload.get("idempotency_key"))
            or not valid_auth_receipt(payload.get("auth_receipt"))
        ):
            raise ValueError("invalid_request")
        for key in ("prov_id", "parent_prov_id", "manifest_binding_id"):
            if key in payload and not valid_id(payload[key]):
                raise ValueError("invalid_request")
        if operation == "mint":
            if not isinstance(
                payload["atp_context"], str
            ) or not HASH_PATTERN.fullmatch(payload["atp_context"]):
                raise ValueError("invalid_request")
        if operation == "bind":
            if any(not isinstance(payload[layer], dict) for layer in LAYER_ORDER):
                raise ValueError("invalid_request")
            if payload["session"].get("session_id") != payload["owner"]["session_id"]:
                raise ValueError("invalid_request")
        value = sanitized(payload)
        if operation == "log":
            value.setdefault("status", "ok")
            value.setdefault("result", "accepted")
            value.setdefault("payload_summary", "")
            value.setdefault("metadata", {})
            if any(
                not valid_id(value[key])
                for key in ("phase", "action_type", "status", "result")
            ):
                raise ValueError("invalid_request")
            if (
                not isinstance(value["target"], str)
                or not 1 <= len(value["target"]) <= 256
                or any(ord(c) < 32 for c in value["target"])
                or not isinstance(value["payload_summary"], str)
                or len(value["payload_summary"]) > 512
                or not isinstance(value["metadata"], dict)
            ):
                raise ValueError("invalid_request")
        if len(canonical_json(value).encode()) > 256 * 1024:
            raise ValueError("invalid_request")
        return value

    @staticmethod
    def _owned_root(conn, parent: str, owner_json: str):
        return conn.execute(
            "SELECT * FROM agent_logs WHERE prov_id=? AND parent_prov_id IS NULL AND kind='atp_prompt' AND owner_json=?",
            (parent, owner_json),
        ).fetchone()

    def owned_mutation(self, operation: str, payload: Any) -> tuple[int, dict]:
        if operation not in {"mint", "bind", "log"}:
            return 422, {"error": "invalid_request"}
        try:
            value = self._owned_request(operation, payload)
        except (ValueError, TypeError, OverflowError):
            return 422, {"error": "invalid_request"}
        owner_json = canonical_json(value["owner"])
        # New authentication is required upstream for every attempt. A fresh
        # receipt can authorize a retry, but cannot rewrite committed evidence.
        request_json = canonical_json(
            {k: v for k, v in value.items() if k != "auth_receipt"}
        )
        conn = None
        try:
            conn = self.connect()
            with conn:
                conn.execute("BEGIN IMMEDIATE")
                prior = conn.execute(
                    "SELECT request_json,receipt_json FROM provenance_operations WHERE operation=? AND owner_json=? AND idempotency_key=?",
                    (operation, owner_json, value["idempotency_key"]),
                ).fetchone()
                if prior:
                    if prior["request_json"] != request_json:
                        return 409, {"error": "idempotency_conflict"}
                    receipt = json.loads(prior["receipt_json"])
                    if (
                        not isinstance(receipt, dict)
                        or receipt.get("owner") != value["owner"]
                        or not self._owned_replay_valid(
                            conn, operation, receipt, owner_json
                        )
                    ):
                        return 503, {"error": "provenance_unavailable"}
                    return 200, receipt
                if operation != "mint" and not self._owned_root(
                    conn, value["parent_prov_id"], owner_json
                ):
                    return 404, {"error": "not_found"}
                if operation != "mint" and not self._owned_parent_valid(
                    conn, value["parent_prov_id"], owner_json
                ):
                    return 503, {"error": "provenance_unavailable"}
                ts = now_iso()
                if operation == "mint":
                    prov_id = str(uuid.uuid4())
                    record = {
                        "kind": "atp_prompt",
                        "prov_id": prov_id,
                        "parent_prov_id": None,
                        "ts": ts,
                        "owner": value["owner"],
                        "auth_receipt": value["auth_receipt"],
                        "atp_context": value["atp_context"],
                    }
                    receipt = {
                        k: record[k]
                        for k in (
                            "prov_id",
                            "ts",
                            "owner",
                            "auth_receipt",
                            "atp_context",
                        )
                    }
                    receipt["body_sha256"] = body_hash(record)
                    self._insert_owned_log(conn, record, receipt)
                elif operation == "bind":
                    if conn.execute(
                        "SELECT 1 FROM manifest_bindings WHERE manifest_binding_id=?",
                        (value["manifest_binding_id"],),
                    ).fetchone():
                        return 409, {"error": "idempotency_conflict"}
                    refs, layers, parent_ref = {}, [], None
                    for name in LAYER_ORDER:
                        body = {**value[name], "bound_at": ts}
                        layer_hash = canonical_hash(
                            {
                                "layer": name,
                                "body": body,
                                "parent_ref": parent_ref,
                                "manifest_binding_id": value["manifest_binding_id"],
                                "owner": value["owner"],
                            }
                        )
                        conn.execute(
                            "INSERT INTO manifest_layers(layer_hash,layer_name,parent_ref,manifest_binding_id,bound_at,body_json) VALUES(?,?,?,?,?,?)",
                            (
                                layer_hash,
                                name,
                                parent_ref,
                                value["manifest_binding_id"],
                                ts,
                                canonical_json(body),
                            ),
                        )
                        refs[name + "_ref"] = layer_hash
                        layers.append(
                            {"layer": name, "layer_hash": layer_hash, "bound_at": ts}
                        )
                        parent_ref = layer_hash
                    record = {
                        "kind": "manifest_binding",
                        "parent_prov_id": value["parent_prov_id"],
                        "manifest_binding_id": value["manifest_binding_id"],
                        "owner": value["owner"],
                        "auth_receipt": value["auth_receipt"],
                        "ts": ts,
                        "refs": refs,
                        "layers": {name: value[name] for name in LAYER_ORDER},
                    }
                    receipt = {
                        "manifest_binding_id": value["manifest_binding_id"],
                        "parent_prov_id": value["parent_prov_id"],
                        "session_id": value["owner"]["session_id"],
                        "ts": ts,
                        "owner": value["owner"],
                        "auth_receipt": value["auth_receipt"],
                        "refs": refs,
                        "layers": layers,
                        "body_sha256": body_hash(record),
                    }
                    conn.execute(
                        """INSERT INTO manifest_bindings(manifest_binding_id,session_id,declaration_ref,version_ref,session_ref,route_ref,
                           created_at,updated_at,owner_json,parent_prov_id,canonical_body_json,receipt_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            value["manifest_binding_id"],
                            value["owner"]["session_id"],
                            *(refs[key] for key in REF_KEYS),
                            ts,
                            ts,
                            owner_json,
                            value["parent_prov_id"],
                            canonical_json(record),
                            canonical_json(receipt),
                        ),
                    )
                else:
                    if conn.execute(
                        "SELECT 1 FROM agent_logs WHERE prov_id=?", (value["prov_id"],)
                    ).fetchone():
                        return 409, {"error": "idempotency_conflict"}
                    binding = conn.execute(
                        "SELECT * FROM manifest_bindings WHERE manifest_binding_id=? AND owner_json=? AND parent_prov_id=?",
                        (
                            value["manifest_binding_id"],
                            owner_json,
                            value["parent_prov_id"],
                        ),
                    ).fetchone()
                    if not binding or not complete_refs(binding_refs(binding)):
                        return 404, {"error": "not_found"}
                    if not self._verify_owned_binding(conn, binding, value["owner"]):
                        return 503, {"error": "provenance_unavailable"}
                    previous = conn.execute(
                        """SELECT al.body_sha256, ar.sequence_no FROM agent_logs al JOIN action_refs ar ON ar.prov_id=al.prov_id
                           WHERE al.parent_prov_id=? AND ar.manifest_binding_id=? ORDER BY ar.sequence_no DESC LIMIT 1""",
                        (value["parent_prov_id"], value["manifest_binding_id"]),
                    ).fetchone()
                    refs = binding_refs(binding)
                    record = {k: v for k, v in value.items() if k != "idempotency_key"}
                    record.update(
                        kind="agent_action",
                        ts=ts,
                        refs=refs,
                        prev_action_hash=previous["body_sha256"] if previous else None,
                        sequence_no=previous["sequence_no"] + 1 if previous else 1,
                    )
                    receipt = {
                        k: record[k]
                        for k in (
                            "prov_id",
                            "parent_prov_id",
                            "ts",
                            "owner",
                            "auth_receipt",
                            "manifest_binding_id",
                            "refs",
                            "prev_action_hash",
                            "sequence_no",
                        )
                    }
                    receipt.update(body_sha256=body_hash(record), layers_bound=4)
                    self._insert_owned_log(conn, record, receipt)
                    conn.execute(
                        """INSERT INTO action_refs(prov_id,manifest_binding_id,declaration_ref,version_ref,session_ref,route_ref,
                           prev_action_hash,sequence_no) VALUES(?,?,?,?,?,?,?,?)""",
                        (
                            value["prov_id"],
                            value["manifest_binding_id"],
                            *(refs[key] for key in REF_KEYS),
                            record["prev_action_hash"],
                            record["sequence_no"],
                        ),
                    )
                conn.execute(
                    "INSERT INTO provenance_operations(operation,owner_json,idempotency_key,request_json,receipt_json) VALUES(?,?,?,?,?)",
                    (
                        operation,
                        owner_json,
                        value["idempotency_key"],
                        request_json,
                        canonical_json(receipt),
                    ),
                )
            return 200, receipt
        except sqlite3.IntegrityError:
            return 409, {"error": "idempotency_conflict"}
        except (sqlite3.Error, ValueError, TypeError, KeyError):
            return 503, {"error": "provenance_unavailable"}
        finally:
            if conn is not None:
                conn.close()

    @staticmethod
    def _owned_replay_valid(conn, operation, receipt, owner_json):
        """A receipt cache cannot conceal missing or corrupted committed evidence."""
        try:
            if operation == "bind":
                row = conn.execute(
                    "SELECT * FROM manifest_bindings WHERE manifest_binding_id=? AND owner_json=?",
                    (receipt["manifest_binding_id"], owner_json),
                ).fetchone()
                return (
                    row is not None
                    and json.loads(row["receipt_json"]) == receipt
                    and ProvenanceStore._owned_parent_valid(
                        conn, row["parent_prov_id"], owner_json
                    )
                    and ProvenanceStore._verify_owned_binding(
                        conn, row, receipt["owner"]
                    )
                )
            row = conn.execute(
                "SELECT * FROM agent_logs WHERE prov_id=? AND owner_json=?",
                (receipt["prov_id"], owner_json),
            ).fetchone()
            if row is None:
                return False
            record = json.loads(row["canonical_body_json"])
            if (
                not isinstance(record, dict)
                or record.get("owner") != receipt["owner"]
                or body_hash(record) != receipt["body_sha256"]
                or row["body_sha256"] != receipt["body_sha256"]
                or json.loads(row["receipt_json"]) != receipt
            ):
                return False
            keys = (
                ("prov_id", "ts", "owner", "auth_receipt", "atp_context")
                if operation == "mint"
                else (
                    "prov_id",
                    "parent_prov_id",
                    "ts",
                    "owner",
                    "auth_receipt",
                    "manifest_binding_id",
                    "refs",
                    "prev_action_hash",
                    "sequence_no",
                )
            )
            expected = {key: record[key] for key in keys}
            expected["body_sha256"] = body_hash(record)
            if operation == "log":
                expected["layers_bound"] = 4
            if (
                expected != receipt
                or not ProvenanceStore._owned_projection_valid(row, record)
                or record.get("kind")
                != ("atp_prompt" if operation == "mint" else "agent_action")
            ):
                return False
            if operation == "mint":
                return record.get("parent_prov_id") is None
            if not ProvenanceStore._owned_parent_valid(
                conn, row["parent_prov_id"], owner_json
            ):
                return False
            refs = conn.execute(
                "SELECT * FROM action_refs WHERE prov_id=?", (row["prov_id"],)
            ).fetchone()
            if (
                refs is None
                or record.get("refs") != binding_refs(refs)
                or record.get("manifest_binding_id") != refs["manifest_binding_id"]
                or record.get("sequence_no") != refs["sequence_no"]
                or record.get("prev_action_hash") != refs["prev_action_hash"]
            ):
                return False
            binding = conn.execute(
                "SELECT * FROM manifest_bindings WHERE manifest_binding_id=? AND owner_json=? AND parent_prov_id=?",
                (refs["manifest_binding_id"], owner_json, row["parent_prov_id"]),
            ).fetchone()
            return (
                binding is not None
                and binding_refs(binding) == binding_refs(refs)
                and ProvenanceStore._verify_owned_binding(
                    conn, binding, receipt["owner"]
                )
            )
        except (ValueError, TypeError, KeyError):
            return False

    @staticmethod
    def _owned_parent_valid(conn, parent, owner_json):
        root = ProvenanceStore._owned_root(conn, parent, owner_json)
        if root is None:
            return False
        try:
            receipt = json.loads(root["receipt_json"])
            return isinstance(receipt, dict) and ProvenanceStore._owned_replay_valid(
                conn, "mint", receipt, owner_json
            )
        except (ValueError, TypeError):
            return False

    @staticmethod
    def _owned_projection_valid(row, record):
        try:
            return (
                all(
                    record.get(key) == row[key]
                    for key in ("prov_id", "parent_prov_id", "ts", "kind")
                )
                and row["owner_json"] == canonical_json(record["owner"])
                and row["agent_id"] == record["owner"]["principal_id"]
                and row["actor"] == record["owner"]["principal_id"]
                and json.loads(row["input_json"]) == record.get("metadata", {})
                and row["payload_summary"]
                == record.get("payload_summary", record.get("atp_context", ""))
                and all(
                    row[key] == record.get(key, default)
                    for key, default in (
                        ("phase", "atp_prompt"),
                        ("action_type", None),
                        ("target", None),
                        ("status", "ok"),
                        ("result", "accepted"),
                    )
                )
                and all(
                    row[key] is None
                    for key in (
                        "model",
                        "output_json",
                        "error",
                        "latency_ms",
                        "tags_json",
                    )
                )
            )
        except (ValueError, TypeError, KeyError):
            return False

    @staticmethod
    def _insert_owned_log(conn, record: dict, receipt: dict) -> None:
        conn.execute(
            """INSERT INTO agent_logs(prov_id,parent_prov_id,ts,agent_id,actor,kind,phase,action_type,target,result,status,
               input_json,payload_summary,body_sha256,canonical_body_json,owner_json,receipt_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                record["prov_id"],
                record["parent_prov_id"],
                record["ts"],
                record["owner"]["principal_id"],
                record["owner"]["principal_id"],
                record["kind"],
                record.get("phase", "atp_prompt"),
                record.get("action_type"),
                record.get("target"),
                record.get("result", "accepted"),
                record.get("status", "ok"),
                canonical_json(record.get("metadata", {})),
                record.get("payload_summary", record.get("atp_context", "")),
                receipt["body_sha256"],
                canonical_json(record),
                canonical_json(record["owner"]),
                canonical_json(receipt),
            ),
        )

    def owned_chain(
        self, parent: str, owner: dict, *, limit: int = 100, offset: int = 0
    ) -> tuple[int, dict]:
        if (
            not valid_id(parent)
            or not valid_owner(owner)
            or type(limit) is not int
            or not 1 <= limit <= 100
            or type(offset) is not int
            or offset < 0
        ):
            return 422, {"error": "invalid_request"}
        conn = None
        try:
            conn = self.connect(readonly=True)
            conn.execute("BEGIN")
            owner_json = canonical_json(owner)
            if not self._owned_root(conn, parent, owner_json):
                return 404, {"error": "not_found"}
            total = conn.execute(
                "SELECT COUNT(*) FROM agent_logs WHERE (prov_id=? OR parent_prov_id=?) AND owner_json=?",
                (parent, parent, owner_json),
            ).fetchone()[0]
            rows = conn.execute(
                """SELECT kind,receipt_json FROM agent_logs WHERE (prov_id=? OR parent_prov_id=?) AND owner_json=?
                   ORDER BY CASE WHEN parent_prov_id IS NULL THEN 0 ELSE 1 END,rowid LIMIT ? OFFSET ?""",
                (parent, parent, owner_json, limit, offset),
            ).fetchall()
            entries = []
            for row in rows:
                receipt = json.loads(row["receipt_json"])
                operation = "mint" if row["kind"] == "atp_prompt" else "log"
                if (
                    not isinstance(receipt, dict)
                    or receipt.get("owner") != owner
                    or not self._owned_replay_valid(
                        conn, operation, receipt, owner_json
                    )
                ):
                    return 503, {"error": "provenance_unavailable"}
                entries.append(
                    {
                        "kind": "root" if row["kind"] == "atp_prompt" else "action",
                        **receipt,
                    }
                )
            return 200, {
                "parent_prov_id": parent,
                "owner": owner,
                "entries": entries,
                "total": total,
                "next_offset": offset + len(entries)
                if offset + len(entries) < total
                else None,
            }
        except (sqlite3.Error, ValueError, TypeError):
            return 503, {"error": "provenance_unavailable"}
        finally:
            if conn is not None:
                conn.close()

    def owned_verify(self, parent: str, owner: dict) -> tuple[int, dict]:
        if not valid_id(parent) or not valid_owner(owner):
            return 422, {"error": "invalid_request"}
        conn = None
        try:
            conn = self.connect(readonly=True)
            conn.execute("BEGIN")
            owner_json = canonical_json(owner)
            if not self._owned_root(conn, parent, owner_json):
                return 404, {"error": "not_found"}
            rows = conn.execute(
                """SELECT al.*,ar.manifest_binding_id,ar.declaration_ref,ar.version_ref,ar.session_ref,ar.route_ref,
                          ar.prev_action_hash,ar.sequence_no FROM agent_logs al LEFT JOIN action_refs ar ON ar.prov_id=al.prov_id
                   WHERE al.prov_id=? OR al.parent_prov_id=?
                   ORDER BY CASE WHEN al.parent_prov_id IS NULL THEN 0 ELSE 1 END,ar.manifest_binding_id,ar.sequence_no,al.rowid""",
                (parent, parent),
            ).fetchall()
            problems, heads, bindings = [], {}, set()
            recomputed = 0

            def problem(code, prov_id=None):
                if len(problems) < 100:
                    problems.append(
                        {
                            "code": code,
                            "prov_id": prov_id if valid_id(prov_id) else None,
                        }
                    )

            for binding in conn.execute(
                "SELECT * FROM manifest_bindings WHERE parent_prov_id=?", (parent,)
            ):
                if binding["owner_json"] != owner_json:
                    problem("owner_mismatch")
                else:
                    if valid_id(binding["manifest_binding_id"]):
                        bindings.add(binding["manifest_binding_id"])
                    else:
                        problem("invalid_manifest_binding")
                    if not self._verify_owned_binding(conn, binding, owner):
                        problem("invalid_manifest_binding")
            for row in rows:
                if row["owner_json"] != owner_json:
                    problem("owner_mismatch")
                    continue
                record = None
                try:
                    record = json.loads(row["canonical_body_json"])
                    if not isinstance(record, dict):
                        raise ValueError()
                    recomputed += 1
                    if body_hash(record) != row["body_sha256"]:
                        problem("body_hash_mismatch", row["prov_id"])
                    for key in ("prov_id", "parent_prov_id", "ts", "kind"):
                        if record.get(key) != row[key]:
                            problem("record_projection_mismatch", row["prov_id"])
                    if (
                        record.get("owner") != owner
                        or row["agent_id"] != owner["principal_id"]
                        or row["actor"] != owner["principal_id"]
                    ):
                        problem("owner_mismatch")
                    expected_receipt = {
                        k: record[k]
                        for k in (
                            ("prov_id", "ts", "owner", "auth_receipt", "atp_context")
                            if row["parent_prov_id"] is None
                            else (
                                "prov_id",
                                "parent_prov_id",
                                "ts",
                                "owner",
                                "auth_receipt",
                                "manifest_binding_id",
                                "refs",
                                "prev_action_hash",
                                "sequence_no",
                            )
                        )
                    }
                    expected_receipt["body_sha256"] = row["body_sha256"]
                    if row["parent_prov_id"] is not None:
                        expected_receipt["layers_bound"] = 4
                    if json.loads(row["receipt_json"]) != expected_receipt:
                        problem("receipt_mismatch", row["prov_id"])
                    if not self._owned_projection_valid(row, record):
                        problem("record_projection_mismatch", row["prov_id"])
                except (ValueError, TypeError, KeyError):
                    problem("invalid_canonical_body", row["prov_id"])
                    record = None
                if row["parent_prov_id"] is None:
                    continue
                binding_id = row["manifest_binding_id"]
                if valid_id(binding_id):
                    bindings.add(binding_id)
                previous_hash, previous_seq = heads.get(binding_id, (None, 0))
                if row["sequence_no"] != previous_seq + 1:
                    problem("sequence_gap", row["prov_id"])
                if row["prev_action_hash"] != previous_hash:
                    problem("broken_link", row["prov_id"])
                heads[binding_id] = (row["body_sha256"], previous_seq + 1)
                refs = binding_refs(row)
                binding = conn.execute(
                    "SELECT * FROM manifest_bindings WHERE manifest_binding_id=? AND owner_json=? AND parent_prov_id=?",
                    (binding_id, owner_json, parent),
                ).fetchone()
                if (
                    not binding
                    or refs != binding_refs(binding)
                    or not complete_refs(refs)
                    or not record
                    or record.get("refs") != refs
                    or record.get("manifest_binding_id") != binding_id
                    or record.get("prev_action_hash") != row["prev_action_hash"]
                    or record.get("sequence_no") != row["sequence_no"]
                ) or not self._verify_owned_binding(conn, binding, owner):
                    problem("invalid_manifest_binding", row["prov_id"])
            return 200, {
                "parent_prov_id": parent,
                "owner": owner,
                "verified": not problems,
                "root_present": True,
                "action_count": sum(row["parent_prov_id"] is not None for row in rows),
                "bindings": sorted(bindings),
                "checks": [
                    "body_sha256 recomputation",
                    "stored projection consistency",
                    "immutable receipt consistency",
                    "owner and root binding",
                    "manifest layer hashes",
                    "prev_action_hash linkage",
                    "sequence_no continuity",
                ],
                "not_checked": [
                    "Authstructure authentication receipt signature or current credential lifecycle"
                ],
                "problems": problems,
                "coverage": {
                    "owned_records": sum(
                        row["owner_json"] == owner_json for row in rows
                    ),
                    "body_recomputed_records": recomputed,
                    "legacy_records": sum(row["owner_json"] is None for row in rows),
                },
            }
        except (sqlite3.Error, ValueError, TypeError):
            return 503, {"error": "provenance_unavailable"}
        finally:
            if conn is not None:
                conn.close()

    @staticmethod
    def _verify_owned_binding(conn, binding, owner):
        try:
            record = json.loads(binding["canonical_body_json"])
            receipt = json.loads(binding["receipt_json"])
            refs = binding_refs(binding)
            if (
                not isinstance(record, dict)
                or not isinstance(receipt, dict)
                or record.get("owner") != owner
                or record.get("parent_prov_id") != binding["parent_prov_id"]
                or record.get("manifest_binding_id") != binding["manifest_binding_id"]
                or record.get("refs") != refs
                or body_hash(record) != receipt.get("body_sha256")
            ):
                return False
            previous = None
            layers = []
            for name in LAYER_ORDER:
                layer = conn.execute(
                    "SELECT * FROM manifest_layers WHERE layer_hash=?",
                    (refs[name + "_ref"],),
                ).fetchone()
                if (
                    not layer
                    or layer["manifest_binding_id"] != binding["manifest_binding_id"]
                    or layer["layer_name"] != name
                    or layer["parent_ref"] != previous
                ):
                    return False
                body = json.loads(layer["body_json"])
                if (
                    body != {**record["layers"][name], "bound_at": record["ts"]}
                    or layer["bound_at"] != record["ts"]
                ):
                    return False
                expected = canonical_hash(
                    {
                        "layer": name,
                        "body": body,
                        "parent_ref": previous,
                        "manifest_binding_id": binding["manifest_binding_id"],
                        "owner": owner,
                    }
                )
                if expected != layer["layer_hash"]:
                    return False
                layers.append(
                    {
                        "layer": name,
                        "layer_hash": expected,
                        "bound_at": layer["bound_at"],
                    }
                )
                previous = expected
            expected_receipt = {
                "manifest_binding_id": binding["manifest_binding_id"],
                "parent_prov_id": binding["parent_prov_id"],
                "session_id": owner["session_id"],
                "ts": record["ts"],
                "owner": owner,
                "auth_receipt": record["auth_receipt"],
                "refs": refs,
                "layers": layers,
                "body_sha256": body_hash(record),
            }
            return (
                receipt == expected_receipt
                and binding["session_id"] == owner["session_id"]
            )
        except (ValueError, TypeError, KeyError):
            return False
