# Source of server/ and ui/

Synced from the Prove repository, branch
`fix/local-origin-guard-and-content-digests` at commit `6da6ac5`
(QH-Agentic-OS/prove#12, draft). Fixes found in review here are made in Prove
first and copied back, so the two copies do not drift.

Identical to Prove: `atp_hooks.py`, `hosted_service.py`, `provenance_core.py`,
`provenance_http.py`, `provenance_schema.py`, `provenance_service.py`,
`trajectory.py`, `ui/app.css`.

Different on purpose, for this public build:

| File | Difference |
|---|---|
| `manifest.py` | Emitters are the plugin's own; routing memory and private-stack names are removed. |
| `ui/app.js` | Simulation agent profiles and sample paths use generic names. Everything else matches Prove. |

The plugin's own local server (`scripts/prove_local.py`) subclasses
`provenance_service.Handler` and is stricter than Prove's local service: it
serves the dashboard itself, so it allows only its own origin.
