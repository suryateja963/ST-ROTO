# Installing ST-ROTO

This guide covers installing, checking, updating and removing ST-ROTO, for single artists and for studios. Day-to-day use is in `docs/MANUAL.md`.

> **What has been verified:** Windows 11, **Nuke 17.1v3 Non-commercial**, NVIDIA RTX 5060 Laptop (CUDA), the same machine through DirectML, and its integrated Intel UHD GPU. Installation was tested end to end with the built setup in temporary folders: install, Nuke loads the installed copy, tracking, uninstall. **No other Nuke version or edition, operating system or second computer has been tested yet.** Rows marked *untested* below say what is expected and why, not what was seen.

## 1. Which Nuke versions and editions

The download contains Python packages built for **Python 3.11 on 64-bit Windows**. A Nuke whose Python is not 3.11 can't load them, and then the AI is unavailable.

| Nuke | Python | With this package |
|---|---|---|
| 17.1 | 3.11 | **tested** (Non-commercial) |
| 17.0 | 3.11 | untested; expected to work (same Python and CUDA 12) |
| 16.x | 3.11 | untested; the Python matches, but CUDA in 16 is documented as 11.8+, so the CUDA runtime may fall back to the CPU. DirectML doesn't depend on Nuke's CUDA. |
| 15.x and older | 3.10 / 3.9 / 3.7 | **not supported by this package**. The AI packages won't load. The core code is written to run on Python 3.7, but the Nuke adapter has not been tried there. |
| macOS, Linux | – | not supported (Windows-only packages and installer) |

| Edition | What to expect |
|---|---|
| **Nuke Non-commercial** (tested) | Works within the edition's limits: at most 10 Python-accessible nodes per session (ST_Roto uses 3), renders up to 1920×1080 (larger plates are tracked from reduced frames), scripts saved encrypted (`.nknc`). Mattes default to *fit 1920x1080*. |
| **Nuke Indie** (untested) | Foundry documents the same 10-node Python limit; its render limit wasn't measured. Expected to behave like Non-commercial. |
| **Nuke, NukeX, Nuke Studio** (untested) | No node or render limits: full-resolution tracking and mattes (the default matte size there is *full resolution*). Expected to work; not verified. |

Also note **Foundry's Non-commercial licence**: it forbids professional or business use and the creation of commercial tools with that edition. Check that your use is allowed.

## 2. Hardware

| GPU | Runtime ST-ROTO uses | Notes |
|---|---|---|
| NVIDIA with a driver for CUDA 12 | CUDA (fastest) | tracking about 0.35 s/frame (tiny) or 0.55 s/frame (large) at 720p on an RTX 5060 Laptop |
| AMD, Intel, other DirectX 12 GPU | DirectML (automatic when no NVIDIA driver is found) | **from the release after 0.1.0**. Measured: the same shapes as CUDA; about 6 s/frame on an integrated Intel UHD. AMD untested. |
| none | CPU | works, but much slower |

GPU memory for a track: tiny needs about 3.7 GB with CUDA (2.6 GB with DirectML); large about 6.8 GB (4.3 GB). System RAM: 16 GB was used in testing. Disk: about 1.2 GB for the program and the tiny model, plus 2.0 GB for the large model and 0.1 GB for ViTMatte.

## 3. Single artist: install with the setup

