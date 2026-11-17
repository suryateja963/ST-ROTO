"""Build dist/ST-ROTO-Setup.exe from st_roto_setup.py with PyInstaller (T-103, REQ-210). Run with the project venv:
  .venv\\Scripts\\python.exe -I tools/installer/build_exe.py
The .exe is the same setup (install / upgrade / rollback / repair / uninstall / status); double-clicked without
arguments it shows a small menu and installs the ST-ROTO-*.zip package lying next to it. No network at run time."""
import os
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def main():
    work = os.path.join(ROOT, "tmp", "pyinstaller")
    cmd = [sys.executable, "-m", "PyInstaller", "--onefile", "--console", "--noconfirm", "--clean",
           "--name", "ST-ROTO-Setup", "--distpath", os.path.join(ROOT, "dist"), "--workpath", work,
           "--specpath", work, os.path.join(ROOT, "tools", "installer", "st_roto_setup.py")]
    subprocess.check_call(cmd)
    exe = os.path.join(ROOT, "dist", "ST-ROTO-Setup.exe")
    print("built", exe, os.path.getsize(exe), "bytes")


if __name__ == "__main__":
    main()
