"""Developer helper: replace whole top-level functions/classes in a Python file by name, keeping the file's line
endings. Usage: python tools/dev/replace_functions.py TARGET.py NEW_DEFS.py
NEW_DEFS.py holds complete top-level definitions; each replaces the same-named one in TARGET (or is appended if
absent). Used because exact-substring edits break on CRLF files (CLAUDE.md pitfalls)."""
import ast
import sys


def blocks(src):
    tree = ast.parse(src)
    lines = src.split("\n")
    out = {}
    nodes = [n for n in tree.body]
    for i, n in enumerate(nodes):
        if not isinstance(n, (ast.FunctionDef, ast.ClassDef)):
            continue
        start = n.lineno - 1 - len(getattr(n, "decorator_list", []))
        end = (nodes[i + 1].lineno - 1) if i + 1 < len(nodes) else len(lines)
        while end > start and lines[end - 1].strip() == "":
            end -= 1
        out[n.name] = (start, end)
    return out


def main(target, new):
    raw = open(target, "rb").read().decode("utf-8")
    crlf = "\r\n" in raw
    src = raw.replace("\r\n", "\n")
    new_src = open(new, encoding="utf-8").read().replace("\r\n", "\n")
    new_blocks = blocks(new_src)
    new_lines = new_src.split("\n")
    lines = src.split("\n")
    for name, (s, e) in sorted(new_blocks.items(), key=lambda kv: kv[1][0]):
        text = new_lines[s:e]
        cur = blocks("\n".join(lines))
        if name in cur:
            cs, ce = cur[name]
            lines[cs:ce] = text
            print("replaced", name)
        else:
            lines += ["", ""] + text
            print("appended", name)
    out = "\n".join(lines)
    ast.parse(out)
    if crlf:
        out = out.replace("\n", "\r\n")
    open(target, "wb").write(out.encode("utf-8"))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
