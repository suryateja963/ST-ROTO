"""ST-ROTO core: Nuke-independent, AI-independent rotoscoping engine (pre-alpha).

Layering (ARCHITECTURE.md, D-026): this package must never import nuke, Qt or onnxruntime, so that
traditional roto works with every AI feature disabled (master prompt section 3) and the core is
unit-testable outside Nuke. Code must remain Python 3.7 compatible (Nuke 13, D-017).
"""
__version__ = "0.0.1.dev0"
