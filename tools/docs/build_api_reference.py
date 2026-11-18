"""Generate docs/API_REFERENCE.md from the source (T-125): every module of st_roto, st_roto_ai and st_roto_nuke with
its docstring and every public class / function with its signature and docstring. Reads the files with `ast` (nothing
is imported, so it runs without Nuke or ONNX Runtime). Re-run after code changes:
  .venv\\Scripts\\python.exe -I tools/docs/build_api_reference.py [--check]
--check exits 1 if docs/API_REFERENCE.md is out of date (used by the unit tests)."""
import ast
import glob
import io
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(ROOT, "docs", "API_REFERENCE.md")
PACKAGES = (("st_roto", "Core: pure Python 3.7+ and numpy; no Nuke, Qt or ONNX Runtime"),
            ("st_roto_ai", "AI layer: ONNX Runtime + numpy; no Nuke or Qt"),
            ("st_roto_nuke", "Nuke adapter"))


def _sig(fn):
    a = fn.args
    parts = []
    pos = a.posonlyargs + a.args
    defaults = [None] * (len(pos) - len(a.defaults)) + list(a.defaults)
    for arg, d in zip(pos, defaults):
        parts.append(arg.arg + ("=" + ast.unparse(d) if d is not None else ""))
    if a.vararg:
        parts.append("*" + a.vararg.arg)
    elif a.kwonlyargs:
        parts.append("*")
    for arg, d in zip(a.kwonlyargs, a.kw_defaults):
        parts.append(arg.arg + ("=" + ast.unparse(d) if d is not None else ""))
    if a.kwarg:
        parts.append("**" + a.kwarg.arg)
    return "(%s)" % ", ".join(p for p in parts if p not in ("self", "cls"))


def _doc(node):
    d = ast.get_docstring(node) or ""
    return d.strip()


def _quote(text, indent=""):
    return "\n".join((indent + "> " + line).rstrip() for line in text.splitlines()) if text else ""


def build():
    out = ["# ST-ROTO API reference", "",
           "Generated from the source by `tools/docs/build_api_reference.py` - do not edit by hand. Public names only "
           "(no leading underscore). Architecture, data model and conventions: `docs/DEVELOPER_GUIDE.md`.", ""]
    toc = []
    body = []
    for pkg, what in PACKAGES:
        files = sorted(glob.glob(os.path.join(ROOT, "src", pkg, "*.py")))
        body += ["## `%s` - %s" % (pkg, what), ""]
        toc.append("* `%s`: %s" % (pkg, ", ".join(
            "[%s](#%s%s)" % (os.path.basename(f)[:-3], pkg, os.path.basename(f)[:-3])   # GitHub slug: dot removed
            for f in files if not f.endswith("__init__.py"))))
        for f in files:
            name = os.path.basename(f)[:-3]
            if name == "__init__":
                continue
            tree = ast.parse(io.open(f, encoding="utf-8").read())
            body += ["### %s.%s" % (pkg, name), ""]
            md = _doc(tree)
            if md:
                body += [md, ""]
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
                    body += ["* **`%s%s`**" % (node.name, _sig(node))]
                    if _doc(node):
                        body += ["", _quote(_doc(node), "  "), ""]
                elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
                    bases = ", ".join(ast.unparse(b) for b in node.bases)
                    body += ["* **class `%s`**%s" % (node.name, (" (%s)" % bases) if bases else "")]
                    if _doc(node):
                        body += ["", _quote(_doc(node), "  "), ""]
                    for m in node.body:
                        if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)) and (
                                not m.name.startswith("_") or m.name == "__init__"):
                            body += ["  * `%s%s`%s" % (m.name, _sig(m), (" - " + _doc(m).split("\n")[0]) if _doc(m)
                                                       else "")]
            body.append("")
    return "\n".join(out + ["## Contents", ""] + toc + [""] + body).rstrip() + "\n"


def main():
    text = build()
    if "--check" in sys.argv:
        cur = io.open(OUT, encoding="utf-8").read() if os.path.exists(OUT) else ""
        if cur.replace("\r\n", "\n") != text:
            print("docs/API_REFERENCE.md is out of date: run tools/docs/build_api_reference.py")
            return 1
        print("up to date")
        return 0
    with io.open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    print("wrote", OUT, len(text.splitlines()), "lines")
    return 0


if __name__ == "__main__":
    sys.exit(main())
