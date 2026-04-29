"""Shared helpers for upload / estimate flow (avoids circular imports)."""
from __future__ import annotations

from typing import Any, Dict

import bpy

from .state import STATE


def tag_renderbob_sidebar_redraw() -> None:
    try:
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == "VIEW_3D":
                    area.tag_redraw()
    except Exception:
        pass


def safe_progress_end(wm: bpy.types.WindowManager) -> None:
    try:
        wm.progress_end()
    except Exception:
        pass


def apply_quote_block_to_props(
    props: Any,
    quote_block: Dict[str, Any],
) -> None:
    """Apply estimate / latest-quote payload to scene props and STATE labels."""
    qid = quote_block.get("quoteId") or quote_block.get("id")
    props.quote_id = str(qid or "")
    p50 = quote_block.get("predictedRuntimeMinutesP50")
    p90 = quote_block.get("predictedRuntimeMinutesP90")
    cents = quote_block.get("predictedCostCents")
    if p50 is not None and p90 is not None:
        STATE.estimate_line1 = f"~{p50:.0f}–{p90:.0f} min (p50 / p90)"
    elif p50 is not None:
        STATE.estimate_line1 = f"~{p50:.0f} min (p50)"
    else:
        STATE.estimate_line1 = ""
    if cents is not None:
        STATE.estimate_line2 = f"~EUR {float(cents) / 100.0:.2f}"
    else:
        STATE.estimate_line2 = ""
