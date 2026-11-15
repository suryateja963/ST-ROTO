"""Generates docs/adr/ADR-*.md (Phase 2 proposals). Edit the ADR text here, re-run to regenerate."""
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(ROOT, "docs", "adr")
P = "research/probes/2026-11-15_"

ADRS = [
 ("0001", "In-process inference with ONNX Runtime inside Nuke's Python",
  "§5.3 requires AI to run inside the Nuke process. Options: (A) Nuke's Inference node + `.cat` (TorchScript), (B) C++ NDK node + ONNX Runtime C++, (C) ONNX Runtime Python package in Nuke's interpreter, (D) C++ node on Nuke's bundled libtorch.",
  "Use (C) now: `onnxruntime-gpu` loaded into Nuke's Python, pinned per Nuke line to the build matching Nuke's CUDA major, reusing Nuke's own CUDA/cuDNN DLLs. Add (B) later for commercial editions (D-011) behind the same AI-layer interface.",
  f"C runs on Nuke 17.1 NC with CUDA, coexists with libtorch, ships no NVIDIA DLLs ({P}gpu_ort). ORT 1.27+ needs CUDA 13 and silently falls back to CPU on Nuke 17.1. A cannot hold interactive prompts or video memory. B and D cannot run on NC.",
  "Per-Nuke-line runtime pins and a CI check of provider DLL imports. Python-side pixel transfer cost (measured ~26–90 ms/frame) until an in-memory or C++ path exists. Silent CPU fallback must be detected and reported to the artist (§4)."),
 ("0002", "Models as ONNX graphs + numpy orchestration (no PyTorch at runtime)",
  "SAM 2.1 video needs stateful memory logic. Shipping PyTorch into Nuke adds GBs, a second CUDA stack and ABI risk.",
  "Each model is exported to a small set of ONNX graphs (pure neural blocks with dynamic shapes where needed); all state and control logic is plain numpy in the model adapter. Every export is verified against the upstream PyTorch implementation, component by component and end to end.",
  f"SAM 2.1 image and video ported this way: component max diff ≤ 1.9e-4, per-frame mask IoU vs PyTorch ≥ 0.99997 over 48 frames ({P}video).",
  "Each new model costs porting work and needs a reference test. Upstream behaviour changes must be tracked by pinning the reference library version (transformers 5.23 today)."),
 ("0003", "Host adapter per Nuke API generation, with a node-budget guard",
  "Nuke 13–17 differ in Python, Qt and API details. Non-commercial and Indie cap Python at 10 Node objects (measured: later accesses return None).",
  "All Nuke calls go through `st_roto_nuke` adapters: pixel I/O, native Roto read/write (tangent rule, key-before-append rule), viewer hooks, node creation. A budget guard counts node accesses on restricted editions and refuses an operation that would exceed the cap, with a clear message.",
  f"10-node cap and its failure mode measured (`docs/MACHINE_AUDIT_2026-11-15.md`). Roto pitfalls measured ({P}bezier, {P}video).",
  "Core code stays Nuke-free and unit-testable. Each pitfall gets a per-version regression test (R-32, R-33)."),
 ("0004", "Domain model: objects with multiple representations and provenance",
  "§6, §8 and §10 require identity, hierarchy, several geometry types, artist control and history. The video probe showed one object can split into several pieces (frame 23).",
  "Project ▸ Shot ▸ Object (tree). An Object owns any number of ShapeTracks (each a keyed spline with constant topology), MaskTracks and MatteTracks. Every element carries provenance (ai_generated / imported_native / artist_created / artist_modified_ai / locked + model id, revision, parameters). Artist corrections are stored as operations layered over AI output, never as overwrites.",
  f"Split-object failure: a single shape reached IoU 0.558 on the split frame ({P}video).",
  "Exporters must map multi-shape objects to Roto layers. Re-running AI merges under locked and artist-modified data instead of replacing it (REQ-042)."),
 ("0005", "Storage: SQLite project database + content-addressed cache",
  "§18 requires transactions, autosave, crash recovery, snapshots, relinking, portable packages and a separation of essential versus regenerable data. Nuke scripts are a poor database (size, merge conflicts, no transactions).",
  "One SQLite file per project (WAL, schema migrations) for essential state and the operation log. A content-addressed cache directory (hash of source frame + model revision + parameters) for regenerable data. The ST-ROTO node stores only the project id and path.",
  "SQLite ships with Python's standard library in every Nuke version (sqlite3 present in Nuke 17.1's lib, audit).",
  "Two sources of truth to keep in sync (script link ↔ DB). Concurrent multi-process access relies on SQLite locking until the collaboration design (D-022) adds a sync layer."),
 ("0006", "Every edit is an operation (command bus + operation log)",
  "Undo/redo, corrections that survive AI re-runs, autosave, audit history and future collaboration (D-022..D-025) all need the same thing: an ordered, attributed record of changes.",
  "All mutations go through commands that produce immutable operations (who, when, what, before/after refs) appended to the log in the same transaction as the state change. State can be rebuilt from snapshots plus the log.",
  "Design argument. Not yet prototyped.",
  "More upfront structure. Enables D-023 (keep both versions, owner picks) without redesign. Log compaction will be needed for long projects."),
 ("0007", "Hardware-aware model routing with measured VRAM tables",
  "§4 targets machines from CPU-only to large GPUs. Measured on 8 GB: SAM 2.1 large tracking peaks at 7.8 GB, tiny at 4.8 GB. Large was not better on the synthetic occlusion shot.",
  "Each model adapter ships a measured table (model × task × resolution → VRAM, time). The router picks the best model that fits the detected free VRAM with a safety margin, falls back down a chain (large → small → tiny → CPU) and always tells the artist what ran and why. The artist can override.",
  f"{P}sam2 and {P}video measurements; R-34, R-35.",
  "Tables must be measured per GPU class and kept current. Defaults are chosen from benchmarks (§21), not model size."),
 ("0008", "Geometry engine independent of Nuke; Nuke conventions in the adapter",
  "Fitting, conversions and booleans must be testable and reusable for every exporter. Nuke's Roto conventions are specific and were found by experiment.",
  "`st_roto.geometry` holds pure-numpy algorithms (adaptive Schneider fitting for static shapes, fixed-count fitting with correspondence for animated shapes, conversions). Nuke specifics (y-up, pixel-centre +0.5, tangent = 2 × handle, leftTangent → previous point) live only in the Nuke exporter.",
  f"Static Bézier IoU 0.9957 with 20 points; animated 16-anchor shape ~0.98–0.99 ({P}bezier, {P}video). 7 unit tests.",
  "Exporters for Silhouette/Mocha/SVG reuse the same geometry. Conventions are re-verified per Nuke version."),
 ("0009", "Background jobs with a single GPU arbiter",
  "§14 requires Nuke to stay usable during processing, plus pause/resume/cancel/priority. 8 GB cards cannot hold two large models at once.",
  "A job scheduler runs AI work on worker threads. One GPU arbiter serialises GPU sessions and unloads models under memory pressure. Results reach Nuke only through main-thread command application. Propagation checkpoints tracker state per chunk for resumability.",
  "Headless runs measured. GUI threading NOT yet tested (assumption).",
  "Must be prototyped in the Nuke GUI early: Nuke's Python threading rules and ORT CUDA on a worker thread are the main unknowns."),
 ("0010", "Explicit, recorded colour transform for model input (OCIO)",
  "§13.1: respect Nuke colour management, never silently alter colour; model conversions must be documented, reproducible and inspectable. The probes hard-coded an sRGB re-encode.",
  "Each model adapter declares its expected input space. The transform from the shot's working space is done with PyOpenColorIO (shipped with Nuke, audit) using the script's OCIO config, recorded in provenance, viewable by the artist, and applied only to the model input, never to outputs.",
  "PyOpenColorIO present in Nuke 17.1 site-packages (audit). Linear→sRGB round trip matched the source PNG to 1.2e-7 in the SAM probe.",
  "Per-adapter colour metadata. Needs tests with ACES and other configs."),
]


def main():
    os.makedirs(OUT, exist_ok=True)
    index = ["# Architecture Decision Records", "", "All **Proposed** (2026-11-15). None approved yet. See `ARCHITECTURE.md`.", "",
             "| ADR | Title | Status |", "|---|---|---|"]
    for num, title, ctx, dec, evid, cons in ADRS:
        fn = f"ADR-{num}.md"
        with open(os.path.join(OUT, fn), "w", encoding="utf-8", newline="\n") as f:
            f.write(f"# ADR-{num}: {title}\n\n**Status:** Proposed (2026-11-15) · **Decider:** project owner\n\n"
                    f"## Context\n{ctx}\n\n## Decision (proposed)\n{dec}\n\n## Evidence\n{evid}\n\n## Consequences\n{cons}\n")
        index.append(f"| [ADR-{num}]({fn}) | {title} | Proposed |")
    with open(os.path.join(OUT, "README.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(index) + "\n")
    print("wrote", len(ADRS), "ADRs")


if __name__ == "__main__":
    main()
