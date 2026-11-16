"""Unpack an ST-ROTO package inside Nuke and relink missing plates (T-075).

`unpack_and_relink(zip, dest, choose)` holds the logic; `choose(shot, missing_path)` returns a new plate path (or
None to skip) - the menu passes a file dialog, tests pass a function. Every relinked plate is checked against the
fingerprint recorded for its shot: the same footage moved elsewhere is accepted, different footage that merely
has the same names is refused. Packaged Nuke scripts get the same path changes.
"""
from __future__ import annotations

import json
import os
import re

from st_roto import persistence
from st_roto.commands import CommandBus
from st_roto.store import ProjectStore


def sequence_pattern_from_file(path: str) -> str:
    """'D:/plates/sh010.0012.exr' -> 'D:/plates/sh010.####.exr' (last digit group before the extension)."""
    p = path.replace("\\", "/")
    m = re.match(r"^(.*?)(\d+)(\.[^./]+)$", p)
    return "%s%s%s" % (m.group(1), "#" * len(m.group(2)), m.group(3)) if m else p     # one # per padded digit


def unpack_and_relink(zip_path: str, dest_dir: str, choose, relink: dict = None) -> dict:
    out = persistence.unpack(zip_path, dest_dir, relink=relink)
    report = {"project": out["project"], "scripts": out["scripts"], "relinked": [], "refused": [], "skipped": [],
              "fingerprints": dict(out["fingerprints"]), "encrypted_scripts": out["encrypted_scripts"],
              "path_map": dict(out["path_map"])}
    if not out["missing_sources"]:
        return report
    store = ProjectStore(out["project"])
    bus = CommandBus(store, author="unpack")
    script_map = {}
    try:
        for miss in out["missing_sources"]:
            shot = store.row("shots", miss["shot_id"])
            while True:
                new = choose(shot, miss["source_path"])
                if not new:
                    report["skipped"].append(shot["name"]); break
                new = sequence_pattern_from_file(new) if os.path.isfile(new) else new.replace("\\", "/")
                try:
                    c = persistence.relink_shot(bus, shot["id"], new)
                except ValueError as e:
                    report["refused"].append((shot["name"], str(e)))
                    continue                                    # ask again
                report["relinked"].append((shot["name"], new, c["state"]))
                report["fingerprints"][shot["id"]] = c["state"]
                script_map[miss["source_path"]] = new
                break
    finally:
        store.close()
    report["path_map"].update(script_map)
    for sp in out["scripts"]:
        if sp in out["encrypted_scripts"]:
            with open(sp + persistence.RELINK_SIDECAR, "w", encoding="utf-8") as fh:
                json.dump(report["path_map"], fh, indent=1, sort_keys=True)
            continue
        with open(sp, encoding="utf-8", errors="surrogateescape") as fh:
            text = fh.read()
        with open(sp, "w", encoding="utf-8", errors="surrogateescape") as fh:
            fh.write(persistence.relink_text(text, script_map))
    return report


def apply_relink_to_open_script(mapping: dict = None, script_path: str = None) -> dict:
    """Relink the script open in Nuke: every ST_Roto node's project file and the file of the Read feeding it.
    mapping: {old prefix: new prefix}; default: the sidecar written by unpack next to `script_path` (needed for
    Non-commercial scripts, which are encrypted). Only ST_Roto groups and their inputs are touched (10-node limit
    in Non-commercial). Returns {"changed": [(node, knob, old, new)]}."""
    import nuke
    if mapping is None:
        script_path = script_path or nuke.root().name()
        side = script_path + persistence.RELINK_SIDECAR
        if not os.path.exists(side):
            return {"changed": []}
        with open(side, encoding="utf-8") as fh:
            mapping = json.load(fh)
    changed = []
    for g in nuke.allNodes("Group"):
        if "stroto_project" not in g.knobs():
            continue
        targets = [(g, "stroto_project")]
        src = g.input(0)
        if src is not None and "file" in src.knobs():
            targets.append((src, "file"))
        for node, knob in targets:
            old = node[knob].value()
            new = persistence.relink_path(old, mapping)
            if new != old:
                node[knob].setValue(new)
                changed.append((node.name(), knob, old, new))
    return {"changed": changed}


def summary(report: dict) -> str:
    lines = ["Unpacked: %s" % report["project"]]
    lines += ["Script: %s" % s for s in report["scripts"]]
    lines += ["Relinked %s -> %s (%s)" % r for r in report["relinked"]]
    lines += ["Refused for %s: %s" % r for r in report["refused"]]
    lines += ["Not relinked: %s" % s for s in report["skipped"]]
    return "\n".join(lines)


def unpack_package_ui():                                      # pragma: no cover - interactive
    import nuke
    z = nuke.getFilename("ST-ROTO package to unpack", "*.zip")
    if not z:
        return None
    dest = nuke.getInput("Unpack into this (new, empty) folder", os.path.splitext(z)[0] + "_unpacked")
    if not dest:
        return None

    def choose(shot, missing):
        return nuke.getFilename("Plates of shot '%s' not found (%s). Pick any frame of them, or cancel to skip"
                                % (shot["name"], missing))
    try:
        rep = unpack_and_relink(z, dest, choose)
    except Exception as e:
        nuke.message("ST-ROTO: unpacking failed: %s" % e)
        return None
    nuke.message(summary(rep))
    if rep["scripts"] and nuke.ask("Open the unpacked script now?\n%s" % rep["scripts"][0]):
        nuke.scriptOpen(rep["scripts"][0])
        ch = apply_relink_to_open_script(rep["path_map"])
        if ch["changed"]:
            nuke.scriptSave()
            nuke.message("Relinked in the script:\n" + "\n".join("%s.%s -> %s" % (n, k, v) for n, k, _, v in ch["changed"]))
    return rep
