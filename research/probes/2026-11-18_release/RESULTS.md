# Release 0.1.0 files, tested end to end (T-122, D-046) — 2026-11-18

Built from commit 28be5e0 + the release changes: `st_roto_setup.py package --models tiny`, `package-model` for
SAM 2.1 large and ViTMatte-S, `build_exe.py`.

| File | Bytes | Notes |
|---|---|---|
| ST-ROTO-Setup.exe | 7,218,734 | PyInstaller one-file |
| ST-ROTO-0.1.0.zip | 647,132,902 | 1,640 files (rebuilt after the test with the updated user guide only - manifests compared: no other file differs): src, nuke_plugin, .tools/nuke-py311, SAM 2.1 tiny, manifests, LICENSE, NOTICE, VERSION, user guide |
| ST-ROTO-model-sam2.1-hiera-large.zip | 2,045,556,195 | stored (not deflated); below GitHub's 2 GiB per-file limit (2,147,483,648) |
| ST-ROTO-model-vitmatte-small-composition-1k.zip | 103,912,063 | |

SHA-256 in `docs/releases/0.1.0.md`.

## Install with the BUILT exe (temporary base / home under `tmp/`, the owner's set-up untouched)

* Command line `ST-ROTO-Setup.exe install --source ST-ROTO-0.1.0.zip --base … --home …`: main package + both model
  packages lying next to it installed (20 s), each model checked against its package and against 0.1.0's export
  manifest.
* Double-click path (menu, with LOCALAPPDATA / USERPROFILE redirected to temporary folders for the setup process
  only): the menu lists the main zip + both model zips; choice 1 installed all, wrote the marked init.py block;
  choice 4 removed every file and the init.py it had created. (Piping the answer from PowerShell 5.1 delivered
  something other than "1" - a PowerShell pipe quirk, not seen with a byte pipe or by a person typing; the menu's
  input handling is unchanged since T-103.)

## Nuke 17.1v3 NC, HOME = the temporary home (`check_release.py`)

| Check | Result |
|---|---|
| ST-ROTO loaded from | the installed copy (`<base>/0.1.0/src`), repository not on sys.path |
| Version reported | 0.1.0 |
| Models found in the installed location, full verify (licence/approval/revision + SHA-256 of every file) | tiny 13/13, large 13/13, ViTMatte 3/3 all ok |
| Track 3 frames, model = sam2.1-hiera-large | done, device cuda; 6 ONNX sessions loaded, all from the installed large model, none other |
| Render mattes, edges = ViTMatte-S | 3 frames 1280x720, ViTMatte-S edges, caveat shown |

## Unit tests

4 new installer tests (`tests/unit/test_installer.py`): model package next to the main package installed, verified,
repaired from its package; a model package that does not match the version's export manifest (or a version without
one) is refused and nothing is installed; a damaged model package installs nothing and leaves no work folder; an
upgrade carries a separately installed model over only when the new version expects exactly those files.

## Not tested

* Installing on a second computer (only this machine).
* Downloading the files from GitHub (the uploaded files are compared by SHA-256 after upload instead).
