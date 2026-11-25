"""One job step, run apart from the API: python -m api.jobstep <log> <command...>. The command's output goes to the log
file and its exit code to <log>.rc when it ends. The API (jobs.py) follows the log, so a restarting API (dev reload,
a crash) leaves the step running: the new API picks the log up again instead of losing the work."""

import os
import subprocess
import sys

if __name__ == "__main__":
    log, cmd = sys.argv[1], sys.argv[2:]
    with open(log, "ab") as out:
        rc = subprocess.call(cmd, stdout=out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    with open(log + ".rc.tmp", "w") as f:
        f.write(str(rc))
    os.replace(log + ".rc.tmp", log + ".rc")  # whole or not at all: its presence means the step ended
