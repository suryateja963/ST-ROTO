"""Download owner-approved model weights into D:/ST-ROTO/models/weights (git-ignored).

Approval: decision D-015 (SAM 2.1 tiny/small etc.) and owner request 2026-11-15 (SAM 2.1 large).
Each download is pinned to the exact Hugging Face commit and every file's SHA-256 is written to
models/manifests/<name>.json, which IS committed (provenance, master prompt sections 15 and 24).

Usage:  .venv\\Scripts\\python.exe tools/models/download_models.py sam2.1-hiera-tiny sam2.1-hiera-large
"""
import hashlib, json, os, sys, datetime

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
os.environ["HF_HOME"] = os.path.join(ROOT, ".tools", "hf-home")          # keep caches inside the project
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
from huggingface_hub import HfApi, snapshot_download  # noqa: E402

CATALOGUE = {
    "sam2.1-hiera-tiny":  {"repo": "facebook/sam2.1-hiera-tiny",  "licence": "apache-2.0", "approval": "D-015"},
    "sam2.1-hiera-small": {"repo": "facebook/sam2.1-hiera-small", "licence": "apache-2.0", "approval": "D-015"},
    "sam2.1-hiera-large": {"repo": "facebook/sam2.1-hiera-large", "licence": "apache-2.0", "approval": "owner request 2026-11-15"},
    # D-032: optional learned matting; weights Apache-2.0, trained on Composition-1k (Adobe DIM terms: caveat shown)
    "vitmatte-small-composition-1k": {"repo": "hustvl/vitmatte-small-composition-1k", "licence": "apache-2.0", "approval": "D-032"},
}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(name):
    spec = CATALOGUE[name]
    info = HfApi().model_info(spec["repo"])
    card_licence = (info.card_data or {}).get("license") if info.card_data else None
    if card_licence != spec["licence"]:
        raise SystemExit(f"{name}: card licence {card_licence!r} != expected {spec['licence']!r}; stopping")
    dest = os.path.join(ROOT, "models", "weights", name)
    snapshot_download(spec["repo"], revision=info.sha, local_dir=dest)
    files = {}
    for dp, _, fns in os.walk(dest):
        for fn in fns:
            p = os.path.join(dp, fn)
            if os.sep + ".cache" + os.sep in p:
                continue
            files[os.path.relpath(p, dest).replace("\\", "/")] = {"bytes": os.path.getsize(p), "sha256": sha256(p)}
    manifest = {
        "name": name, "repo": spec["repo"], "revision": info.sha, "licence": card_licence,
        "approval": spec["approval"], "downloaded_utc": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "files": files,
    }
    os.makedirs(os.path.join(ROOT, "models", "manifests"), exist_ok=True)
    with open(os.path.join(ROOT, "models", "manifests", name + ".json"), "w") as f:
        json.dump(manifest, f, indent=1)
    total = sum(v["bytes"] for v in files.values())
    print(f"{name}: revision {info.sha[:10]}, {len(files)} files, {total/1e6:.1f} MB")


if __name__ == "__main__":
    for n in sys.argv[1:]:
        fetch(n)
