"""Local PDF report: tiny vs large on the owner's green-screen shots, with the Roto outlines on the images.
Contains images of the owner's footage: written ONLY to the local results folder, never committed.
  .venv\\Scripts\\python.exe -I build_pdf.py img=<pdf_images.py output> previews=<folder> out=<pdf>"""
import json
import os
import sys

from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics.shapes import Drawing, String
from reportlab.graphics.widgets.markers import makeMarker
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

HERE = os.path.dirname(os.path.abspath(__file__))
args = dict(a.split("=", 1) for a in sys.argv[1:] if "=" in a)
IMG, PRE, OUT = args["img"], args["previews"], args["out"]
S = json.load(open(os.path.join(HERE, "summary.json")))
RES = {s: json.load(open(os.path.join(HERE, "result_%s.json" % s))) for s in S}
TILE = json.load(open(os.path.join(HERE, "result_vitmatte_tile_study.json")))
PAGE = landscape(A4)
W = PAGE[0] - 30 * mm
TINY, LARGE = colors.HexColor("#d62728"), colors.HexColor("#1f63d6")
ss = getSampleStyleSheet()
H1 = ParagraphStyle("h1", parent=ss["Heading1"], fontSize=20, spaceAfter=6)
H2 = ParagraphStyle("h2", parent=ss["Heading2"], fontSize=14, spaceBefore=4, spaceAfter=4)
BODY = ParagraphStyle("b", parent=ss["BodyText"], fontSize=9.5, leading=12.5)
SMALL = ParagraphStyle("s", parent=BODY, fontSize=8, leading=10, textColor=colors.HexColor("#444444"))
DESC = {"SHOT-112": "Close-up torso, cut off by the frame, slow movement",
        "SHOT-113": "Dancer with raised arms (encloses green: a hole), flapping fabric",
        "SHOT-114": "Torso in front; a man runs in from the right (motion blur) and stays",
        "SHOT-115": "Head and shoulders, long dark hair",
        "SHOT-116": "Head and shoulders, long hair, turning head",
        "SHOT-117": "Torso in front, a man behind gesturing",
        "SHOT-118": "Wide shot: couple close together, crew member, lights and stands in frame"}


def img(path, width):
    from reportlab.lib.utils import ImageReader
    iw, ih = ImageReader(path).getSize()
    return Image(path, width=width, height=width * ih / float(iw))


def table(data, widths, head=1, zebra=True):
    t = Table(data, colWidths=widths, repeatRows=head)
    st = [("FONT", (0, 0), (-1, -1), "Helvetica", 8.5), ("FONT", (0, 0), (-1, head - 1), "Helvetica-Bold", 8.5),
          ("BACKGROUND", (0, 0), (-1, head - 1), colors.HexColor("#22313f")),
          ("TEXTCOLOR", (0, 0), (-1, head - 1), colors.white), ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
          ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (1, 0), (-1, -1), "CENTER")]
    if zebra:
        for r in range(head, len(data)):
            if r % 2 == 0:
                st.append(("BACKGROUND", (0, r), (-1, r), colors.HexColor("#f2f4f7")))
    t.setStyle(TableStyle(st))
    return t


