"""Run a test script inside an isolated, headless Blender.

Usage:
    python tests/run_blender.py                      # runs tests/test_addon.py
    python tests/run_blender.py tests/probe_behaviour.py -- out.json
    python tests/run_blender.py --addon-root PATH ...   # test another copy of the add-on

Isolation: Blender runs with --background --factory-startup (no user preferences,
no startup file) and BLENDER_USER_RESOURCES pointing at a temporary folder, so
your real profile, installed add-ons and open Blender sessions are never touched.

The Blender executable is taken from --blender, the BLENDER environment variable,
the default Windows install path of Blender 5.3, or `blender` on PATH.
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
DEFAULT_WIN = r"C:\Program Files\Blender Foundation\Blender 5.3\blender.exe"


def find_blender(explicit):
    for cand in (explicit, os.environ.get("BLENDER"), DEFAULT_WIN, shutil.which("blender")):
        if cand and os.path.isfile(cand):
            return cand
    sys.exit("Blender not found: pass --blender PATH or set BLENDER")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blender")
    ap.add_argument("--addon-root", default=REPO,
                    help="folder that contains the driver_controller package")
    ap.add_argument("script", nargs="?", default=os.path.join(HERE, "test_addon.py"))
    ap.add_argument("script_args", nargs=argparse.REMAINDER)
    a = ap.parse_args()

    blender = find_blender(a.blender)
    profile = tempfile.mkdtemp(prefix="dc_profile_")
    env = dict(os.environ, BLENDER_USER_RESOURCES=profile, DC_ADDON_ROOT=os.path.abspath(a.addon_root))
    extra = [x for x in a.script_args if x != "--"]
    cmd = [blender, "--background", "--factory-startup", "--python-exit-code", "1",
           "--python", os.path.abspath(a.script), "--", *extra]
    try:
        return subprocess.call(cmd, env=env)
    finally:
        shutil.rmtree(profile, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
