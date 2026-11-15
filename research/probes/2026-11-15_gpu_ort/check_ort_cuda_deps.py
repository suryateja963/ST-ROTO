"""Report which CUDA/cuDNN DLL names an onnxruntime_providers_cuda.dll imports.
Usage: python check_ort_cuda_deps.py <dir containing onnxruntime package> [...]"""
import re, sys, os
for root in sys.argv[1:]:
    p = os.path.join(root, "onnxruntime", "capi", "onnxruntime_providers_cuda.dll")
    if not os.path.exists(p):
        print(root, "NO CUDA PROVIDER DLL"); continue
    data = open(p, "rb").read()
    names = sorted(set(m.decode() for m in re.findall(rb"(?:cu[a-zA-Z_]+|nvrtc|nvJitLink)[a-zA-Z0-9_]*64_[0-9]+(?:_0)?\.dll", data)))
    print(os.path.basename(root), names)
