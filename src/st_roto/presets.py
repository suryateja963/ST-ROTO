"""Settings presets for the ST_Roto node (T-111, REQ-120/REQ-121 'presets'). Pure Python.

A preset is a named set of NODE SETTINGS (model, edges, matte options, channels to check, ...), never shot data
(prompts, object names, frame ranges, project or output paths). Files are JSON:
    {"format": "st_roto.preset", "version": 1, "name": ..., "description": ..., "settings": {knob: value}}
Locations, highest priority first (a preset name found in several places uses the first):
    user    ST_ROTO_USER_PRESET_DIR, else %USERPROFILE%/.st_roto/presets (created when the artist saves one)
    studio  ST_ROTO_PRESET_DIR (several folders separated by os.pathsep; read-only for ST-ROTO)
    builtin BUILTIN below (shipped with ST-ROTO)
"""
from __future__ import annotations

import json
import os
import re

FORMAT, VERSION = "st_roto.preset", 1

# knob -> type ("bool", "int", "float", "str", "choice"). Choices are validated against the node's knob when applied.
SETTINGS = {
    "stroto_model": "choice", "stroto_device": "choice", "stroto_anchors": "choice",
    "stroto_retrack_model": "choice", "stroto_colour": "choice", "stroto_ai_off": "bool",
    "stroto_edges": "choice", "stroto_soft": "bool", "stroto_band": "int", "stroto_radius": "int",
    "stroto_matte_size": "choice", "stroto_rgb_mode": "choice", "stroto_spill": "choice", "stroto_offset": "int", "stroto_edge_blur": "float",
    "stroto_core_edge": "int", "stroto_stereo": "bool",
    "stroto_ch_stats": "str", "stroto_ch_motion": "str", "stroto_ch_motion_back": "str",
    "stroto_ch_motion_conv": "choice", "stroto_ch_crypto": "str",
    "stroto_review_colours": "bool", "stroto_replace_alpha": "bool",
    "stroto_mb_mode": "choice", "stroto_mb_samples": "int", "stroto_mb_shutter": "float", "stroto_mb_offset": "choice",
}

BUILTIN = {
    "Quick look": {
        "description": "Fastest: tiny model, hard matte edges, mattes fitted to 1920x1080.",
        "settings": {"stroto_model": "sam2.1-hiera-tiny", "stroto_retrack_model": "same as model",
                     "stroto_anchors": "auto", "stroto_edges": "hard", "stroto_matte_size": "fit 1920x1080"}},
    "Final quality": {
        "description": "Large model for re-tracks (measured +0.045 IoU on real footage, T-080), guided soft edges, "
                       "full-resolution mattes.",
        "settings": {"stroto_model": "sam2.1-hiera-tiny", "stroto_retrack_model": "sam2.1-hiera-large",
                     "stroto_anchors": "auto", "stroto_edges": "guided filter", "stroto_soft": True,
                     "stroto_matte_size": "full resolution"}},
    "Traditional roto (AI off)": {
        "description": "Every AI control hidden; hand-drawn shapes, guided soft or hard mattes.",
        "settings": {"stroto_ai_off": True, "stroto_edges": "guided filter"}},
    "CG plate with passes": {
        "description": "Checks shapes against depth.Z, forward/backward motion vectors (convention measured) and "
                       "Cryptomatte; review colours on; the node replaces the plate's alpha.",
        "settings": {"stroto_ch_stats": "depth.Z", "stroto_ch_motion": "forward", "stroto_ch_motion_back": "backward",
                     "stroto_ch_motion_conv": "auto (measure)", "stroto_review_colours": True,
                     "stroto_replace_alpha": True}},
    "Stereo": {
        "description": "Tracks every view of a stereo script (prompts in the prompt view).",
        "settings": {"stroto_stereo": True}},
}

_NAME_OK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.()+-]{0,63}$")


def user_dir() -> str:
    d = os.environ.get("ST_ROTO_USER_PRESET_DIR")
    if d:
        return d
    return os.path.join(os.path.expanduser("~"), ".st_roto", "presets")


