"""Background job / progress / logs polling (no UI buttons)."""
from __future__ import annotations

import bpy

from .job_lifecycle import is_payment_paid, normalize_job_dict
from .logging_utils import log_error
from .state import STATE
from .storage import load_settings
from .workflows import (
    get_job,
    get_job_logs_status,
    get_job_progress,
)


def sync_job_snapshot_once(context, token: str, public_id: str) -> None:
    """Populate STATE.job_snapshot immediately (e.g. after publish/pay)."""
    if not public_id or not token:
        return
    job_r = get_job(context, token, public_id)
    if job_r.ok:
        job = normalize_job_dict(job_r.data)
        STATE.job_snapshot = {"job": job}
        if is_payment_paid(job):
            STATE.awaiting_stripe_checkout = False
        st_raw = job.get("status")
        if isinstance(st_raw, dict):
            sn = str(st_raw.get("name") or "")
        else:
            sn = str(st_raw or "")
        STATE.active_job_public_id = public_id
        STATE.active_job_status = sn


def _token_from_scene(scene) -> str:
    if not scene or not hasattr(scene, "renderbob"):
        return ""
    return (scene.renderbob.api_token or "").strip()


def needs_onboarding() -> bool:
    """First run: no saved token and user has not opened the setup link yet."""
    if (load_settings().get("api_token") or "").strip():
        return False
    if STATE.setup_launched:
        return False
    return True


def renderbob_background_poll() -> float:
    """Return next interval seconds, or None to stop."""
    try:
        if needs_onboarding() or not STATE.auth_ok:
            return 5.0
        context = bpy.context
        scene = getattr(context, "scene", None)
        if scene is None or not hasattr(scene, "renderbob"):
            return 5.0
        token = _token_from_scene(scene)
        if not token:
            return 5.0
        props = scene.renderbob
        public_id = (props.draft_public_id or STATE.active_job_public_id or "").strip()
        if not public_id:
            return 5.0

        job_r = get_job(context, token, public_id)
        if job_r.ok:
            job = normalize_job_dict(job_r.data)
            STATE.job_snapshot = {"job": job}
            if is_payment_paid(job):
                STATE.awaiting_stripe_checkout = False
            st_raw = job.get("status")
            if isinstance(st_raw, dict):
                sn = str(st_raw.get("name") or "")
            else:
                sn = str(st_raw or "")
            STATE.active_job_public_id = public_id
            STATE.active_job_status = sn

        pr = get_job_progress(context, token, public_id)
        if pr.ok:
            pdata = pr.data.get("data", pr.data)
            completion = (
                pdata.get("progress")
                or pdata.get("completion")
                or pdata.get("percentage")
            )
            try:
                factor = (
                    float(completion) / 100.0
                    if float(completion) > 1
                    else float(completion)
                )
                props.progress = max(0.0, min(1.0, factor))
            except Exception:
                pass

        lr = get_job_logs_status(context, token, public_id)
        if lr.ok:
            ldata = lr.data.get("data", lr.data)
            phase = ldata.get("phase") if isinstance(ldata, dict) else None
            cw = (ldata or {}).get("cloudWatch") if isinstance(ldata, dict) else {}
            if isinstance(cw, dict) and cw.get("hasEvents"):
                STATE.log_status_line = f"Logs: phase={phase or '?'}"
            elif phase:
                STATE.log_status_line = f"Logs: phase={phase}"
            else:
                STATE.log_status_line = "Logs: waiting…"
        else:
            STATE.log_status_line = ""

        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == "VIEW_3D":
                    area.tag_redraw()
    except Exception as err:
        log_error(f"background poll: {err}")
    return 5.0
