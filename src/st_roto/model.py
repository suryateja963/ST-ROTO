"""Domain vocabulary shared by the store, commands and exporters (ADR-0004).

Canonical coordinate space for all geometry stored by ST-ROTO
-------------------------------------------------------------
Source-image pixel space at full resolution: x to the right, y DOWN, origin at the top-left corner of the
top-left pixel (so the centre of pixel (col,row) is (col+0.5, row+0.5)). Exporters convert to host
conventions (e.g. Nuke: y up, tangent = 2 x handle offset; see st_roto_nuke when it exists).

Shape keys store, per control point, six floats: x, y, h_in_x, h_in_y, h_out_x, h_out_y, where the
handles are ABSOLUTE positions of the cubic Bezier control points (h_in belongs to the segment arriving
at the point, h_out to the segment leaving it).

Frames are arbitrary integers (negative, gaps and non-contiguous ranges allowed: master prompt section 11).
"""
from __future__ import annotations

import math
import uuid

# --- provenance -------------------------------------------------------------------------------
AI_GENERATED = "ai_generated"
IMPORTED_NATIVE = "imported_native"
ARTIST_CREATED = "artist_created"
ARTIST_MODIFIED_AI = "artist_modified_ai"
ORIGINS = (AI_GENERATED, IMPORTED_NATIVE, ARTIST_CREATED, ARTIST_MODIFIED_AI)
# "locked" (the fifth class in master prompt section 6) is a separate flag, because any origin can be locked.

# Who performs an operation. AI may only touch AI-generated, unlocked content (REQ-042).
ACTOR_ARTIST = "artist"
ACTOR_AI = "ai"
ACTOR_IMPORT = "import"
ACTORS = (ACTOR_ARTIST, ACTOR_AI, ACTOR_IMPORT)

FLOATS_PER_POINT = 6


def new_id() -> str:
    return uuid.uuid4().hex


def origin_for_write(actor: str, previous_origin: str | None) -> str:
    """Origin recorded when `actor` writes over content whose previous origin is `previous_origin`."""
    if actor == ACTOR_AI:
        return AI_GENERATED
    if actor == ACTOR_IMPORT:
        return IMPORTED_NATIVE
    if previous_origin in (AI_GENERATED, ARTIST_MODIFIED_AI):
        return ARTIST_MODIFIED_AI
    return ARTIST_CREATED


def validate_points(points, point_count: int) -> list:
    """Return points as a list of `point_count` lists of 6 finite floats, or raise ValueError."""
    if len(points) != point_count:
        raise ValueError("expected %d points, got %d" % (point_count, len(points)))
    out = []
    for i, p in enumerate(points):
        if len(p) != FLOATS_PER_POINT:
            raise ValueError("point %d: expected %d floats, got %d" % (i, FLOATS_PER_POINT, len(p)))
        q = [float(v) for v in p]
        if not all(math.isfinite(v) for v in q):
            raise ValueError("point %d contains a non-finite value" % i)
        out.append(q)
    return out
