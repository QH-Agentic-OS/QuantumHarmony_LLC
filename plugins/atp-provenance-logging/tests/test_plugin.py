"""Plugin-level checks: network-free UI, local server, hook modes, capture.

    python3 -m unittest discover -s plugins/atp-provenance-logging/tests -v

Stdlib only. Each test that needs a service starts the bundled one on a free
port with a temporary ledger and data dir.
"""

import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UI = ROOT / "ui"
SCRIPTS = ROOT / "scripts"
NETWORK_REF = re.compile(r"""(src|href)\s*=\s*["']\s*(https?:)?//""", re.I)


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class OfflineUITests(unittest.TestCase):
    def test_pages_load_nothing_from_the_network(self):
        for page in ("index.html", "prove-offline.html"):
            text = (UI / page).read_text()
            self.assertIsNone(NETWORK_REF.search(text), page)
            self.assertNotIn("unpkg.com/react", text.split("-->", 1)[-1] if page == "index.html" else text)

    def test_index_references_only_local_files_that_exist(self):
        text = (UI / "index.html").read_text()
        refs = re.findall(r'(?:src|href)="([^"]+)"', text)
        self.assertEqual(
            sorted(refs),
            sorted(["app.css", "vendor/react.production.min.js", "vendor/react-dom.production.min.js", "app.js"]),
        )
        for ref in refs:
            self.assertTrue((UI / ref).is_file(), ref)

    def test_vendored_react_matches_recorded_checksums(self):
        for line in (UI / "vendor" / "SHA256SUMS").read_text().splitlines():
            digest, name = line.split()
            self.assertEqual(hashlib.sha256((UI / "vendor" / name).read_bytes()).hexdigest(), digest, name)

    def test_app_needs_no_eval_and_single_file_build_is_current(self):
        self.assertNotRegex((UI / "app.js").read_text(), r"\beval\(|new Function\(")
        result = subprocess.run([sys.executable, "-I", str(SCRIPTS / "build_offline.py"), "--check"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


class LocalServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.port = free_port()
        cls.env = dict(os.environ, HOME=cls.tmp.name, CLAUDE_PLUGIN_DATA=str(Path(cls.tmp.name) / "data"))
        for key in [k for k in cls.env if k.startswith("CLAUDE_PLUGIN_OPTION_")]:
            del cls.env[key]
        cls.db = Path(cls.tmp.name) / "ledger" / "provenance.db"
        cls.proc = subprocess.Popen(
            [sys.executable, "-I", str(SCRIPTS / "prove_local.py"), "serve", "--port", str(cls.port), "--db", str(cls.db)],
            env=cls.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        for _ in range(50):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{cls.port}/health", timeout=0.5)
                break
            except OSError:
                time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        cls.proc.wait(5)
        cls.tmp.cleanup()

    def get(self, path):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=3) as r:
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()

    def hook(self, event, payload, **options):
        env = dict(self.env)
        env["CLAUDE_PLUGIN_OPTION_SERVICE_URL"] = f"http://127.0.0.1:{self.port}"
        env["CLAUDE_PLUGIN_OPTION_LEDGER_PATH"] = str(self.db)
        env.update({f"CLAUDE_PLUGIN_OPTION_{k.upper()}": v for k, v in options.items()})
        return subprocess.run([sys.executable, "-I", str(SCRIPTS / "prove_hook.py"), event],
                              input=json.dumps(payload), env=env, capture_output=True, text=True, timeout=60)

    def test_creates_ledger_and_serves_dashboard_with_csp(self):
        self.assertTrue(self.db.is_file())
        status, headers, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn(b'<div id="root">', body)
        self.assertIn("script-src 'self'", headers["Content-Security-Policy"])
        for path in ("/app.js", "/app.css", "/vendor/react.production.min.js", "/vendor/react-dom.production.min.js"):
            self.assertEqual(self.get(path)[0], 200, path)

    def test_serves_only_listed_assets(self):
        for path in ("/../server/manifest.py", "/provenance.db", "/vendor/SHA256SUMS", "/prove-offline.html"):
            self.assertEqual(self.get(path)[0], 404, path)

    def test_runtime_metadata_hashes_the_bundled_dashboard(self):
        status, _, body = self.get("/runtime/metadata")
        self.assertEqual(status, 200)
        digest = hashlib.sha256((UI / "app.js").read_bytes()).hexdigest()
        self.assertIn(digest, body.decode())

    def test_hooks_capture_a_transcript_as_verified_steps(self):
        work = Path(self.tmp.name) / "work"
        work.mkdir(exist_ok=True)
        lines = [
            {"type": "user", "timestamp": "2026-01-01T00:00:00Z", "cwd": str(work),
             "message": {"role": "user", "content": "add a test"}},
            {"type": "assistant", "timestamp": "2026-01-01T00:00:01Z", "cwd": str(work),
             "message": {"role": "assistant", "content": [
                 {"type": "tool_use", "id": "toolu_1", "name": "Bash",
                  "input": {"command": "curl -H 'Authorization: Bearer abcdefghijklmnopqrst' x"}}]}},
        ]
        transcript = work / "t.jsonl"
        transcript.write_text("".join(json.dumps(line) + "\n" for line in lines))
        payload = {"session_id": "plugin-test", "cwd": str(work), "transcript_path": str(transcript)}
        for event in ("session-start", "post-tool", "stop"):
            self.assertEqual(self.hook(event, payload, mode="offline").returncode, 0, event)
        states = list((Path(self.env["CLAUDE_PLUGIN_DATA"]) / "atp-session").glob("*/plugin-test.json"))
        self.assertEqual(len(states), 1)
        state = json.loads(states[0].read_text())
        status, _, body = self.get(f"/verify?parent_prov_id={state['root_prov_id']}")
        report = json.loads(body)
        self.assertEqual(status, 200)
        self.assertTrue(report["verified"])
        self.assertEqual(report["capture_methods"], {"harness_transcript": 2})
        self.assertNotIn(b"abcdefghijklmnopqrst", self.db.read_bytes())

    def test_a_record_over_512_kib_is_still_captured(self):
        work = Path(self.tmp.name) / "big"
        work.mkdir(exist_ok=True)
        big = {"type": "user", "timestamp": "2026-01-01T00:00:00Z", "cwd": str(work),
               "message": {"role": "user", "content": "y" * 600_000}}
        small = {"type": "user", "timestamp": "2026-01-01T00:00:01Z", "cwd": str(work),
                 "message": {"role": "user", "content": "after"}}
        transcript = work / "t.jsonl"
        transcript.write_text(json.dumps(big) + "\n" + json.dumps(small) + "\n")
        payload = {"session_id": "big-record", "cwd": str(work), "transcript_path": str(transcript)}
        for event in ("session-start", "stop"):
            self.assertEqual(self.hook(event, payload).returncode, 0, event)
        state = json.loads(next((Path(self.env["CLAUDE_PLUGIN_DATA"]) / "atp-session").glob("*/big-record.json")).read_text())
        self.assertEqual(state["trajectories"]["big-record"]["offset"], transcript.stat().st_size)

    def test_refuses_to_record_into_a_different_ledger(self):
        other = Path(self.tmp.name) / "other.db"
        result = self.hook("session-start", {"session_id": "wrong-ledger"}, ledger_path=str(other), autostart="false")
        self.assertIn("capture is off", result.stdout)
        self.assertEqual(list((Path(self.env["CLAUDE_PLUGIN_DATA"]) / "atp-session").glob("*/wrong-ledger.json")), [])

    def test_offline_traffic_ignores_environment_proxies(self):
        trap = socket.socket()
        trap.bind(("127.0.0.1", 0))
        trap.listen(5)
        trap.settimeout(0.2)
        self.addCleanup(trap.close)
        proxy = f"http://127.0.0.1:{trap.getsockname()[1]}"
        env_backup = dict(self.env)
        self.env.update(HTTP_PROXY=proxy, http_proxy=proxy, NO_PROXY="", no_proxy="")
        try:
            result = self.hook("session-start", {"session_id": "proxied"}, mode="offline")
        finally:
            self.env.clear()
            self.env.update(env_backup)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(len(list((Path(self.env["CLAUDE_PLUGIN_DATA"]) / "atp-session").glob("*/proxied.json"))), 1)
        with self.assertRaises(socket.timeout):
            trap.accept()  # nothing was sent to the proxy

    def test_atp_markers_share_the_session_root(self):
        work = Path(self.tmp.name) / "atp"
        work.mkdir(exist_ok=True)
        transcript = work / "t.jsonl"
        transcript.write_text(json.dumps({"type": "user", "timestamp": "2026-01-01T00:00:00Z", "cwd": str(work),
                                          "message": {"role": "user", "content": "ATP: do it"}}) + "\n")
        payload = {"session_id": "atp-session", "cwd": str(work), "transcript_path": str(transcript)}
        self.assertEqual(self.hook("session-start", payload).returncode, 0)
        env = {k: v for k, v in self.env.items() if k != "PROVENANCE_SERVICE_URL"}

        def helper(*args):
            run = subprocess.run([sys.executable, "-I", str(SCRIPTS / "prove_log.py"), *args],
                                 env=env, cwd=work, capture_output=True, text=True, timeout=30)
            self.assertEqual(run.returncode, 0, run.stderr)
            return run.stdout.strip()

        root = helper("begin", "--context", "ATP: do it")
        state = json.loads(next((Path(self.env["CLAUDE_PLUGIN_DATA"]) / "atp-session").glob("*/atp-session.json")).read_text())
        self.assertEqual(root, state["root_prov_id"])
        self.assertEqual(self.hook("stop", payload).returncode, 0)
        helper("end", root, "--summary", "done")
        chain = json.loads(helper("chain", root))
        phases = [e.get("phase") or e.get("action_type") for e in chain]
        self.assertIn("atp_prompt", phases[1:])          # the marker, after the root
        self.assertIn("step", phases)                    # a harness-captured step under the same root
        self.assertEqual(phases[-1], "atp_response")
        self.assertTrue(json.loads(helper("verify", root))["verified"])
        self.assertNotEqual(helper("begin", "--new-root", "--context", "separate"), root)

    def test_concurrent_hooks_register_one_root(self):
        work = Path(self.tmp.name) / "race"
        work.mkdir(exist_ok=True)
        transcript = work / "t.jsonl"
        transcript.write_text(json.dumps({"type": "user", "timestamp": "2026-01-01T00:00:00Z", "cwd": str(work),
                                          "message": {"role": "user", "content": "go"}}) + "\n")
        payload = json.dumps({"session_id": "race", "cwd": str(work), "transcript_path": str(transcript)})
        env = dict(self.env, CLAUDE_PLUGIN_OPTION_SERVICE_URL=f"http://127.0.0.1:{self.port}",
                   CLAUDE_PLUGIN_OPTION_LEDGER_PATH=str(self.db))
        procs = [subprocess.Popen([sys.executable, "-I", str(SCRIPTS / "prove_hook.py"), "post-tool"],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=env) for _ in range(6)]
        for proc in procs:
            proc.communicate(payload.encode(), timeout=60)
        state = json.loads(next((Path(self.env["CLAUDE_PLUGIN_DATA"]) / "atp-session").glob("*/race.json")).read_text())
        status, _, body = self.get(f"/verify?parent_prov_id={state['root_prov_id']}")
        self.assertTrue(json.loads(body)["verified"])
        self.assertEqual(json.loads(body)["trajectories"]["race"]["steps"], 1)
        import sqlite3
        with sqlite3.connect(self.db) as conn:
            roots = conn.execute("SELECT COUNT(*) FROM agent_logs WHERE parent_prov_id IS NULL "
                                 "AND canonical_body_json LIKE ?", ("%claude-code session race %",)).fetchone()[0]
        self.assertEqual(roots, 1)

    def test_offline_mode_refuses_a_remote_service(self):
        result = self.hook("session-start", {"session_id": "x"}, mode="offline",
                           service_url="https://prove.example.com")
        self.assertEqual(result.returncode, 0)
        self.assertIn("not loopback", result.stdout)
        strict = self.hook("session-start", {"session_id": "x"}, mode="offline", strict="true",
                           service_url="https://prove.example.com")
        self.assertEqual(strict.returncode, 2)

    def test_hosted_mode_needs_https_and_a_url(self):
        self.assertIn("no service URL", self.hook("session-start", {"session_id": "x"}, mode="hosted",
                                                  service_url="").stdout)
        self.assertIn("https", self.hook("session-start", {"session_id": "x"}, mode="hosted",
                                         service_url="http://prove.example.com").stdout)

    def test_capture_off_does_nothing(self):
        result = self.hook("session-start", {"session_id": "off"}, capture="false")
        self.assertEqual((result.returncode, result.stdout), (0, ""))
        self.assertEqual(list((Path(self.env["CLAUDE_PLUGIN_DATA"]) / "atp-session").glob("*/off.json")), [])

    def test_strict_refuses_prompts_while_prove_is_down(self):
        dead = f"http://127.0.0.1:{free_port()}"
        result = self.hook("user-prompt", {"session_id": "strict"}, strict="true", service_url=dead, autostart="false")
        self.assertEqual(result.returncode, 2)
        self.assertIn("unreachable", result.stderr)
        self.assertEqual(self.hook("user-prompt", {"session_id": "strict"}, strict="true").returncode, 0)

    def test_strict_hosted_refuses_prompts_when_the_token_is_rejected(self):
        port, token = free_port(), "t" * 40
        db = Path(self.tmp.name) / "hosted" / "provenance.db"
        subprocess.run([sys.executable, "-I", str(SCRIPTS / "prove_local.py"), "init", "--db", str(db)],
                       env=self.env, check=True, capture_output=True)
        proc = subprocess.Popen([sys.executable, str(ROOT / "server" / "hosted_service.py")],
                                env=dict(self.env, PROV_DB=str(db), PORT=str(port), PROV_API_TOKEN=token),
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            url = f"http://127.0.0.1:{port}"
            for _ in range(50):
                try:
                    urllib.request.urlopen(f"{url}/health", timeout=0.5)
                    break
                except OSError:
                    time.sleep(0.1)
            options = dict(mode="hosted", service_url=url, strict="true", autostart="false", ledger_path="")
            for bad in ("wrong" * 8, ""):
                result = self.hook("user-prompt", {"session_id": "hosted-strict"}, api_token=bad, **options)
                self.assertEqual(result.returncode, 2, bad)
                self.assertIn("rejected the api_token", result.stderr)
            good = self.hook("user-prompt", {"session_id": "hosted-strict"}, api_token=token, **options)
            self.assertEqual(good.returncode, 0, good.stderr)
        finally:
            proc.terminate()
            proc.wait(5)

    def test_state_is_scoped_to_the_ledger(self):
        payload = {"session_id": "scoped"}
        self.hook("session-start", payload)
        other = f"http://127.0.0.1:{free_port()}"
        self.hook("session-start", payload, service_url=other, autostart="false")
        found = list((Path(self.env["CLAUDE_PLUGIN_DATA"]) / "atp-session").glob("*/scoped.json"))
        self.assertEqual(len(found), 1)  # the dead ledger registered nothing, and nothing was reused

    def test_helper_follows_this_workspaces_receipt(self):
        work = Path(self.tmp.name) / "receipt"
        work.mkdir(exist_ok=True)
        payload = {"session_id": "endpoint", "cwd": str(work)}
        self.hook("session-start", payload, mode="offline")
        env = {k: v for k, v in self.env.items() if k != "PROVENANCE_SERVICE_URL"}
        sub = work / "sub"
        sub.mkdir(exist_ok=True)
        run = subprocess.run([sys.executable, "-I", str(SCRIPTS / "prove_log.py"), "begin", "--context", "t"],
                             env=env, cwd=sub, capture_output=True, text=True, timeout=30)
        self.assertEqual(run.returncode, 0, run.stderr)
        state = json.loads(next((Path(self.env["CLAUDE_PLUGIN_DATA"]) / "atp-session").glob("*/endpoint.json")).read_text())
        self.assertEqual(run.stdout.strip(), state["root_prov_id"])  # found from a subfolder

    def test_receipts_end_with_the_session_or_when_capture_is_off(self):
        work = Path(self.tmp.name) / "stale"
        work.mkdir(exist_ok=True)
        receipts = Path(self.env["HOME"]) / ".prove" / "active-sessions"
        self.hook("session-start", {"session_id": "first", "cwd": str(work)})
        self.assertEqual(len(list(receipts.glob("*.json"))) >= 1, True)
        before = set(receipts.glob("*.json"))
        self.hook("session-end", {"session_id": "other", "cwd": str(work)})
        self.assertEqual(set(receipts.glob("*.json")), before)  # not this session's to drop
        self.hook("session-start", {"session_id": "second", "cwd": str(work)}, capture="false")
        self.assertEqual(len(set(receipts.glob("*.json"))), len(before) - 1)
        self.hook("session-start", {"session_id": "third", "cwd": str(work)})
        self.hook("session-end", {"session_id": "third", "cwd": str(work)})
        self.assertEqual(len(set(receipts.glob("*.json"))), len(before) - 1)

    def setUp(self):
        sys.path.insert(0, str(ROOT / "server"))
        import atp_hooks
        self.hooks = atp_hooks

    def test_mask_hides_credentials_without_moving_offsets(self):
        raw = b'{"x": "curl -H \'Authorization: Bearer abcdefghijklmnopqrst\' ghp_ABCDEFGH12345678"}\n'
        masked = self.hooks._mask(raw)
        self.assertEqual(len(masked), len(raw))
        self.assertNotIn(b"abcdefghijklmnopqrst", masked)
        self.assertNotIn(b"ghp_ABCDEFGH", masked)

    def test_chunks_never_exceed_the_record_limit(self):
        with tempfile.NamedTemporaryFile("wb", delete=False) as f:
            f.write(b"{}\n" * 1001)
        try:
            pieces = list(self.hooks._transcript_chunks(f.name, 0, 512 * 1024, max_records=400))
        finally:
            os.unlink(f.name)
        self.assertEqual([p.count(b"\n") for p in pieces], [400, 400, 201])
        self.assertEqual(sum(map(len, pieces)), 3 * 1001)


class SubagentRetryTests(unittest.TestCase):
    def test_failed_subagent_ingest_is_retried_by_later_hooks(self):
        sys.path.insert(0, str(ROOT / "server"))
        import atp_hooks
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        sub = Path(tmp.name) / "sub.jsonl"
        sub.write_text(json.dumps({"type": "user", "message": {"role": "user", "content": "x"}}) + "\n")
        state = {"session_id": "s", "root_prov_id": "r", "binding_id": "b", "trajectories": {}}
        calls = []

        def fake_post(path, payload, timeout=10):
            calls.append(payload["trajectory_id"])
            if len(calls) == 1:
                return 0, None  # Prove down at SubagentStop
            return 200, {"consumed_to": payload["offset"] + len(payload["chunk"].encode()), "chain_sha256": "c"}

        orig_post, orig_dir, orig_state = atp_hooks._post_status, atp_hooks.STATE_DIR, atp_hooks._require_state
        atp_hooks._post_status, atp_hooks.STATE_DIR = fake_post, Path(tmp.name) / "state"
        try:
            atp_hooks._require_state = lambda hook: state
            atp_hooks.cmd_subagent_stop({"agent_transcript_path": str(sub), "agent_id": "a1"})
            self.assertNotIn("pending_subagents", state)  # retried in the same run once Prove answered
            self.assertEqual(calls, ["s:a1", "s:a1"])
        finally:
            atp_hooks._post_status, atp_hooks.STATE_DIR, atp_hooks._require_state = orig_post, orig_dir, orig_state


class DashboardDefaultsTests(unittest.TestCase):
    def test_dashboard_defaults_to_its_own_origin(self):
        js = (UI / "app.js").read_text()
        self.assertIn("window.location.origin", js)
        self.assertNotIn("'http://localhost:8787'", js)
        self.assertIn("e.phase || ARTEMIS_ACTION_TO_PHASE", js)
        self.assertIn("e.input && typeof e.input === 'object'", js)
        self.assertIn("/verify?parent_prov_id=", js)  # live chains pass only on the service's verdict


class RemoteBindTests(unittest.TestCase):
    def test_local_server_refuses_non_loopback_without_flag(self):
        result = subprocess.run([sys.executable, "-I", str(SCRIPTS / "prove_local.py"), "serve", "--host", "0.0.0.0"],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 2)
        self.assertIn("refusing to bind", result.stderr)


if __name__ == "__main__":
    unittest.main()
