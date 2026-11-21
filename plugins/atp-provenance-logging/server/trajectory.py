"""Harness transcript normalizers for step-level provenance capture.

Prove ingests the harness's own record of a session (a transcript chunk)
instead of a summary the agent chose to write. Each normalizer turns raw
harness records into bounded, secret-free step dicts:

- raw content, thinking and large tool arguments become sha256 digests
- absolute paths become a workspace-relative path plus a digest of the root,
  or a bare digest when the path lies outside the workspace
- every value is bounded so the result passes ``provenance_core.sanitized``

Supported harness formats:

``claude_code_jsonl``
    Claude Code session transcripts (one JSON record per line).
``trajectory_json``
    Concatenated step objects (``step_index``, ``source``, ``type``,
    ``status``, ``created_at``, ``content``, ``thinking``, ``tool_calls``,
    ``truncated_fields``), not necessarily newline-delimited.

Stdlib only.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime
from typing import Any, Iterator

HARNESSES = ("claude_code_jsonl", "trajectory_json")

MAX_STRING = 512
MAX_LIST = 50
MAX_KEYS = 50
MAX_DEPTH = 2
CONTENT_KEYS = {
    "content", "message", "body", "text", "new_string", "old_string", "prompt",
    # NotebookEdit cell source and the text-editor tool's file content.
    "new_source", "file_text", "new_str", "old_str",
}

_TIMING = re.compile(r"^Created At: (\S+)\nCompleted At: (\S+)", re.M)
_FILE_PATH = re.compile(r"^File Path: `?file://([^`\n]+)`?", re.M)
_LINES_TOTAL = re.compile(r"Total Lines: (\d+)")
_BYTES_TOTAL = re.compile(r"Total Bytes: (\d+)")
_LINES_SHOWN = re.compile(r"Showing lines (\d+) to (\d+)")
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def sha256(value: Any) -> str:
    if isinstance(value, bytes):
        data = value
    elif isinstance(value, str):
        data = value.encode("utf-8")
    else:
        data = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def digest(value: Any) -> dict:
    text = value if isinstance(value, str) else json.dumps(value, sort_keys=True)
    return {"sha256": sha256(text), "bytes": len(text.encode("utf-8"))}


def path_ref(path: str, root: str | None) -> dict:
    """Never return the raw absolute path: it carries user and machine names."""
    path = path.strip().strip('"')
    if path.startswith("file://"):
        path = path[len("file://"):]
    root = (root or "").rstrip("/")
    if root and (path == root or path.startswith(root + "/")):
        rel = path[len(root):].lstrip("/") or "."
        return {"root_sha256": sha256(root), "rel_path": bounded_str(rel)}
    return {"path_sha256": sha256(path)}


def looks_like_path(value: str) -> bool:
    return value.startswith("/") or value.startswith("file://") or bool(
        re.match(r"^[A-Za-z]:[\\/]", value)
    )


def bounded_str(value: str) -> Any:
    if len(value) > MAX_STRING or _CONTROL.search(value):
        return digest(value)
    return value


def bounded(value: Any, root: str | None = None, key: str = "", depth: int = 0) -> Any:
    """Shrink arbitrary tool arguments into a storable, hash-stable shape."""
    if key.lower() in CONTENT_KEYS and value is not None:
        return digest(value)  # any type: decoded JSON content is still content
    if isinstance(value, str):
        if looks_like_path(value) and "\n" not in value:
            return path_ref(value, root)
        return bounded_str(value)
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value if abs(value) < 2**53 else str(value)
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if depth >= MAX_DEPTH:
        return digest(value)
    if isinstance(value, list):
        if len(value) > MAX_LIST:
            return digest(value)
        return [bounded(item, root, key, depth + 1) for item in value]
    if isinstance(value, dict):
        if len(value) > MAX_KEYS or any(
            not isinstance(k, str) or len(k) > 128 or _CONTROL.search(k) for k in value
        ):
            return digest(value)
        return {k: bounded(v, root, k, depth + 1) for k, v in value.items()}
    return digest(str(value))


def _decode_arg(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def _ms(start: str | None, end: str | None) -> int | None:
    try:
        delta = datetime.fromisoformat(end.replace("Z", "+00:00")) - datetime.fromisoformat(
            start.replace("Z", "+00:00")
        )
        return int(delta.total_seconds() * 1000)
    except (AttributeError, TypeError, ValueError):
        return None


def _tool_call(
    index: int, name: Any, args: Any, root: str | None, tool_use_id: Any = None, decode: bool = True
) -> dict:
    """``decode``: arguments may arrive JSON-encoded as strings (trajectory_json).

    Claude's tool ``input`` is already decoded, so its values are recorded
    as they are: a Bash command of ``"false"`` stays that string.
    """
    args = args if isinstance(args, dict) else {"value": args}

    def arg(key: str, value: Any) -> Any:
        if not decode:
            return value
        plain = _decode_arg(value)
        # Content is digested as text: a JSON-encoded string decodes to its
        # text (so it hashes like the same Claude call), but JSON file
        # content is not turned into an object.
        if key.lower() in CONTENT_KEYS and not isinstance(plain, str):
            return value
        return plain

    decoded = {str(k): arg(str(k), v) for k, v in args.items()}
    call = {
        "call_index": index,
        "tool_name": bounded_str(str(name or "unknown")),
        "args": bounded(decoded, root),
        "args_sha256": sha256(decoded),
    }
    if tool_use_id:
        call["tool_use_id"] = bounded_str(str(tool_use_id))
    return call


def _base_step(**fields) -> dict:
    step = {
        "step_index": None,
        "source": None,
        "step_type": None,
        "status": None,
        "created_at": None,
        "started_at": None,
        "completed_at": None,
        "duration_ms": None,
        "content_sha256": None,
        "content_bytes": 0,
        "thinking_present": False,
        "thinking_sha256": None,
        "truncated_fields": [],
        "tool_use_id": None,
        "tool_calls": [],
        "artifacts": [],
    }
    step.update(fields)
    return step


# ── record splitting ─────────────────────────────────────────────────────────
def split_records(harness: str, chunk: bytes) -> tuple[list[tuple[int, Any]], int]:
    """Return ([(byte_offset_in_chunk, record)], consumed_bytes).

    Only complete records are consumed; a trailing partial record stays
    unconsumed so the producer resends it with the next chunk.
    """
    if harness == "claude_code_jsonl":
        records, position = [], 0
        while True:
            end = chunk.find(b"\n", position)
            if end < 0:
                break
            line = chunk[position:end].strip()
            if line:
                records.append((position, json.loads(line.decode("utf-8"))))
            position = end + 1
        return records, position
    if harness == "trajectory_json":
        text = chunk.decode("utf-8")
        decoder, index, records, consumed_chars = json.JSONDecoder(), 0, [], 0
        while True:
            while index < len(text) and text[index].isspace():
                index += 1
            if index >= len(text):
                consumed_chars = index if records else 0
                break
            try:
                record, end = decoder.raw_decode(text, index)
            except json.JSONDecodeError:
                if records:
                    consumed_chars = index  # keep whitespace after the last record
                break  # partial trailing object: leave it for the next chunk
            records.append((len(text[:index].encode("utf-8")), record))
            index = consumed_chars = end
        return records, len(text[:consumed_chars].encode("utf-8"))
    raise ValueError("unsupported harness")


# ── normalizers ──────────────────────────────────────────────────────────────
def normalize_trajectory_record(record: dict, root: str | None) -> dict:
    if not isinstance(record, dict) or not isinstance(record.get("step_index"), int):
        raise ValueError("trajectory record requires an integer step_index")
    content = record.get("content") if isinstance(record.get("content"), str) else ""
    timing = _TIMING.search(content)
    thinking = record.get("thinking") if isinstance(record.get("thinking"), str) else ""
    truncated = record.get("truncated_fields") or []
    step = _base_step(
        step_index=record["step_index"],
        source=bounded_str(str(record.get("source") or "").lower()),
        step_type=bounded_str(str(record.get("type") or "generic").lower()),
        status=bounded_str(str(record.get("status") or "").lower()),
        created_at=bounded_str(str(record.get("created_at") or "")) or None,
        started_at=timing.group(1) if timing else None,
        completed_at=timing.group(2) if timing else None,
        duration_ms=_ms(timing.group(1), timing.group(2)) if timing else None,
        content_sha256=sha256(content) if content else None,
        content_bytes=len(content.encode("utf-8")),
        thinking_present=bool(thinking),
        thinking_sha256=sha256(thinking) if thinking else None,
        truncated_fields=[bounded_str(str(f)) for f in truncated[:MAX_LIST]]
        if isinstance(truncated, list)
        else [],
    )
    for n, call in enumerate((record.get("tool_calls") or [])[:MAX_LIST]):
        if isinstance(call, dict):
            step["tool_calls"].append(_tool_call(n, call.get("name"), call.get("args"), root))
    found = _FILE_PATH.search(content)
    if found:
        shown = _LINES_SHOWN.search(content)
        lines, size = _LINES_TOTAL.search(content), _BYTES_TOTAL.search(content)
        step["artifacts"].append(
            {
                "kind": "file_read",
                **path_ref(found.group(1), root),
                "lines_total": int(lines.group(1)) if lines else None,
                "bytes_total": int(size.group(1)) if size else None,
                "lines_from": int(shown.group(1)) if shown else None,
                "lines_to": int(shown.group(2)) if shown else None,
                "content_truncated": "content" in step["truncated_fields"],
            }
        )
    return step


def _claude_blocks(message: Any) -> list:
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    return [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []


def normalize_claude_record(record: dict, root: str | None, step_index: int) -> dict:
    if not isinstance(record, dict):
        raise ValueError("claude record must be an object")
    kind = str(record.get("type") or "generic")
    message = record.get("message") if isinstance(record.get("message"), dict) else {}
    blocks = _claude_blocks(message)
    root = record.get("cwd") if isinstance(record.get("cwd"), str) else root
    texts = [b.get("text", "") for b in blocks if b.get("type") == "text"]
    thinking = [b.get("thinking", "") for b in blocks if b.get("type") == "thinking"]
    tool_uses = [b for b in blocks if b.get("type") == "tool_use"]
    results = [b for b in blocks if b.get("type") == "tool_result"]
    content = canonical = json.dumps(
        {"text": texts, "tool_results": [r.get("content") for r in results]}, sort_keys=True
    ) if (texts or results) else ""
    if kind == "assistant":
        step_type = "planner_response"
        source = "model"
    elif kind == "user" and results:
        step_type = "tool_result"
        source = "system"
    elif kind == "user":
        step_type = "user_input"
        source = "user_explicit"
    elif kind == "summary":
        step_type = "checkpoint"
        source = "system"
    else:
        step_type = bounded_str(kind.lower())
        source = "system"
    status = "error" if any(r.get("is_error") for r in results) else "done"
    step = _base_step(
        step_index=step_index,
        source=source,
        step_type=step_type,
        status=status,
        created_at=bounded_str(str(record.get("timestamp") or "")) or None,
        content_sha256=sha256(canonical) if content else None,
        content_bytes=len(content.encode("utf-8")),
        thinking_present=bool(thinking),
        thinking_sha256=sha256("".join(thinking)) if thinking else None,
    )
    if results and isinstance(results[0].get("tool_use_id"), str):
        step["tool_use_id"] = bounded_str(results[0]["tool_use_id"])
    for n, use in enumerate(tool_uses[:MAX_LIST]):
        step["tool_calls"].append(
            _tool_call(n, use.get("name"), use.get("input"), root, use.get("id"), decode=False)
        )
        args = use.get("input") if isinstance(use.get("input"), dict) else {}
        target = args.get("file_path") or args.get("path") or args.get("notebook_path")
        if isinstance(target, str) and looks_like_path(target):
            name = str(use.get("name") or "").lower()
            kind_ = "file_write" if name in {"write", "edit", "multiedit", "notebookedit"} else (
                "dir_list" if name in {"ls", "glob"} else "file_read"
            )
            step["artifacts"].append({"kind": kind_, **path_ref(target, root)})
    for key in ("isSidechain", "agentId", "uuid", "parentUuid"):
        if record.get(key) is not None:
            step.setdefault("harness_refs", {})[key] = bounded(record[key])
    return step


def normalize(harness: str, records: list[tuple[int, Any]], root: str | None, next_index: int) -> list[dict]:
    """Normalize split records; ``source_offset`` is relative to the chunk."""
    steps = []
    for n, (offset, record) in enumerate(records):
        if harness == "claude_code_jsonl":
            step = normalize_claude_record(record, root, next_index + n)
        else:
            step = normalize_trajectory_record(record, root)
        step["source_offset"] = offset
        steps.append(step)
    return steps


def oversized_step(step_index: int, size: int, sha256_hex: str) -> dict:
    """A record too large to send: kept as its position, length and digest."""
    step = _base_step(
        step_index=step_index,
        source="system",
        step_type="oversized_record",
        status="omitted",
        content_sha256=sha256_hex,
        content_bytes=size,
        truncated_fields=["record"],
    )
    step["source_offset"] = 0
    return step


def describe(step: dict) -> str:
    """A content-free one-line summary for the legacy payload_summary column."""
    calls = [c["tool_name"] for c in step["tool_calls"] if isinstance(c["tool_name"], str)]
    parts = [str(step["step_type"])]
    if calls:
        parts.append(f"{len(calls)} tool call(s): {', '.join(calls[:5])}")
    for artifact in step["artifacts"][:1]:
        if artifact.get("rel_path"):
            parts.append(str(artifact["rel_path"]))
    if step["truncated_fields"]:
        parts.append("truncated")
    return " · ".join(parts)[:280]


def iter_file_chunks(path: str, offset: int, budget: int) -> Iterator[bytes]:
    """Yield newline-terminated chunks of a transcript from ``offset`` (producer side)."""
    with open(path, "rb") as handle:
        handle.seek(offset)
        while True:
            data = handle.read(budget)
            if not data:
                return
            cut = data.rfind(b"\n")
            if cut < 0:
                return  # a single record larger than the budget; caller reports it
            chunk = data[: cut + 1]
            handle.seek(offset + len(chunk))
            offset += len(chunk)
            yield chunk


def chain_of(path: str, end_offsets: list[int]) -> list[dict]:
    """Recompute Prove's chunk chain from the producer's own transcript copy.

    ``end_offsets`` are the ``consumed_to`` values from Prove's receipts (or
    ``trajectory_chunks.end_offset``). Compare the output with the ledger.
    """
    out, prior, start = [], None, 0
    with open(path, "rb") as handle:
        data = handle.read()
    for end in end_offsets:
        chunk_sha = sha256(data[start:end])
        chain = sha256((prior or "") + chunk_sha)
        out.append({"start_offset": start, "end_offset": end, "chunk_sha256": chunk_sha, "chain_sha256": chain})
        prior, start = chain, end
    return out


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Prove transcript tools")
    sub = parser.add_subparsers(dest="command", required=True)
    norm = sub.add_parser("normalize", help="print normalized steps for a transcript file")
    norm.add_argument("harness", choices=HARNESSES)
    norm.add_argument("path")
    norm.add_argument("--workspace-root")
    chain = sub.add_parser("chain", help="recompute chunk chain hashes for audit")
    chain.add_argument("path")
    chain.add_argument("end_offsets", help="comma-separated consumed_to offsets")
    args = parser.parse_args(argv)
    if args.command == "chain":
        offsets = [int(x) for x in args.end_offsets.split(",") if x]
        for row in chain_of(args.path, offsets):
            print(json.dumps(row, sort_keys=True))
        return 0
    with open(args.path, "rb") as handle:
        records, consumed = split_records(args.harness, handle.read())
    for step in normalize(args.harness, records, args.workspace_root, 0):
        print(json.dumps(step, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
