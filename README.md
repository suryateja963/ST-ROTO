# ST-ROTO

AI-assisted **and** traditional rotoscoping inside Foundry Nuke. Free and open source (Apache License 2.0).

Click on an object (or draw a box around it) on one frame, press **Track**, and ST-ROTO tracks it through the shot with
SAM 2.1, running locally on your graphics card inside Nuke. The result is **native, animated Nuke Roto shapes** you can
edit like any other shape, plus EXR mattes. Every AI feature can be switched off for traditional roto.

> **Pre-release 0.1.0: not production-ready.** Tested only on Nuke 17.1 Non-commercial on Windows with an NVIDIA
> RTX GPU, on synthetic test shots and public benchmark footage - not yet on a real production shot. Please report
> problems.

"Nuke" is a trademark of The Foundry Visionmongers Ltd. ST-ROTO is not affiliated with or endorsed by Foundry.

## Install

1. Open **[Releases](https://github.com/suryateja963/ST-ROTO/releases)** and download from the latest release into
   **one folder**:
   - `ST-ROTO-Setup.exe` - the installer
   - `ST-ROTO-0.1.0.zip` - ST-ROTO with the fast SAM 2.1 tiny model
   - `ST-ROTO-model-sam2.1-hiera-large.zip` - the more accurate large model (recommended)
   - `ST-ROTO-model-vitmatte-small-composition-1k.zip` - learned soft edges (optional; read its licence note below)
2. Close Nuke and double-click `ST-ROTO-Setup.exe`. Windows SmartScreen may warn that the program is not signed:
   **More info > Run anyway**.
3. Type **1** and press Enter. Everything in the folder is installed and checked (SHA-256 of every file); no
   administrator rights, nothing is downloaded. Files go to `%LOCALAPPDATA%\ST-ROTO`, and one marked block is added to
   `%USERPROFILE%\.nuke\init.py`.
4. Start Nuke: **Nodes > ST-ROTO > ST_Roto**. **ST-ROTO > System report...** shows what your machine can do.

The same `ST-ROTO-Setup.exe` repairs (2), rolls back to the previous version (3) and uninstalls (4) - uninstalling
removes only ST-ROTO's files and its block in `init.py`.

**Requirements:** Windows 10/11 64-bit; Nuke 17.1 (Nuke 16 / 17.0 use the same Python 3.11 but are untested; Nuke 15
and older are not supported by this package); a graphics card for fast tracking: NVIDIA (CUDA 12, fastest) or, from the next release, AMD / Intel via
DirectML - without one ST-ROTO runs on the CPU (slow). The large model needs ~7 GB of free GPU memory; with *model = auto* ST-ROTO uses
it where it fits and the tiny model elsewhere.

## Use

Read the **[manual](docs/MANUAL.md)** (quick version: [user guide](docs/USER_GUIDE_v0.md)). In short: select your Read node, create **ST_Roto**, type an object
name, set a box and/or include click on the object, press **Load model** then **Track**. Fix frames with
**Re-prompt here** or by editing the shape and pressing **Re-track object**; your own keys are never overwritten.
**Render mattes (EXR)**, **Export shapes**, **Export Alembic**, **Delivery package** hand the work on.

Also: several objects per node, holdout / garbage roles, stereo and multi-camera, Cryptomatte and motion-vector tools
for CG plates, scene-cut detection and AMD / Intel GPUs via DirectML (both from the next release; 0.1.0 has neither), edge decontamination and despill, project backups and crash recovery, model manager.

## Licences

ST-ROTO's own code: Apache License 2.0 (`LICENSE`). The release downloads also contain third-party models and Python
packages under their own licences, listed in `NOTICE` (SAM 2.1: Apache-2.0; ONNX Runtime: MIT; numpy, OpenCV,
OpenEXR, protobuf and others: BSD / Apache). **ViTMatte** weights are Apache-2.0 but were trained on Adobe's
Composition-1k data, whose terms are reported to be non-commercial: decide whether that suits your use before
installing `ST-ROTO-model-vitmatte-small-composition-1k.zip` (it is optional; the default edges use no learned
model). No NVIDIA software is included: ST-ROTO uses the CUDA libraries that ship with Nuke.

## Status and evidence

- What is done and what is missing for 1.0: [`docs/ACCEPTANCE.md`](docs/ACCEPTANCE.md) (20 criteria; 3 met, 16 partly,
  1 not met: compatibility beyond Nuke 17.1 Non-commercial).
- Known defects: [`DEFECTS.md`](DEFECTS.md). Every measured claim has its evidence in `research/probes/*/RESULTS.md`.
- Owner's specification: `docs/MASTER_PROMPT.md`. Registers: `REQUIREMENTS_REGISTER.md`, `DECISION_REGISTER.md`,
  `RISK_REGISTER.md`, `MODEL_REGISTER.md`, `LICENCE_REGISTER.md`, `COMPATIBILITY_MATRIX.md`, `TASK_BOARD.md`,
  `DEVELOPMENT_LOG.md`.

## Build from source (developers)

Start with the **[developer guide](docs/DEVELOPER_GUIDE.md)**. 
The repository holds the code only; model files and the Python packages used inside Nuke are not committed. Developer
set-up and the model export pipeline: `CLAUDE.md` (Commands) and `tools/models/`. Release files are built with
`tools/installer/st_roto_setup.py package` / `package-model` and `tools/installer/build_exe.py`.
