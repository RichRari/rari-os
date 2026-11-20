"""Rari OS self-test. Run with ./test.sh — it starts a throwaway copy of Rari OS on a spare
port with its own temporary database (your real data and API credits are never touched),
checks every part, hammers it with requests at the same time, and prints PASS or FAIL."""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent
results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail and not ok else ""))


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def request(base, path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read().decode()
        return r.status, raw


def main():
    print(f"Rari OS self-test · Python {sys.version.split()[0]} · {sys.platform}\n")
    check("Python 3.9 or newer", sys.version_info >= (3, 9), sys.version)

    tmp = tempfile.mkdtemp(prefix="rari-os-test-")
    watch = Path(tmp) / "watch"
    watch.mkdir()
    (watch / "a.txt").write_text("hello")
    env = {**os.environ, "RARI_OS_DATA": str(Path(tmp) / "data"), "RARI_OS_WATCH": str(watch),
           "ANTHROPIC_API_KEY": ""}  # never spend API credits during tests
    port = free_port()
    log_path = Path(tmp) / "server.log"
    log = open(log_path, "w")
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "rari_os.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(60):
            try:
                request(base, "/api/status")
                break
            except Exception:
                time.sleep(0.25)
        check("Server starts", server.poll() is None)

        status, page = request(base, "/")
        check("Control panel loads (RARI//OS)", status == 200 and "<title>RARI//OS</title>" in page)

        check("AI replies render formatting (bold, lists, code)", "function renderMd" in page and "renderMd(body" in page)

        for path in ("/api/status", "/api/agents", "/api/runs?limit=5", "/api/chat",
                     "/api/runs?agent=system_health&limit=1"):
            try:
                status, _ = request(base, path)
                check(f"GET {path}", status == 200, status)
            except Exception as e:
                check(f"GET {path}", False, e)

        agents = json.loads(request(base, "/api/agents")[1])
        check("All agents registered", len(agents) >= 3, len(agents))
        for a in agents:
            for _ in range(40):  # if the scheduler is already running it, wait and retry
                res = json.loads(request(base, f"/api/agents/{a['name']}/run", "POST")[1])
                if res.get("status") != "busy":
                    break
                time.sleep(0.25)
            check(f"Agent runs without crashing: {a['name']}", res.get("status") in ("ok", "alert"), res)

        (watch / "a.txt").write_text("changed")
        (watch / "b.txt").write_text("new")
        res = json.loads(request(base, "/api/agents/file_integrity/run", "POST")[1])
        check("File Integrity Monitor detects changes", res.get("status") == "alert", res)

        status, _ = request(base, "/api/agents/system_health", "PATCH", {"enabled": False, "interval_seconds": 120})
        a = next(x for x in json.loads(request(base, "/api/agents")[1]) if x["name"] == "system_health")
        check("Agent settings save", status == 200 and a["enabled"] is False and a["interval_seconds"] == 120)

        # The bug from Nov 19: many requests at the same time while agents run.
        paths = [("/api/agents", "GET"), ("/api/runs?limit=60", "GET"),
                 ("/api/runs?agent=system_health&limit=1", "GET"),
                 ("/api/agents/system_health/run", "POST"), ("/api/agents/file_integrity/run", "POST")]
        jobs = paths * 40

        def hit(job):
            try:
                return request(base, job[0], job[1])[0]
            except Exception as e:
                return str(e)

        with ThreadPoolExecutor(max_workers=25) as pool:
            codes = list(pool.map(hit, jobs))
        bad = [c for c in codes if c != 200]
        check(f"Stress test: {len(jobs)} requests at once", not bad, f"{len(bad)} failed, e.g. {bad[:3]}")
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
        log.close()

    # Nov 19: the AI core could not see alert file paths and spoke in UTC.
    os.environ["RARI_OS_DATA"] = env["RARI_OS_DATA"]
    sys.path.insert(0, str(ROOT))
    try:
        from rari_os.main import build_chat_context
        ctx = build_chat_context()
        check("AI core sees alert details (file names)", "b.txt" in ctx)
        check("AI core sees local time, not raw UTC", "CURRENT LOCAL TIME" in ctx and "+00:00" not in ctx)
    except Exception as e:
        check("AI core context builds", False, e)

    errors = [ln for ln in log_path.read_text().splitlines()
              if "Traceback" in ln or "Error" in ln and "INFO" not in ln]
    check("No errors in server log", not errors, errors[:3])

    passed = sum(results)
    print(f"\n{'ALL PASS' if all(results) else 'FAILED'}: {passed}/{len(results)} checks")
    if not all(results):
        print(f"Server log kept at {log_path}")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