def chart(shot, width=W, height=58 * mm):
    d = Drawing(width, height)
    lp = LinePlot()
    lp.x, lp.y, lp.width, lp.height = 40, 22, width - 150, height - 38
    data = []
    for m in ("tiny", "large"):
        data.append([(r["frame"], r["iou_core"]) for r in RES[shot]["tracking"][m]["per_frame"]])
    lp.data = data
    lo = min(v for s in data for _, v in s)
    lp.yValueAxis.valueMin = max(0.0, min(0.95, round(lo - 0.02, 2)))
    lp.yValueAxis.valueMax = 1.0
    lp.xValueAxis.valueMin, lp.xValueAxis.valueMax = 0, max(f for f, _ in data[0])
    lp.lines[0].strokeColor, lp.lines[1].strokeColor = TINY, LARGE
    lp.lines[0].strokeWidth = lp.lines[1].strokeWidth = 1.6
    lp.lines[0].symbol, lp.lines[1].symbol = makeMarker("FilledCircle", size=2.5), makeMarker("FilledSquare", size=2.5)
    lp.lines[0].symbol.fillColor, lp.lines[1].symbol.fillColor = TINY, LARGE
    lp.xValueAxis.labels.fontSize = lp.yValueAxis.labels.fontSize = 7
    d.add(lp)
    d.add(String(lp.x + lp.width + 12, lp.y + lp.height - 6, "tiny", fillColor=TINY, fontSize=9, fontName="Helvetica-Bold"))
    d.add(String(lp.x + lp.width + 12, lp.y + lp.height - 20, "large", fillColor=LARGE, fontSize=9, fontName="Helvetica-Bold"))
    d.add(String(lp.x, 4, "frame", fontSize=7))
    d.add(String(2, lp.y + lp.height + 6, "core IoU vs keyed reference (per frame)", fontSize=7))
    return d


