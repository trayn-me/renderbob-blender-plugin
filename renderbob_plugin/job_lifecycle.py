"""Parse job API payloads for UI state (payment, status, terminals)."""
from __future__ import annotations

from typing import Any, Dict, Optional


def job_status_name(job: Optional[Dict[str, Any]]) -> str:
    if not job:
        return ""
    return _status_name(job)


def _status_name(job: Dict[str, Any]) -> str:
    raw = job.get("status")
    if isinstance(raw, dict):
        return str(raw.get("name") or raw.get("id") or "").strip().lower()
    if raw is not None:
        return str(raw).strip().lower()
    return ""


def payment_status_from_job(job: Dict[str, Any]) -> str:
    return str(
        job.get("payment_status") or job.get("paymentStatus") or ""
    ).strip().lower()


def normalize_job_dict(response_data: Dict[str, Any]) -> Dict[str, Any]:
    """Unwrap { data: job } or return job dict."""
    if not isinstance(response_data, dict):
        return {}
    inner = response_data.get("data")
    if isinstance(inner, dict):
        return inner
    return response_data


def is_payment_paid(job: Dict[str, Any]) -> bool:
    return payment_status_from_job(job) == "paid"


def is_terminal_status(status_name: str) -> bool:
    s = (status_name or "").lower()
    if not s:
        return False
    if s in ("failed", "terminated", "cancelled", "canceled"):
        return True
    if "completed" in s:
        return True
    return False


def is_success_terminal(status_name: str) -> bool:
    s = (status_name or "").lower()
    return "completed" in s


def compute_render_panel_phase(
    job: Optional[Dict[str, Any]],
    public_id: str,
) -> str:
    """
    idle — no linked job id on the scene.
    syncing — linked id but no snapshot yet (poll will fill).
    draft — unpaid draft; estimate + start render.
    pending — queued after pay; upload/start render locked.
    active — rendering (progress + terminate).
    failed — terminal failure / cancelled / terminated.
    completed — successful terminal.
    """
    pid = (public_id or "").strip()
    if not pid:
        return "idle"
    if not job:
        return "syncing"
    st = job_status_name(job)
    if is_success_terminal(st):
        return "completed"
    if is_terminal_status(st):
        return "failed"
    if st in ("active", "rendering", "processing", "paused"):
        return "active"
    if st in ("pending", "analyzed"):
        return "pending"
    if st == "draft":
        return "pending" if is_payment_paid(job) else "draft"
    return "syncing"


def render_panel_phase_from_context(context: Any) -> str:
    """Resolve phase for the current .blend using scene job id + last polled snapshot."""
    from .state import STATE

    scene = getattr(context, "scene", None)
    if scene is None or not hasattr(scene, "renderbob"):
        return "idle"
    public_id = (scene.renderbob.draft_public_id or "").strip()
    job = STATE.job_snapshot.get("job")
    job = job if isinstance(job, dict) else None
    return compute_render_panel_phase(job, public_id)


def should_allow_upload_and_estimate(context: Any) -> bool:
    """Upload / re-estimate allowed for new work or draft retry; blocked while queued or rendering."""
    phase = render_panel_phase_from_context(context)
    return phase in ("idle", "draft", "failed")


def should_show_start_render_operator(context: Any) -> bool:
    """Start render (pay + launch) only in draft phase when idle and a quote exists."""
    from .state import STATE

    if STATE.upload_estimate_stage != "idle":
        return False
    if render_panel_phase_from_context(context) != "draft":
        return False
    scene = getattr(context, "scene", None)
    if scene is None or not hasattr(scene, "renderbob"):
        return False
    props = scene.renderbob
    if STATE.awaiting_stripe_checkout:
        return False
    if not (props.quote_id or "").strip():
        return False
    job = STATE.job_snapshot.get("job")
    if isinstance(job, dict) and is_payment_paid(job):
        return False
    return True


def should_allow_terminate_job(context: Any) -> bool:
    return render_panel_phase_from_context(context) == "active"
