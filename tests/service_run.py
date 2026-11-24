import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

ENGINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.join(ENGINE, "edu4self")


def fail(why, out=""):
    print("SERVICE RUN FAILED: %s" % why)
    if out:
        print(out)
    sys.exit(1)


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def cli(env, *args, ok=True):
    r = subprocess.run([sys.executable, CLI, *args], env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, encoding="utf-8", errors="replace", timeout=120)
    print("$ edu4self %s  (exit %d)\n%s" % (" ".join(args), r.returncode, r.stdout))
    if ok and r.returncode:
        fail("edu4self %s exited %d" % (args[0], r.returncode), r.stdout)
    return r.stdout


def answers(port):
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d/api/config" % port, timeout=5) as r:
            return json.load(r)
    except OSError:
        return None


def wait_for(cond, seconds=30):
    end = time.time() + seconds
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.5)
    return False


def main():
    if not os.environ.get("GITHUB_ACTIONS"):
        sys.exit("CI only: this installs and removes the login service of the machine it runs on.")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    tmp = tempfile.mkdtemp(prefix="edu4self-service-")
    env = dict(os.environ, EDU4SELF_CONFIG_HOME=os.path.join(tmp, "cfg"), CLAUDE_CONFIG_DIR=os.path.join(tmp, "claude"),
               EDU4SELF_NO_UPDATE_CHECK="1", PYTHONUTF8="1")
    for k in ("EDU4SELF_VAULT", "EDU4SELF_PORT"):
        env.pop(k, None)
    vault, port = os.path.join(tmp, "learn"), free_port()
    try:
        cli(env, "setup", "--vault", vault, "--name", "Kim", "--port", str(port), "--no-plugin", "--no-open", "--gifts", "off")
        if not wait_for(lambda: (answers(port) or {}).get("config", {}).get("name") == "Kim"):
            fail("the login service didn't serve the new vault on port %d" % port)
        out = cli(env, "status")
        if "installed (starts at login)" not in out:
            fail("status doesn't see the login service", out)
        cli(env, "restart")
        if not wait_for(lambda: answers(port) is not None):
            fail("the dashboard didn't come back after restart")
        cli(env, "uninstall")
        if not wait_for(lambda: answers(port) is None, 15):
            fail("the dashboard still answers after uninstall")
        out = cli(env, "status", ok=False)
        if "not installed" not in out:
            fail("status still sees a login service after uninstall", out)
        print("SERVICE RUN OK")
    finally:
        cli(env, "uninstall", ok=False)
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
