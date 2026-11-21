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

    def test_state_is_scoped_to_the_ledger(self):
        payload = {"session_id": "scoped"}
        self.hook("session-start", payload)
        other = f"http://127.0.0.1:{free_port()}"
        self.hook("session-start", payload, service_url=other, autostart="false")
        found = list((Path(self.env["CLAUDE_PLUGIN_DATA"]) / "atp-session").glob("*/scoped.json"))
        self.assertEqual(len(found), 1)  # the dead ledger registered nothing, and nothing was reused

    def test_helper_follows_the_endpoint_the_hooks_published(self):
        self.hook("session-start", {"session_id": "endpoint"}, mode="offline")
        cfg = json.loads((Path(self.env["HOME"]) / ".prove" / "plugin-endpoint.json").read_text())
        self.assertEqual(cfg, {"mode": "offline", "service_url": f"http://127.0.0.1:{self.port}"})
        env = {k: v for k, v in self.env.items() if k != "PROVENANCE_SERVICE_URL"}
        run = subprocess.run([sys.executable, "-I", str(SCRIPTS / "prove_log.py"), "begin", "--context", "t"],
                             env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertRegex(run.stdout.strip(), r"^[0-9a-f-]{36}$")


class TranscriptChunkTests(unittest.TestCase):
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


class DashboardDefaultsTests(unittest.TestCase):
    def test_dashboard_defaults_to_its_own_origin(self):
        js = (UI / "app.js").read_text()
        self.assertIn("window.location.origin", js)
        self.assertNotIn("'http://localhost:8787'", js)


class RemoteBindTests(unittest.TestCase):
    def test_local_server_refuses_non_loopback_without_flag(self):
        result = subprocess.run([sys.executable, "-I", str(SCRIPTS / "prove_local.py"), "serve", "--host", "0.0.0.0"],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 2)
        self.assertIn("refusing to bind", result.stderr)


if __name__ == "__main__":
    unittest.main()
