"""A stranger's first run, end to end, the way the README says: setup, check, serve, status, doctor.

CI runs it on macOS, Linux and Windows (the first-run job). It runs locally too and touches nothing of yours:
the settings, the Claude config and the vault all go to a temporary folder, on a free port, with no login service
and no plugin install. Exits non-zero on the first thing that goes wrong, and says what.

    python3 tests/first_run.py
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

ENGINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.join(ENGINE, "edu4self")
# doctor may fail these on a machine without Claude Code (CI): everything else must pass
NEEDS_CLAUDE = ("Claude Code", "tutor skills", "edu4self plugin")


def fail(why, out=""):
    print("FIRST RUN FAILED: %s" % why)
    if out:
        print(out)
    sys.exit(1)


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def cli(env, *args, ok=True):
    t = time.time()
    r = subprocess.run([sys.executable, CLI, *args], env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, encoding="utf-8", errors="replace", timeout=120)
    print("$ edu4self %s  (exit %d, %.1fs)" % (" ".join(args), r.returncode, time.time() - t))
    if ok and r.returncode:
        fail("edu4self %s exited %d" % (args[0], r.returncode), r.stdout)
    return r.stdout


def main():
    if hasattr(sys.stdout, "reconfigure"):      # doctor prints ✓ and ✗; Windows' console code page can't
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    tmp = tempfile.mkdtemp(prefix="edu4self-first-run-")
    env = dict(os.environ, EDU4SELF_CONFIG_HOME=os.path.join(tmp, "cfg"), CLAUDE_CONFIG_DIR=os.path.join(tmp, "claude"),
               EDU4SELF_NO_UPDATE_CHECK="1", PYTHONUTF8="1")
    for k in ("EDU4SELF_VAULT", "EDU4SELF_PORT"):
        env.pop(k, None)
    vault, port = os.path.join(tmp, "learn"), free_port()
    server = None
    try:
        out = cli(env, "setup", "--vault", vault, "--name", "Kim", "--port", str(port),
                  "--no-service", "--no-plugin", "--no-open", "--gifts", "off")
        if "./edu4self serve" not in out or "http://127.0.0.1:%d/" % port not in out:
            fail("setup didn't say how to start the dashboard and where it is", out)
        cli(env, "check")

        server = subprocess.Popen([sys.executable, CLI, "serve"], env=env, stdin=subprocess.DEVNULL,
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding="utf-8", errors="replace")
        first = []
        reader = threading.Thread(target=lambda: first.append(server.stdout.readline()), daemon=True)
        reader.start()
        reader.join(20)
        if not first or "http://127.0.0.1:%d/" % port not in first[0]:
            fail("serve didn't print its address within 20 s", "".join(first))
        print("$ edu4self serve  -> %s" % first[0].strip())
        with urllib.request.urlopen("http://127.0.0.1:%d/api/config" % port, timeout=10) as r:
            got = json.load(r)
        if got.get("error") is not None or got.get("config", {}).get("name") != "Kim":
            fail("the dashboard doesn't serve the new vault's config", json.dumps(got)[:500])

        cli(env, "status")
        out = cli(env, "doctor", ok=False)
        bad = [l for l in out.splitlines() if "✗" in l and not any(k in l for k in NEEDS_CLAUDE)]
        if bad or "✓ dashboard answering" not in out:
            fail("doctor found a problem that isn't about Claude Code", out)
        print(out)
        print("FIRST RUN OK")
    finally:
        if server:
            server.kill()
            server.wait()
            server.stdout.close()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
