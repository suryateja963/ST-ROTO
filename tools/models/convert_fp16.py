"""Make fp16 variants of an exported ONNX graph (inputs/outputs stay fp32). Experimental (T-062).

Usage: .venv\\Scripts\\python.exe tools/models/convert_fp16.py models/onnx/sam2.1-hiera-tiny/video/memattn.onnx
Writes <name>_fp16.onnx (everything fp16 except the converter's default block list) and
<name>_fp16keep.onnx (additionally keeps Softmax / LayerNormalization / ReduceMean / Pow / Sqrt in fp32).
Accuracy must be validated against the fp32 graph and the PyTorch reference before any use.
"""
import os, sys
import onnx
from onnxconverter_common import float16

KEEP = ["Softmax", "LayerNormalization", "ReduceMean", "Pow", "Sqrt", "Div", "Erf"]


def _fix_internal_casts(m):
    """The model's own explicit Cast-to-float32 nodes (e.g. RoPE `q.float()`) survive conversion and clash with the
    fp16 graph around them. Retarget them to fp16, except the converter's graph-boundary casts (keep_io_types) and
    casts that feed nodes kept in fp32 by the block list (detected via consumers' op types)."""
    from onnx import TensorProto, helper
    consumers = {}
    for n in m.graph.node:
        for i in n.input:
            consumers.setdefault(i, []).append(n)
    outputs = {o.name for o in m.graph.output}
    changed = 0
    for n in m.graph.node:
        if n.op_type != "Cast" or "graph_input_cast" in n.name or "graph_output_cast" in n.name:
            continue
        to = next(a for a in n.attribute if a.name == "to")
        if to.i != TensorProto.FLOAT or n.output[0] in outputs:
            continue
        if any(c.op_type in KEEP or c.op_type in float16.DEFAULT_OP_BLOCK_LIST for c in consumers.get(n.output[0], [])):
            continue
        to.i = TensorProto.FLOAT16
        changed += 1
    print("retargeted internal fp32 casts:", changed)
    return m


def main(path):
    m = onnx.load(path)
    # Stale value_info (fp32 shape/type annotations from export) conflicts with converted Cast nodes
    # ("Type (tensor(float16)) of output arg ... does not match expected type (tensor(float))"): drop it.
    del m.graph.value_info[:]
    base = os.path.splitext(path)[0]
    a = float16.convert_float_to_float16(m, keep_io_types=True)
    onnx.save(_fix_internal_casts(a), base + "_fp16.onnx")
    b = float16.convert_float_to_float16(m, keep_io_types=True, op_block_list=list(float16.DEFAULT_OP_BLOCK_LIST) + KEEP)
    onnx.save(_fix_internal_casts(b), base + "_fp16keep.onnx")
    for p in (path, base + "_fp16.onnx", base + "_fp16keep.onnx"):
        print(os.path.basename(p), round(os.path.getsize(p) / 1e6, 1), "MB")


if __name__ == "__main__":
    main(sys.argv[1])
