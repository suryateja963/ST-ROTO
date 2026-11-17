# T-085 — Fully local operation (REQ-140, master prompt §16), 2026-11-17

**Question.** Does ST-ROTO use the network, send telemetry, or transmit anything automatically?

## Evidence

| layer | method | result |
|---|---|---|
| Product code (static) | `tests/unit/test_offline.py`: AST scan of `src/` + `nuke_plugin/` for 24 network modules (socket, ssl, http, urllib, requests, asyncio, webbrowser, huggingface_hub, ...) | none imported; `socket` only in `st_roto/persistence.py`, only `socket.gethostname()` (local, session marker); enforced in CI |
| ONNX Runtime telemetry | the bundled `onnxruntime.dll` (1.26.0, official Windows build) contains Microsoft's TraceLogging provider `Microsoft.ML.ONNXRuntime`, which emits usage events through ETW **by default**; Windows may forward them depending on its diagnostic-data settings | **was not disabled before T-085** (gap). Now `st_roto_ai.runtime` calls `ort.disable_telemetry_events()` at import, before any session; unit test requires it in every product module importing ORT; Nuke test confirms `TELEMETRY_DISABLED == True` |
| Python inside Nuke (behavioural) | `tests/nuke/run_nuke_tests.py::test_offline_no_network`: `sys.addaudithook` records every socket creation/bind/connect/send, DNS lookup, urllib/http/ftp/smtp/webbrowser event with its stack, during: node, 2 prompts, Load model, Track (CUDA, 6 frames × 2 objects), soft mattes (EXR), JSON/SVG export, backup, package | **0 events**, test passes (`tests/nuke/out/results_test_offline_no_network.json`) |
| OS connection table (native code included) | `tools/offline/watch_network.py`: launches Nuke, polls the Windows TCP/UDP tables for the Nuke process tree every 0.05 s | see below |

### OS-level: Nuke itself contacts a server at start-up

| run | duration | external connections |
|---|---|---|
| baseline: `Nuke17.1.exe --nc -t empty_script.py` (no ST-ROTO) | 4.2 s | 2 × TCP 443 to 54.73.130.128 (`ec2-…eu-west-1.compute.amazonaws.com`), at 0.3–2.2 s |
| baseline repeated (`watch_baseline_2.json`) | 3.2 s | 1 × TCP 443 to 54.73.130.128 **and** 1 × to 34.241.207.160: both addresses are Nuke's own |
| ST-ROTO workflow (the Nuke test above) | 16.6 s | 2 × TCP 443 to 34.241.207.160 (AWS, reverse DNS timed out), at 0.25–1.95 s |

Both runs show the same pattern: two short HTTPS connections during Nuke's start-up, before the Python script
runs, with or without ST-ROTO. Nothing else external during the 14 s of tracking, mattes, export and packaging.
The machine's own LAN address is redacted (`<local>`). Loopback connections (127.0.0.1, Nuke-internal) are listed in the JSON files and are not transmission.

**Attribution (not proven):** Nuke 17.1 **Non-commercial** itself, presumably its licence / registration check
(Foundry's NC licence is tied to an account). ST-ROTO cannot and does not influence it. Not measured: a
commercial Nuke licence, interactive (GUI) Nuke, and whether Nuke NC still starts with this traffic blocked
(needs a firewall rule or the network off: owner's decision, OQ-26).

## Conclusions

1. ST-ROTO's own code makes no network access in the measured workflow (static + Python audit hook) and now
   switches off ONNX Runtime's default Windows telemetry (fixed in this task).
2. "Fully local" for the whole stack also depends on the host: Nuke NC contacts an AWS server at every start.
   Recorded as R-45; the user guide says so.

## Limitations

- Polling can miss connections shorter than 0.05 s; the Python hook cannot see native code (ORT, CUDA, OpenEXR,
  OpenCV): the OS table covers those, within the polling limit.
- ETW events are handed to a Windows service, not sent by the process: they cannot be seen in Nuke's connection
  table. The fix (disable call) is verified; the absence of events in ETW was not traced.
- Not covered by the workflow: ViTMatte mattes, Re-track, collaboration sync (file transport, no network code),
  the model download tool (`tools/models/download_models.py`, deliberately online, owner-run, not product code).

Files: `results_test_offline_no_network.json`, `watch_baseline.json`, `watch_baseline_2.json`, `watch_st_roto_workflow.json`, `empty_script.py`; tool `tools/offline/watch_network.py`.
