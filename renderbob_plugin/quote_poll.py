"""
Non-blocking poll for latest-quote after estimate returns resampling.
Blocking time.sleep in the main thread freezes Blender; this uses bpy.app.timers.
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional

import bpy

from .logging_utils import log_error, log_info
from .state import STATE
from .submit_utils import apply_quote_block_to_props, tag_renderbob_sidebar_redraw
from .workflows import latest_quote

_DIAG_KEY = "renderbob_quote_poll"
_POLL_INTERVAL = 2.0
# Sampling + quote generation can exceed 3 minutes on busy farms
_DEFAULT_TIMEOUT_SEC = 900.0


def _clear_poll_state() -> None:
    STATE.diagnostics.pop(_DIAG_KEY, None)


def stop_quote_poll_timer() -> None:
    try:
        bpy.app.timers.unregister(renderbob_quote_poll_tick)
    except Exception:
        pass
    _clear_poll_state()


def start_quote_poll_timer(public_id: str, timeout_sec: float = _DEFAULT_TIMEOUT_SEC) -> None:
    """Begin background latest-quote polling; keeps upload_estimate_stage at 'estimating'."""
    stop_quote_poll_timer()
    STATE.diagnostics[_DIAG_KEY] = {
        "public_id": public_id,
        "deadline": time.time() + timeout_sec,
    }
    bpy.app.timers.register(
        renderbob_quote_poll_tick,
        first_interval=_POLL_INTERVAL,
        persistent=True,
    )
    log_info(f"quote poll timer started for job={public_id} timeout={timeout_sec}s")


def renderbob_quote_poll_tick() -> Optional[float]:
    """Return next interval or None to stop."""
    try:
        ctx = bpy.context
        scene = getattr(ctx, "scene", None)
        if scene is None or not hasattr(scene, "renderbob"):
            stop_quote_poll_timer()
            STATE.upload_estimate_stage = "idle"
            tag_renderbob_sidebar_redraw()
            return None

        info = STATE.diagnostics.get(_DIAG_KEY)
        if not isinstance(info, dict):
            return None

        public_id = str(info.get("public_id") or "").strip()
        deadline = float(info.get("deadline") or 0)
        if not public_id:
            stop_quote_poll_timer()
            STATE.upload_estimate_stage = "idle"
            tag_renderbob_sidebar_redraw()
            return None

        token = (scene.renderbob.api_token or "").strip()
        if not token:
            stop_quote_poll_timer()
            STATE.upload_estimate_stage = "idle"
            STATE.status_message = "API token missing — quote poll stopped"
            tag_renderbob_sidebar_redraw()
            return None

        if time.time() > deadline:
            stop_quote_poll_timer()
            STATE.upload_estimate_stage = "idle"
            msg = "Timed out waiting for sampling / quote (try again or check the job in RenderBob web)"
            STATE.status_message = msg
            STATE.last_error = msg
            log_error(msg)
            tag_renderbob_sidebar_redraw()
            return None

        response = latest_quote(ctx, token, public_id)
        if not response.ok:
            return _POLL_INTERVAL

        data = response.data.get("data", response.data)
        if not isinstance(data, dict):
            return _POLL_INTERVAL

        st = data.get("samplingStatus")
        if st == "done":
            quote = data.get("quote")
            if not isinstance(quote, dict):
                stop_quote_poll_timer()
                STATE.upload_estimate_stage = "idle"
                STATE.status_message = "Quote poll finished but no quote payload"
                tag_renderbob_sidebar_redraw()
                return None
            apply_quote_block_to_props(scene.renderbob, quote)
            stop_quote_poll_timer()
            STATE.upload_estimate_stage = "idle"
            STATE.status_message = "Estimate ready — review cost, then Start render"
            STATE.last_error = None
            log_info(f"quote ready after resampling job={public_id}")
            tag_renderbob_sidebar_redraw()
            return None

        if st == "failed":
            stop_quote_poll_timer()
            STATE.upload_estimate_stage = "idle"
            err = str(data.get("samplingError") or "Sampling failed")
            STATE.status_message = err
            STATE.last_error = err
            log_error(err)
            tag_renderbob_sidebar_redraw()
            return None

        tag_renderbob_sidebar_redraw()
        return _POLL_INTERVAL
    except Exception as ex:
        log_error(f"quote poll tick: {ex}")
        stop_quote_poll_timer()
        STATE.upload_estimate_stage = "idle"
        tag_renderbob_sidebar_redraw()
        return None