def studio_dirs() -> list:
    return [d for d in os.environ.get("ST_ROTO_PRESET_DIR", "").split(os.pathsep) if d]


def file_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("_") + ".json"


def validate(settings: dict) -> tuple:
    """-> (clean settings, [problems]). Unknown knobs and values of the wrong type are dropped and reported."""
    clean, problems = {}, []
    for k, v in (settings or {}).items():
        t = SETTINGS.get(k)
        if t is None:
            problems.append("%s: not a preset setting (ignored)" % k); continue
        ok = ((t == "bool" and isinstance(v, bool)) or
              (t == "int" and isinstance(v, int) and not isinstance(v, bool)) or
              (t == "float" and isinstance(v, (int, float)) and not isinstance(v, bool)) or
              (t in ("str", "choice") and isinstance(v, str)))
        if not ok:
            problems.append("%s: expected %s, got %r (ignored)" % (k, t, v)); continue
        clean[k] = float(v) if t == "float" else v
    return clean, problems


def _read(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        d = json.load(fh)
    if d.get("format") != FORMAT:
        raise ValueError("%s is not an ST-ROTO preset" % path)
    if int(d.get("version", 0)) > VERSION:
        raise ValueError("%s was written by a newer ST-ROTO (preset version %s)" % (path, d.get("version")))
    return d


def list_presets() -> list:
    """[{"name", "origin": "user"|"studio"|"builtin", "description", "path"}] - one entry per name, highest
    priority origin first; unreadable files are listed with an "error"."""
    seen, out = set(), []
    places = [("user", user_dir())] + [("studio", d) for d in studio_dirs()]
    for origin, d in places:
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.lower().endswith(".json"):
                continue
            p = os.path.join(d, fn)
            try:
                data = _read(p)
                name = str(data.get("name") or fn[:-5])
                entry = {"name": name, "origin": origin, "description": data.get("description", ""), "path": p}
            except (ValueError, OSError) as e:
                name, entry = fn[:-5], {"name": fn[:-5], "origin": origin, "description": "", "path": p,
                                        "error": str(e)}
            if name not in seen:
                seen.add(name); out.append(entry)
    for name, data in BUILTIN.items():
        if name not in seen:
            seen.add(name)
            out.append({"name": name, "origin": "builtin", "description": data["description"], "path": None})
    return out


def load(name: str) -> dict:
    """{"name", "origin", "description", "settings", "problems"} of the highest-priority preset called `name`."""
    for e in list_presets():
        if e["name"] != name:
            continue
        if e.get("error"):
            raise ValueError(e["error"])
        data = BUILTIN[name] if e["origin"] == "builtin" else _read(e["path"])
        clean, problems = validate(data.get("settings", {}))
        return {"name": name, "origin": e["origin"], "description": data.get("description", ""), "settings": clean,
                "problems": problems}
    raise KeyError("no preset named %r" % name)


def save(name: str, settings: dict, description: str = "", directory: str = None) -> str:
    """Write a user preset (or into `directory`); replaces a user preset of the same name. Returns the path."""
    if not _NAME_OK.match(name or ""):
        raise ValueError("preset name: letters, digits, space and _ . ( ) + - only, at most 64 characters")
    clean, problems = validate(settings)
    if problems:
        raise ValueError("; ".join(problems))
    d = directory or user_dir()
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, file_name(name))
    tmp = path + ".part"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"format": FORMAT, "version": VERSION, "name": name, "description": description,
                   "settings": clean}, fh, indent=1, sort_keys=True)
    os.replace(tmp, path)
    return path


def delete(name: str) -> str:
    """Delete a USER preset; studio and built-in presets cannot be deleted from here. Returns the removed path."""
    for e in list_presets():
        if e["name"] == name:
            if e["origin"] != "user":
                raise ValueError("%r is a %s preset: only your own presets can be deleted" % (name, e["origin"]))
            os.remove(e["path"])
            return e["path"]
    raise KeyError("no preset named %r" % name)
