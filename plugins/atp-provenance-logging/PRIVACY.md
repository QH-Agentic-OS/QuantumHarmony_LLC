# ATP Provenance Logging privacy policy

Last updated: November 21, 2026. Published by Quantum Harmony LLC.

This policy covers the ATP Provenance Logging plugin (Prove). Quantum Harmony
LLC runs no service that receives data from this plugin. Everything it records
goes to the Prove service that you choose in the plugin's settings.

## Where data goes

- **standalone** (default) and **offline**: to the Prove service bundled with
  the plugin, running on your own computer at `127.0.0.1`. Offline mode refuses
  any address that is not on your computer.
- **standalone with a `service_url`**: to the Prove instance at that address,
  which you run.
- **hosted**: to the Prove deployment at the https `service_url` you enter,
  authenticated with the `api_token` you enter. That deployment is yours, on a
  host you choose, under that host's own terms and privacy policy.

The dashboard loads nothing from the internet: its scripts and styles are
bundled with the plugin.

## What the hooks send

When `capture` is on, at session start and after each prompt, tool call, stop
and sub-agent stop, the hooks send the part of the Claude Code session
transcript that Prove has not yet received, together with the session id, the
workspace path and the model id. Before anything leaves the hook, values that
look like API keys or bearer tokens are overwritten with `*` characters of the
same length, so the hosted or local service never receives them.

## What Prove stores

Prove parses each transcript record into a step and stores:

- the step's type, status and timestamps;
- tool names and tool arguments, cut to a bounded length, with secret-named
  keys redacted, plus a sha256 of the full arguments;
- file paths relative to the workspace (or a digest), line and byte counts;
- sha256 digests and byte counts, not the text, of message content and
  thinking;
- the hash chain that makes the record tamper-evident.

Prove does not keep the raw transcript. Entries an agent writes itself with
`prove_log.py` or `POST /log` are stored as sent, after redaction.

## Where it is kept, and for how long

In the SQLite ledger of the Prove you chose: by default
`~/.prove/provenance.db` on your computer. Prove never deletes ledger entries;
the ledger is kept until you delete the file. Uninstalling the plugin does not
delete it. The hooks keep small cursor files (offsets and hashes, no content)
in the plugin's data folder.

## Turning it off

Set `capture` to off in the plugin's settings to stop sending transcripts, or
disable or uninstall the plugin.

## Children

The plugin is not intended for people under 18.