def build():
    doc = SimpleDocTemplate(OUT, pagesize=PAGE, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=12 * mm,
                            bottomMargin=12 * mm, title="ST-ROTO green-screen test: tiny vs large",
                            author="ST-ROTO test run")
    st = []
    st.append(Paragraph("ST-ROTO on real green-screen footage: SAM 2.1 tiny vs large", H1))
    st.append(Paragraph("7 shots, 289 frames, 4096x2160 16-bit TIFF - 2026-11-18 - ST-ROTO development build "
                        "(after release 0.1.0) in Nuke 17.1v3 Non-commercial, RTX 5060 Laptop (CUDA)", BODY))
    st.append(Spacer(1, 5))
    st.append(Paragraph(
        "<b>How it was run.</b> Every shot went through the real product: ST_Roto node, one box + one click per "
        "person, <b>Track</b> (people prompted later: <b>Re-track</b> back to frame 0), then <b>Render mattes</b>. "
        "Once with the <font color='#d62728'><b>tiny</b></font> model, once with the "
        "<font color='#1f63d6'><b>large</b></font> model. Nuke Non-commercial renders at most 1920x1080, so the AI "
        "saw every frame reduced to 1920x1012; the Roto shapes are at full 4K.", BODY))
    st.append(Paragraph(
        "<b>How it was measured.</b> There is no hand-made truth for this footage. The reference is a green-screen "
        "key made from the plates. <b>Core IoU</b> compares the shapes with the key only where the key is certain; "
        "hair, motion blur and spill edges are left out. 1.0 means a perfect match. <b>Holes-filled</b> counts green "
        "enclosed by the body (e.g. between raised arms) as foreground, because Roto shapes have no holes. "
        "<b>BF3</b> is a boundary score: the share of outline within 3 px at 2048 wide.", BODY))
    st.append(Spacer(1, 6))
    hdr = ["Shot", "Content", "Frames", "Core IoU tiny\nmean (min)", "Core IoU large\nmean (min)",
           "Holes-filled\ntiny / large", "BF3\ntiny / large", "Better"]
    rows = [hdr]
    for s, v in S.items():
        t, l = v["tracking"]["tiny"], v["tracking"]["large"]
        diff = l["iou_core_mean"] - t["iou_core_mean"]
        better = "large (+%.3f)" % diff if diff > 0.005 else ("tiny (+%.3f)" % -diff if diff < -0.005 else "equal")
        rows.append([s, Paragraph(DESC[s], SMALL), str(v["frames"]),
                     "%.4f (%.4f)" % (t["iou_core_mean"], t["iou_core_min"]),
                     "%.4f (%.4f)" % (l["iou_core_mean"], l["iou_core_min"]),
                     "%.3f / %.3f" % (t["iou_core_holes_filled_mean"], l["iou_core_holes_filled_mean"]),
                     "%.2f / %.2f" % (t["bf3_mean"], l["bf3_mean"]), better])
    st.append(table(rows, [20 * mm, 75 * mm, 14 * mm, 30 * mm, 30 * mm, 28 * mm, 24 * mm, 26 * mm]))
    st.append(Spacer(1, 6))
    st.append(Paragraph(
        "<b>In short.</b> Five of seven shots track at 0.99 with either model, and the outlines sit on top of each "
        "other. <b>SHOT-113</b> is limited by the missing holes (0.989 with the hole counted). <b>SHOT-118</b> is the "
        "one real difference: tiny loses the man's shirt and trousers on several frames (min 0.71) <b>without any "
        "review flag</b>, and large tracks him correctly (min 0.94). On the other shots large is not better.", BODY))
    st.append(PageBreak())

    for s, v in S.items():
        r = RES[s]
        t, l = r["tracking"]["tiny"], r["tracking"]["large"]
        st.append(Paragraph("%s - %s" % (s, DESC[s]), H2))
        flags = lambda m: ", ".join("%s: %s" % (o, ("lost %s" % x["lost"] if x["lost"] else "") +
                                                 (" check %s" % x["check"] if x["check"] else "") or "none")
                                    for o, x in r["tracking"][m]["review_flags"].items())
        secs = lambda m: sum(x["seconds"] for x in r["runs"][m]["steps"] if x["step"].startswith(("track", "retrack")))
        rows = [["", "tiny", "large"],
                ["core IoU mean (min)", "%.4f (%.4f)" % (t["iou_core_mean"], t["iou_core_min"]),
                 "%.4f (%.4f)" % (l["iou_core_mean"], l["iou_core_min"])],
                ["holes-filled mean (min)", "%.4f (%.4f)" % (t["iou_core_holes_filled_mean"], t["iou_core_holes_filled_min"]),
                 "%.4f (%.4f)" % (l["iou_core_holes_filled_mean"], l["iou_core_holes_filled_min"])],
                ["IoU incl. uncertain pixels", "%.4f" % t["iou_mean"], "%.4f" % l["iou_mean"]],
                ["boundary BF3", "%.3f" % t["bf3_mean"], "%.3f" % l["bf3_mean"]],
                ["frames below 0.9 core IoU", str(len(t["frames_core_below_0.9"])), str(len(l["frames_core_below_0.9"]))],
                ["review flags", Paragraph(flags("tiny"), SMALL), Paragraph(flags("large"), SMALL)],
                ["tracking time (s, 4K plate)", "%.0f" % secs("tiny"), "%.0f" % secs("large")]]
        st.append(table(rows, [60 * mm, 70 * mm, 70 * mm]))
        st.append(Spacer(1, 4))
        st.append(chart(s))
        st.append(PageBreak())
        st.append(Paragraph("%s - Roto outlines: <font color='#d62728'>tiny</font> (left) vs "
                            "<font color='#1f63d6'>large</font> (right) on the first, worst and last frame" % s, H2))
        frames = sorted(set(json.load(open(os.path.join(IMG, "index.json")))[s]["pair_frames"]))
        per_img_w = W if len(frames) <= 2 else W
        for f in frames:
            p = os.path.join(IMG, "%s_pair_f%05d.jpg" % (s, f))
            im = img(p, per_img_w * (0.62 if len(frames) == 3 else 0.80))
            st.append(KeepTogether([im, Spacer(1, 3)]))
        st.append(PageBreak())
        pv = os.path.join(PRE, "%s_10frames.jpg" % s)
        if os.path.exists(pv):
            st.append(Paragraph("%s - 10 frames across the shot (red = tiny, blue = large, thin yellow = keyed "
                                "reference)" % s, H2))
            st.append(img(pv, W))
            st.append(PageBreak())

    st.append(Paragraph("Mattes (large model, EXR at 1920x1012)", H2))
    st.append(Paragraph(
        "<b>Hair edges (SHOT-115 / 116).</b> Below: the plate, the keyed reference and the three edge methods on "
        "the outer hair line. The key is nearly binary at hair and ragged, so it <b>cannot judge hair</b>; the "
        "numbers are listed for completeness only. Visually, ViTMatte-S recovers fine stray strands that the hard "
        "shape cuts off, but also softens the clean shoulder edge. The guided filter stays close to the shape.", BODY))
    for s in ("SHOT-115", "SHOT-116"):
        p = os.path.join(IMG, "%s_hair_f00013.jpg" % s)
        if os.path.exists(p):
            st.append(Paragraph(s + ", frame 13", SMALL))
            st.append(img(p, W))
    rows = [["Alpha vs key in the edge band (SAD/1000, lower = closer to the key)", "hard", "guided filter", "ViTMatte-S"]]
    for s in ("SHOT-115", "SHOT-116"):
        m = S[s]["mattes"]
        rows.append([s, "%.2f" % m["hard"]["sad_band"], "%.2f" % m["guided"]["sad_band"], "%.2f" % m["vitmatte"]["sad_band"]])
    st.append(Spacer(1, 4))
    st.append(table(rows, [110 * mm, 30 * mm, 30 * mm, 30 * mm]))
    st.append(PageBreak())

    st.append(Paragraph("Despill and edge decontamination", H2))
    st.append(Paragraph("'premultiplied, decontaminated' with spill 'auto' vs plain premultiplied RGB, composited "
                        "over mid grey. Green excess = mean of max(0, G - max(R, B)) in the soft edges.", BODY))
    rows = [["Shot", "green excess in soft edges: plain", "despilled", "mean RGB change in the solid core"]]
    for s in ("SHOT-113", "SHOT-115", "SHOT-116", "SHOT-118"):
        d = S[s]["mattes"].get("despill")
        if d:
            rows.append([s, "%.3f" % d["edge_green_excess_plain"], "%.3f" % d["edge_green_excess_decon_spill"],
                         "%.3f" % d["core_rgb_change_mean"]])
    st.append(table(rows, [30 * mm, 70 * mm, 40 * mm, 70 * mm]))
    st.append(Spacer(1, 6))
    for s in ("SHOT-113", "SHOT-115", "SHOT-118"):
        p = os.path.join(IMG, "%s_despill.jpg" % s)
        if os.path.exists(p):
            st.append(KeepTogether([Paragraph(s + " (crop of a soft edge)", SMALL), img(p, W * 0.48)]))
    st.append(PageBreak())

    st.append(Paragraph("Holdout, ViTMatte fix, speed", H2))
    rows = [["Holdout (the man as holdout)", "frames", "combined = woman x (1 - man): mean abs error",
             "max abs error", "frames where pixels were removed"]]
    for s in ("SHOT-114", "SHOT-117"):
        h = S[s]["mattes"]["holdout"]
        rows.append([s, str(h["frames"]), "%.6f" % h["mean_abs_err"], "%.3f" % h["max_abs_err"],
                     str(h["frames_where_holdout_removed_pixels"])])
    st.append(table(rows, [50 * mm, 18 * mm, 75 * mm, 30 * mm, 55 * mm]))
    st.append(Paragraph("The max error sits on single edge pixels: the combined matte is made at 4K, then reduced, "
                        "while the layers are reduced separately. The holdout removed almost nothing because the tracker "
                        "gives each person only their visible part.", SMALL))
    st.append(Spacer(1, 6))
    st.append(Paragraph(
        "<b>ViTMatte bug found and fixed (DEF-013).</b> On these 4K close-ups ViTMatte failed: it asked the GPU for "
        "10.5 GB. It now runs in overlapping 1024 px tiles (overlap 256). Checked at half resolution, where one pass "
        "still fits: SAD vs key %.1f (one pass) vs %.1f (tiles) on SHOT-115, %.1f vs %.1f on SHOT-116. In Nuke: "
        "26-27 frames in about 2 minutes per shot."
        % (TILE["SHOT-115"]["one_pass"]["sad_vs_key_band"], TILE["SHOT-115"]["tiles_768_ov256"]["sad_vs_key_band"],
           TILE["SHOT-116"]["one_pass"]["sad_vs_key_band"], TILE["SHOT-116"]["tiles_768_ov256"]["sad_vs_key_band"]), BODY))
    st.append(Spacer(1, 4))
    rows = [["Speed (RTX 5060 Laptop, 4K 16-bit plates)", "tiny", "large"]]
    tot = {m: sum(sum(x["seconds"] for x in RES[s]["runs"][m]["steps"] if x["step"].startswith(("track", "retrack")))
                  for s in S) for m in ("tiny", "large")}
    rows.append(["tracking + re-tracking, all 289 frames (s)", "%.0f" % tot["tiny"], "%.0f" % tot["large"]])
    rows.append(["per frame (incl. reading 50 MB frames, reduced render, cut detection)", "%.1f s" % (tot["tiny"] / 289),
                 "%.1f s" % (tot["large"] / 289)])
    rows.append(["guided-filter matte pass at 4K", "-", "about 16 s per frame (DEF-014, slow)"])
    st.append(table(rows, [120 * mm, 40 * mm, 60 * mm]))
    st.append(Spacer(1, 8))
    st.append(Paragraph("Findings", H2))
    for line in [
        "Five of seven real shots track at about 0.99 against the key with either model, with no lost frames.",
        "Large is not better than tiny on six shots. It is clearly better on the wide shot SHOT-118 (0.894 -> 0.949, "
        "worst frame 0.71 -> 0.94), where the subjects are small.",
        "<b>DEF-012 (open):</b> on SHOT-118 tiny lost part of the man and no review flag warned. Use the large model "
        "on wide shots and check the outlines.",
        "Roto shapes have no holes: green enclosed by arms (SHOT-113) is filled. The status line says so; an artist "
        "adds a cut-out shape.",
        "Despill removed the green spill from soft edges on all four shots, with a small colour change in the solid "
        "core (0.001-0.014).",
        "<b>DEF-013 (fixed):</b> ViTMatte out of memory on 4K close-ups, now tiled. <b>DEF-014 (open):</b> "
        "guided-filter mattes take about 16 s per frame at 4K.",
        "No false scene cuts on any of the 14 runs."]:
        st.append(Paragraph("&bull; " + line, BODY))
    st.append(Spacer(1, 6))
    st.append(Paragraph("Limits", H2))
    for line in [
        "The reference is a green-screen key, not a hand-made matte. It is reliable for body outlines on clean "
        "green, but not for hair, motion blur or spill edges (those are excluded from core IoU). In SHOT-118 it also "
        "contains floor shadow.",
        "The colour space of the footage is unknown; it was treated as sRGB / Rec.709.",
        "Prompts were placed by eye; another box or click can change the result, especially on SHOT-118.",
        "Nuke Non-commercial gave the AI 1920-wide frames; commercial Nuke would give it full 4K (not tested).",
        "7 short shots, one machine, one session. No artist has judged the shapes or mattes for delivery yet."]:
        st.append(Paragraph("&bull; " + line, BODY))

    def footer(c, d):
        c.saveState()
        c.setFont("Helvetica", 7)
        c.setFillColor(colors.grey)
        c.drawString(15 * mm, 6 * mm, "ST-ROTO green-screen test - tiny vs large - contains the owner's footage: "
                                      "not for publication")
        c.drawRightString(PAGE[0] - 15 * mm, 6 * mm, "page %d" % d.page)
        c.restoreState()
    doc.build(st, onFirstPage=footer, onLaterPages=footer)


if __name__ == "__main__":
    build()
    print("wrote", OUT)
