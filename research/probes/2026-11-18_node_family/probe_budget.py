"""T-112 probe: how Nuke 17.1 Non-commercial counts its 10 Python-accessible Node objects (one case per process).
Run: Nuke17.1.exe --nc -t probe_budget.py <case>  -> result_budget_<case>.json
cases: plain | same_twice | del_gc | paste | gizmo | thisnode"""
import gc
import json
import os
import sys
import traceback

import nuke

HERE = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
OUT = HERE + "/out"
os.makedirs(OUT, exist_ok=True)
CASE = sys.argv[1]
R = {"case": CASE}


def remaining(limit=20):
    """How many more Node objects Python can get (creates NoOps until None)."""
    n = 0
    for _ in range(limit):
        x = nuke.nodes.NoOp()
        if x is None:
            break
        n += 1
    return n


SNIPPET = """set cut_paste_input [stack 0]
version 17.1 v3
Group {
 name FamilyTest
 addUserKnob {20 t l T}
 addUserKnob {1 note l note}
}
 Input {
  inputs 0
  name Input1
 }
 Blur {
  name inner_blur
 }
 Grade {
  name inner_grade
 }
 Output {
  name Output1
 }
end_group
"""

GIZMO = """Group {
 name STTestGizmo
 addUserKnob {20 t l T}
 addUserKnob {1 note l note}
}
 Input {
  inputs 0
  name Input1
 }
 Blur {
  name inner_blur
 }
 Grade {
  name inner_grade
 }
 Output {
  name Output1
 }
end_group
"""

try:
    if CASE == "plain":
        R["remaining_fresh"] = remaining()
    elif CASE == "same_twice":
        nuke.nodes.Blur(name="b1")                       # costs 1
        a = nuke.toNode("b1"); b = nuke.toNode("b1"); c = nuke.toNode("b1")
        R["same_object"] = a is b
        R["remaining"] = remaining()                     # 10 - 1 - ? lookups
    elif CASE == "del_gc":
        xs = [nuke.nodes.NoOp() for _ in range(5)]
        del xs
        gc.collect()
        R["remaining_after_del_5"] = remaining()
    elif CASE == "paste":
        p = OUT + "/snippet.nk"
        open(p, "w").write(SNIPPET)
        r = nuke.nodePaste(p)
        R["paste_return"] = str(r)
        R["remaining_after_paste"] = remaining()
    elif CASE == "paste_then_lookup":
        p = OUT + "/snippet.nk"
        open(p, "w").write(SNIPPET)
        nuke.nodePaste(p)
        g = nuke.toNode("FamilyTest")
        R["group_found"] = g is not None
        R["inner_names"] = None
        R["remaining_after_paste_and_lookup"] = remaining()
    elif CASE == "gizmo":
        d = OUT + "/gizmos"
        os.makedirs(d, exist_ok=True)
        open(d + "/STTestGizmo.gizmo", "w").write(GIZMO)
        nuke.pluginAddPath(d)
        g = nuke.createNode("STTestGizmo", inpanel=False)
        R["gizmo_created"] = g is not None and g.Class()
        R["gizmo_knob_note"] = "note" in g.knobs() if g is not None else None
        R["remaining_after_gizmo"] = remaining()
    elif CASE == "thisnode":
        nuke.nodes.NoOp(name="holder")
        h = nuke.toNode("holder")
        h.addKnob(nuke.PyScript_Knob("b", "b", "import nuke; nuke.thisNode()['label'].setValue('ran')"))
        for _ in range(4):
            h["b"].execute()
        R["label"] = h["label"].value()
        R["remaining_after_4_executes"] = remaining()
except Exception:
    R["error"] = traceback.format_exc()
json.dump(R, open(HERE + "/result_budget_%s.json" % CASE, "w"), indent=1)
print(R)
