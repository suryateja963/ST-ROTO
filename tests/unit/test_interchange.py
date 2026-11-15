"""ST-ROTO JSON and SVG interchange (master prompt section 20)."""
import json
import re
import xml.etree.ElementTree as ET

import pytest

from st_roto import interchange
from st_roto import model as m
from st_roto.commands import CommandBus, ProtectedError
from st_roto.store import ProjectStore

P3 = [[10, 10, 8, 12, 12, 8], [50, 10, 48, 8, 52, 12], [30, 40, 34, 40, 26, 40]]


def _project(tmp_path, name):
    s = ProjectStore(str(tmp_path / name)); bus = CommandBus(s)
    bus.execute({"op": "create_shot", "row": {"id": "S", "name": "sh010", "width": 64, "height": 48,
                                              "first_frame": -2, "last_frame": 5}})
    return s, bus


def _populate(s, bus):
    bus.execute({"op": "create_object", "row": {"id": "P", "shot_id": "S", "name": "person", "color": "#ff0000"}})
    bus.execute({"op": "create_object", "row": {"id": "C", "shot_id": "S", "name": "hand", "parent_id": "P"}})
    bus.execute({"op": "create_shape", "row": {"id": "PS", "object_id": "P", "name": "body", "point_count": 3,
                                               "generator": json.dumps({"model": "x"})}}, actor=m.ACTOR_AI)
    bus.execute({"op": "create_shape", "row": {"id": "CS", "object_id": "C", "name": "fingers", "point_count": 3}})
    bus.execute({"op": "set_key", "shape_id": "PS", "frame": -2, "points": P3}, actor=m.ACTOR_AI)
    bus.execute({"op": "set_key", "shape_id": "PS", "frame": 3, "points": [[v + 1 for v in p] for p in P3]}, actor=m.ACTOR_AI)
    bus.execute({"op": "set_key", "shape_id": "PS", "frame": 3, "points": [[v + 2 for v in p] for p in P3]})  # artist edit
    bus.execute({"op": "set_key", "shape_id": "CS", "frame": 0, "points": P3})
    bus.execute({"op": "update_object", "id": "C", "fields": {"locked": 1}})


def test_json_roundtrip_keeps_everything(tmp_path):
    s, bus = _project(tmp_path, "a.stroto"); _populate(s, bus)
    path = str(tmp_path / "sh010.json")
    data = interchange.write_json(path, s, "S")
    assert json.load(open(path)) == json.loads(json.dumps(data))
    assert "y DOWN" in data["coordinates"] and data["shot"]["first_frame"] == -2
    person = [o for o in data["objects"] if o["name"] == "person"][0]
    origins = {k["frame"]: k["origin"] for k in person["shapes"][0]["keys"]}
    assert origins == {-2: "ai_generated", 3: "artist_modified_ai"}
    t, bus2 = _project(tmp_path, "b.stroto")
    ids = interchange.import_shot(bus2, data, "S")
    objs = {o["name"]: o for o in t.objects("S")}
    assert set(objs) == {"person", "hand"} and objs["hand"]["parent_id"] == objs["person"]["id"]
    assert objs["hand"]["locked"] == 1 and objs["person"]["color"] == "#ff0000"
    assert objs["person"]["id"] == ids["P"] != "P"                                  # new ids
    body = t.shapes(objs["person"]["id"])[0]
    keys = {k["frame"]: k for k in t.keys(body["id"])}
    assert keys[3]["points"] == [[v + 2.0 for v in p] for p in P3] and keys[-2]["points"] == [[float(v) for v in p] for p in P3]
    assert {k["origin"] for k in keys.values()} == {m.IMPORTED_NATIVE}
    gen = json.loads(body["generator"])
    assert gen["model"] == "x" and gen["imported_from"]["origin"] == "ai_generated"
    # exporting the imported project again gives the same names, structure and geometry
    def geometry(d):
        by_id = {o["id"]: o["name"] for o in d["objects"]}
        return sorted((o["name"], by_id.get(o["parent_id"]), o["locked"], s_["name"],
                       [(k["frame"], k["points"]) for k in s_["keys"]]) for o in d["objects"] for s_ in o["shapes"])
    assert geometry(interchange.export_shot(t, "S")) == geometry(json.loads(json.dumps(data)))
    # AI may not touch imported content; one undo step removes the whole import
    with pytest.raises(ProtectedError):
        bus2.execute({"op": "set_key", "shape_id": body["id"], "frame": 3, "points": P3}, actor=m.ACTOR_AI)
    bus2.undo()
    assert t.objects("S") == []
    s.close(); t.close()


def test_json_rejects_foreign_or_newer_files(tmp_path):
    s, bus = _project(tmp_path, "c.stroto")
    with pytest.raises(ValueError):
        interchange.import_shot(bus, {"format": "other"}, "S")
    with pytest.raises(ValueError):
        interchange.import_shot(bus, {"format": interchange.FORMAT, "version": 99, "objects": []}, "S")
    s.close()


def test_svg_frame_paths_are_valid_and_exact(tmp_path):
    s, bus = _project(tmp_path, "d.stroto"); _populate(s, bus)
    svg = interchange.svg_frame(s, "S", 0)
    root = ET.fromstring(svg.split("\n", 1)[1])                      # valid XML
    paths = root.findall(".//{http://www.w3.org/2000/svg}path")
    assert len(paths) == 1 and paths[0].get("data-name") == "fingers"            # only shapes keyed on frame 0
    nums = [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", paths[0].get("d"))]
    # M p0, then per segment: out-handle(a), in-handle(b), point(b)
    assert nums[:2] == P3[0][:2]
    assert nums[2:8] == [P3[0][4], P3[0][5], P3[1][2], P3[1][3], P3[1][0], P3[1][1]]
    assert paths[0].get("d").endswith("Z") and len(nums) == 2 + 6 * 3
    assert 'viewBox="0 0 64 48"' in svg
    s.close()
