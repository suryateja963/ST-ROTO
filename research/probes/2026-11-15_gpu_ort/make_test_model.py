"""Build a synthetic ONNX conv network for runtime tests (no downloaded weights).

8 x (3x3 conv, 64 ch) + ReLU on 1x3xHxW float32, then 1x1 conv to 1 channel + sigmoid.
Weights are random (fixed seed). Output has no meaning; it only exercises the runtime.
Run with the project venv:  .venv\\Scripts\\python.exe make_test_model.py
"""
import os
import numpy as np
import onnx
from onnx import helper, TensorProto, numpy_helper

HERE = os.path.dirname(os.path.abspath(__file__))
rng = np.random.default_rng(0)
nodes, inits = [], []
prev, cin = "input", 3
for i in range(8):
    w = (rng.standard_normal((64, cin, 3, 3)) * (1.0 / np.sqrt(cin * 9))).astype(np.float32)
    b = np.zeros(64, np.float32)
    inits += [numpy_helper.from_array(w, f"w{i}"), numpy_helper.from_array(b, f"b{i}")]
    nodes.append(helper.make_node("Conv", [prev, f"w{i}", f"b{i}"], [f"c{i}"], pads=[1, 1, 1, 1]))
    nodes.append(helper.make_node("Relu", [f"c{i}"], [f"r{i}"]))
    prev, cin = f"r{i}", 64
wo = (rng.standard_normal((1, 64, 1, 1)) * 0.1).astype(np.float32)
inits.append(numpy_helper.from_array(wo, "wo"))
nodes.append(helper.make_node("Conv", [prev, "wo"], ["co"]))
nodes.append(helper.make_node("Sigmoid", ["co"], ["output"]))
g = helper.make_graph(
    nodes, "stroto_runtime_probe",
    [helper.make_tensor_value_info("input", TensorProto.FLOAT, [1, 3, "H", "W"])],
    [helper.make_tensor_value_info("output", TensorProto.FLOAT, [1, 1, "H", "W"])],
    inits,
)
m = helper.make_model(g, opset_imports=[helper.make_opsetid("", 17)])
m.ir_version = 9
onnx.checker.check_model(m)
out = os.path.join(HERE, "test_conv.onnx")
onnx.save(m, out)
print("saved", out, os.path.getsize(out), "bytes")
