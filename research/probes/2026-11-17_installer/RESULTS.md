# T-103 — Windows installer: offline package, install, upgrade, rollback, repair, uninstall (REQ-210), 2026-11-17

**Tool.** `tools/installer/st_roto_setup.py` (Python 3.7+ standard library; runs with Nuke's own `python.exe`) and
`dist/ST-ROTO-Setup.exe` (PyInstaller 6.11.1 in the project venv, `tools/installer/build_exe.py`; 7.2 MB, console).
No network at any time: everything comes from the offline package.

| function | behaviour |
|---|---|
| offline package | `package --models none/tiny/all`: zip with `payload/` (src, nuke_plugin, Nuke's Python packages, model manifests, chosen exported models, licence/notice, user guide), `PACKAGE_MANIFEST.json` (size + SHA-256 of every file), the setup script |
| install / upgrade | checks every file of the package first (a damaged package installs nothing), copies into `%LOCALAPPDATA%\ST-ROTO\<version>` (no administrator rights), renames the folder into place only when complete (retried: Windows briefly holds new files - measured), registers the version in `%USERPROFILE%\.nuke\init.py` inside a marked block; other lines of that file are never changed. A newer package = upgrade; the old version stays |
| rollback | switches Nuke back to the previous version (and forward again) |
| repair | finds missing / changed installed files (SHA-256) and re-copies them from the package (refuses a package of another version); re-registers |
| uninstall | removes only ST-ROTO's block (deletes init.py only if ST-ROTO had created it) and ST-ROTO's version folders |
| status | versions, active, previous, what Nuke is told to load |
| .exe | same commands; double-clicked without arguments: a small menu that uses the `ST-ROTO-*.zip` next to it |

**Evidence.**
- Unit (`tests/unit/test_installer.py`, CI): package contents and model choice, install keeps the artist's own
  init.py lines, upgrade -> rollback -> forward, damaged file found and repaired, wrong-version package refused,
  damaged package installs nothing, uninstall restores the artist's init.py byte for byte / removes the one it made.
- End to end (Nuke 17.1 NC, `check_installed.py`, `result_installed.json`): a real package (tiny model, 1,628 files,
  647 MB, built in 40 s) installed with Nuke's `python.exe` in 14 s into a temporary base + home; Nuke started with
  that HOME loaded ST-ROTO **from the installed copy** (not the repository, which was not on its path), resolved the
  model in the installed `models/`, and tracked 3 frames on CUDA. Uninstall removed everything.
- `.exe` (same delivery folder as an artist would get): install, status, menu (quit), uninstall; a studio's own
  init.py line kept. The owner's real `%USERPROFILE%\.nuke\init.py` and `%LOCALAPPDATA%\ST-ROTO` were never touched.

**Findings.** (1) Renaming a just-copied 1,628-file folder failed with "Access is denied" (virus scanner / indexer);
the installer now retries. (2) Starting Nuke with a different `USERPROFILE` makes Nuke Non-commercial exit (code 100,
presumably its licence lives in the real profile); redirecting `HOME` alone is enough for `.nuke`.

**Not done:** a graphical wizard, Start-menu entries, code signing of the .exe (Windows SmartScreen will warn), a
machine-wide (admin) install mode, the `all` models package (2.6 GB) was not built in this test.