1. From **[Releases](https://github.com/suryateja963/ST-ROTO/releases)**, download into **one folder**:

   | File | |
   |---|---|
   | `ST-ROTO-Setup.exe` | the installer (required) |
   | `ST-ROTO-<version>.zip` | ST-ROTO and the SAM 2.1 tiny model (required) |
   | `ST-ROTO-model-sam2.1-hiera-large.zip` | the more accurate large model (recommended) |
   | `ST-ROTO-model-vitmatte-small-composition-1k.zip` | learned soft edges (optional; its weights were trained on Adobe's Composition-1k data, whose terms are reported to be non-commercial: see `NOTICE`) |

   To check the files, compare their SHA-256 with the release notes. In PowerShell: `Get-FileHash <file>`.
2. **Close Nuke.**
3. Double-click `ST-ROTO-Setup.exe`. Windows SmartScreen may warn that the program isn't signed; choose **More info → Run anyway**.
4. The window shows the current status and a menu. Type **1** and press Enter. The setup then:
   - checks every file of every package against its SHA-256 (a damaged package installs nothing);
   - copies ST-ROTO to `%LOCALAPPDATA%\ST-ROTO\<version>\`, so no administrator rights are needed;
   - installs every model package lying next to it, after checking that the model belongs to this version;
   - adds **one marked block** to `%USERPROFILE%\.nuke\init.py`, between `# >>> ST-ROTO >>>` and `# <<< ST-ROTO <<<`. Nothing else in that file changes.
5. Press Enter to close, then start Nuke.

**Nothing is downloaded during installation, and ST-ROTO never uses the network.** It works on machines without internet access, and with Nuke blocked by a firewall.

**Copying to another computer.** Copy the same files, in one folder, to the other machine and run the setup there. It installs for the Windows user who runs it; other users on that machine run it too.

## 4. Check the installation

1. In Nuke, check that **Nodes › ST-ROTO** contains **ST_Roto**, **ST_RotoMatte** and **ST_RotoOutput**, and that the main menu has an **ST-ROTO** entry.
2. **ST-ROTO › System report…** shows the Nuke edition and its limits, the GPU, which AI runtime is active and why, the installed models, and whether each fits in GPU memory.
3. **Windows › Custom › ST-ROTO Models** offers **Verify** (SHA-256 of every model file) and **Self-test** (tracks a generated test image and reports accuracy and speed).
4. Run a quick track on any shot (`docs/MANUAL.md`, section 4).

## 5. Update, add a model, roll back, repair, uninstall

Run `ST-ROTO-Setup.exe` again, from the folder holding the packages:

| Choice | Effect |
|---|---|
| **1** install / upgrade | Installs the newer `ST-ROTO-<version>.zip` (and any model packages) as a new version and switches Nuke to it. The previous version is kept. Models you installed separately are carried over when the new version expects exactly the same files. |
| **2** repair | Re-checks every installed file and re-copies the damaged or missing ones from the package (and from the model packages next to it). |
| **3** roll back | Switches Nuke back to the previously active version. |
| **4** uninstall | Removes ST-ROTO's files and only its block in `init.py`. An `init.py` that contained nothing else is removed. Your projects, mattes and presets are not touched. |

Restart Nuke after 1, 3 or 4.

**Command line** (scripts, deployment). Use the same .exe, or `st_roto_setup.py` with Nuke's own `python.exe`:

```
ST-ROTO-Setup.exe status
ST-ROTO-Setup.exe install --source ST-ROTO-<version>.zip        (also installs ST-ROTO-model-*.zip next to it;
                                                                  --no-model-packages to skip them)
ST-ROTO-Setup.exe install-model --source ST-ROTO-model-<name>.zip   (into the active version)
ST-ROTO-Setup.exe upgrade --source <newer zip>
ST-ROTO-Setup.exe rollback | repair [--source <zip>] | uninstall [--keep-files]
options: --base <install folder>  (default %LOCALAPPDATA%\ST-ROTO)   --home <folder holding .nuke>  (default %USERPROFILE%)
```

## 6. Studios (untested)

There is no studio-wide installer yet. These approaches follow from how the setup works but **have not been tested**:

- **One shared copy:**
  1. Install once into a shared folder: `ST-ROTO-Setup.exe install --source <zip> --base \\server\pipeline\ST-ROTO --home <a scratch folder>`.
  2. Point each artist's Nuke at it by adding the active version's `nuke_plugin` folder to `NUKE_PATH`, or with `nuke.pluginAddPath("//server/pipeline/ST-ROTO/<version>/nuke_plugin")` in a studio `init.py`.

  Every file is verified at install time. The model registry re-checks model files when they are loaded.
- **Models in a studio location.** Set `ST_ROTO_MODELS_STUDIO` to a shared folder holding `onnx/<model>/` and `manifests/` (laid out like the install). A per-user `ST_ROTO_MODELS_USER` wins over the studio folder, which wins over the built-in copy. The Models pane shows where each model comes from.
- **Presets for everyone:** set `ST_ROTO_PRESET_DIR` to a shared folder.
- **Machines without NVIDIA:** nothing to do. The DirectML runtime is chosen automatically. Use `ST_ROTO_RUNTIME` to force `cuda` or `directml`.
- **No AI at all**, for example on render or review machines: set `ST_ROTO_AI=off`. Traditional roto, mattes and exports keep working.

## 7. Developer install (from the repository)

Clone the repository and add `nuke.pluginAddPath("<repo>/nuke_plugin")` to `~/.nuke/init.py`. Don't combine this with an installed copy, or Nuke loads ST-ROTO twice.

The repository holds code only. Two things have to be built separately: the Python packages that run inside Nuke (`.tools/nuke-py311`) and the model exports (`models/onnx`). See `docs/DEVELOPER_GUIDE.md`, section 3.

## 8. Problems

| Symptom | Check |
|---|---|
| No ST-ROTO menu | Run `ST-ROTO-Setup.exe status`. Check that `init.py` has the block, and look in Script Editor for errors. Try **2** (repair). |
| "package damaged, nothing installed" | The download is incomplete: download it again and compare SHA-256. |
| "this ST-ROTO version does not know the model …" / "does not match" | The model package belongs to another ST-ROTO version: download the one from the same release. |
| Status says *device cpu* / *FALLBACK* | Open the **System report**. On NVIDIA, update the driver (CUDA 12). Otherwise check `ST_ROTO_RUNTIME`. |
| "files are still in use (virus scanner?)" | Run the same command again. A scanner briefly locks newly copied files. |
| Windows SmartScreen warning | The setup isn't code-signed yet (known defect DEF-009). |

When reporting a problem, include the output of `ST-ROTO-Setup.exe status`, the **System report** and the Script Editor output.
