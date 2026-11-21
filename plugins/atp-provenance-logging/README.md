# ATP Provenance Logging (Prove)

A Claude Code plugin that makes agent work traceable. Every step of a session
is recorded as a hash-chained child of one root, so you can see what an agent
read, ran and wrote, and prove that nothing in the record was changed or left
out.

```
/plugin marketplace add QH-Agentic-OS/QuantumHarmony_LLC
/plugin install atp-provenance-logging@quantum-harmony-marketplace
```

Needs Python 3.11 or newer on your PATH as `python3`. No packages to install.

## What's in it

| Part | What it does |
|---|---|
| **Hooks** (`hooks/hooks.json`) | On session start, each prompt, each tool call, stop and sub-agent stop, forward the new part of the session transcript to Prove (`POST /ingest/trajectory`). Prove, not the agent, decides what gets recorded. At session end the workspace's capture receipt is dropped. |
| **Skill** (`skills/atp-provenance-logging`) | The ATP contract: one root `prov_id` per session, an `atp_prompt` and an `atp_response` marker for each ATP prompt under it, the root in the ATP header, halt-and-alert if any write fails. |
| **Prove service** (`server/`) | Stdlib-only Python + SQLite. Manifest binding (declaration → version → session → route), `prev_action_hash` chaining, redaction, `/verify`. `hosted_service.py` is the single-port, token-protected variant for your own deployment. |
| **Mission Control** (`ui/`) | The dashboard: live chain, walk-back, import, simulate. Network-free: React 18.3.1 is vendored, CSS is precompiled, no CDN, no eval. |
| **Scripts** (`scripts/`) | `prove_local.py` runs Prove on your machine, `prove_log.py` writes ATP roots and steps from any agent or script, `build_offline.py` builds the single-file dashboard. |

## Three ways to run it

Pick one in the plugin's settings (`/plugin` → atp-provenance-logging → configure).

| | **standalone** (default) | **offline** | **hosted** |
|---|---|---|---|
| Where Prove runs | This machine, `127.0.0.1:8787`, started by the hooks | This machine, same as standalone | Your own deployment (Render, Railway or any Python host with a disk) |
| Ledger | `~/.prove/provenance.db` (or `ledger_path`) | Same | On the host's persistent disk |
| Network | Loopback by default; `service_url` may point at another Prove you run | **Nothing leaves the machine**: non-loopback URLs are refused, no token is ever sent, the dashboard has no network dependency | HTTPS to your service, bearer token |
| Dashboard | `http://127.0.0.1:8787/` | `http://127.0.0.1:8787/`, or `ui/prove-offline.html` opened from disk with no server | Your service URL (user `prove`, password = the token) |
| Needs | Python 3.11+ | Python 3.11+ (nothing for the single-file dashboard) | `service_url` + `api_token` |

All three use the same service code and ledger schema, so an export from one
imports into the others.

### Standalone and offline

Nothing to set up. The first session starts Prove and creates the ledger.
To run it yourself, inside or outside Claude Code:

```bash
python3 scripts/prove_local.py start     # background; also: serve (foreground), stop, status
python3 scripts/prove_local.py export <root prov_id> > run.json
```

`prove_local.py` binds `127.0.0.1` and refuses any other address unless you
pass `--allow-remote`, because the local service has no authentication.

**Single-file dashboard.** `ui/prove-offline.html` holds React, the app and
the CSS in one file. Copy it anywhere (a USB stick, an air-gapped machine) and
open it from disk to **Import JSON** an export or run **Simulate**. Live mode
needs the service. Rebuild it after syncing the UI with
`python3 scripts/build_offline.py`.

### Hosted

Point the plugin at a Prove you deploy. `server/hosted_service.py` serves the
dashboard and the API on one port behind one access token:

```bash
python3 scripts/prove_local.py init --db /data/provenance.db   # once, on the persistent disk
PROV_DB=/data/provenance.db PORT=10000 python3 server/hosted_service.py
```

It generates a token on first start and keeps it next to the ledger
(`provenance-access-token`, mode 600), or uses `PROV_API_TOKEN` if set. Put
that token in the plugin's `api_token` setting and the https URL in
`service_url`. A ledger from an older Prove is refused until you upgrade it:
`python3 scripts/prove_local.py upgrade --db <ledger> --backup <new backup path>`.

A static host such as Netlify can serve `ui/` for import and simulate, but it
cannot run the service, so live capture needs a Python host.

## The ATP flow

Inside Claude Code the hooks mint one root per session and record every step
under it. The skill adds an `atp_prompt` and an `atp_response` marker to that
same root, so one export holds the whole session:

```bash
ID=$(python3 scripts/prove_log.py begin --context "ATP: refactor auth")
python3 scripts/prove_log.py end "$ID" --summary "done, tests green"
python3 scripts/prove_log.py verify "$ID"
```

Entries an agent writes itself are stamped `self_reported`.
`POST /capture/policy` can make a binding refuse them, so only
harness-captured steps count.

## Settings

| Setting | Default | |
|---|---|---|
| `mode` | `standalone` | `standalone`, `offline` or `hosted` |
| `service_url` | empty | hosted: required (https). standalone: optional. offline: loopback only |
| `api_token` | empty | hosted only; kept in your system's credential store |
| `ledger_path` | `~/.prove/provenance.db` | local ledger file |
| `capture` | on | forward session transcripts |
| `autostart` | on | start the local service at session start |
| `strict` | off | refuse prompts while Prove is unreachable (otherwise warn and continue) |

## What gets recorded

See [PRIVACY.md](PRIVACY.md). In short: each transcript record becomes a step
with its type, timing, tool name, bounded and redacted arguments, workspace
relative file paths, and digests of content and thinking. Prove does not keep
the raw transcript. Data goes only to the Prove you chose; by default that is
this machine.

## Development

```bash
python3 -m unittest discover -s plugins/atp-provenance-logging/tests -v
```

`server/` and `ui/app.js` / `ui/app.css` are synced from the Prove repository;
[server/SOURCE.md](server/SOURCE.md) lists the source commit and every change
made for this public build.

License: Apache-2.0. React is MIT (`ui/vendor/LICENSE-react.txt`).
Pairs with `artemis-transmission-protocol`.
