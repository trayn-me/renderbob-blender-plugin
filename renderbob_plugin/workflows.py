import json
import mimetypes
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.request import Request, urlopen

import bpy

from .client import ApiResponse
from .context import make_client
from .logging_utils import log_error, log_info

# Same defaults as render-manager/src/components/JobSetupCard.tsx
TIER_INSTANCE_MAP = {
    "s": "g6e.xlarge",
    "m": "g6.12xlarge",
    "l": "g6e.12xlarge",
}
DEFAULT_MEMORY_TIER = "m"
# Addon always uses middle tier (product requirement).
ADDON_INSTANCE_MEMORY_TIER = "m"


def scene_file_path() -> Optional[Path]:
    current = bpy.data.filepath
    if not current:
        return None
    return Path(current)


def preflight_validate(context: bpy.types.Context) -> Tuple[bool, str]:
    scene = context.scene
    props = scene.renderbob
    blend_path = scene_file_path()
    if not blend_path:
        return False, "Save the .blend file before uploading"
    if props.frame_start > props.frame_end:
        return False, "Frame start must be <= frame end"
    if scene.render.engine.lower() not in {"cycles", "blender_eevee", "blender_eevee_next"}:
        return False, "Only Cycles and Eevee are currently supported"
    return True, "Preflight checks passed"


def fetch_credits(context: bpy.types.Context, token: str) -> ApiResponse:
    client = make_client(context, token)
    return client.get("/billing/credits")


def fetch_servers(context: bpy.types.Context, token: str) -> ApiResponse:
    client = make_client(context, token)
    # Web UI passes ?isActive=true; backend may ignore query, we also filter client-side.
    return client.get("/renders/servers", {"isActive": "true"})


def parse_servers_list(response: ApiResponse) -> List[Dict[str, Any]]:
    if not response.ok:
        return []
    data = response.data
    if isinstance(data, list):
        return [s for s in data if isinstance(s, dict)]
    if isinstance(data, dict):
        inner = data.get("data")
        if isinstance(inner, list):
            return [s for s in inner if isinstance(s, dict)]
    return []


def _server_instance_type(server: Dict[str, Any]) -> str:
    direct = server.get("instance_type") or server.get("instanceType")
    if direct:
        return str(direct).strip().lower()
    cfg = server.get("configuration_json") or {}
    if isinstance(cfg, dict):
        inst = (
            cfg.get("instanceType")
            or cfg.get("instance_type")
            or cfg.get("defaultInstanceType")
            or cfg.get("ec2InstanceType")
        )
        if inst:
            return str(inst).strip().lower()
    return ""


def _is_server_active(server: Dict[str, Any]) -> bool:
    status = server.get("status")
    if not isinstance(status, dict):
        return True
    name = str(status.get("name") or "").strip().lower()
    if not name:
        return True
    return name == "active"


def _sort_servers_prefer_aws(servers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    def sort_key(s: Dict[str, Any]) -> int:
        sp = s.get("server_provider") if isinstance(s.get("server_provider"), dict) else {}
        t = str((sp or {}).get("type") or (sp or {}).get("name") or "").lower()
        return 0 if "aws" in t else 1

    return sorted(servers, key=sort_key)


def render_engine_billing_keyword(scene: bpy.types.Scene) -> str:
    eng = scene.render.engine.lower()
    if "eevee" in eng:
        return "eevee"
    return "cycles"


def _pick_server_meta(
    server: Dict[str, Any],
    engine_keyword: str,
) -> Optional[Dict[str, Any]]:
    metas = server.get("server_meta") or server.get("serverMeta") or []
    if not isinstance(metas, list):
        return None
    for meta in metas:
        if not isinstance(meta, dict):
            continue
        hay = f"{meta.get('render_engine', '')} {meta.get('render_software', '')}".lower()
        if engine_keyword in hay:
            return meta
    for meta in metas:
        if not isinstance(meta, dict):
            continue
        hay = f"{meta.get('render_engine', '')} {meta.get('render_software', '')}".lower()
        if "blender" in hay:
            return meta
    return None


def resolve_default_blender_server(
    servers: List[Dict[str, Any]],
    memory_tier: str,
    engine_keyword: str,
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Match render-manager JobSetupCard: pick server by instance type tier, then meta by engine.
    Returns (server_uuid, server_meta_uuid, human_name) or (None, None, error).
    """
    target = TIER_INSTANCE_MAP.get(memory_tier, TIER_INSTANCE_MAP[DEFAULT_MEMORY_TIER]).lower()
    candidates = _sort_servers_prefer_aws(
        [s for s in servers if isinstance(s, dict) and _is_server_active(s)]
    )
    if not candidates:
        candidates = _sort_servers_prefer_aws([s for s in servers if isinstance(s, dict)])

    for server in candidates:
        if _server_instance_type(server) != target:
            continue
        meta = _pick_server_meta(server, engine_keyword)
        mu = str((meta or {}).get("uuid") or "")
        if meta and server.get("uuid") and mu:
            name = str(server.get("name") or server.get("uuid") or "server")
            return str(server["uuid"]), mu, name

    for server in candidates:
        meta = _pick_server_meta(server, engine_keyword)
        mu = str((meta or {}).get("uuid") or "")
        if meta and server.get("uuid") and mu:
            name = str(server.get("name") or server.get("uuid") or "server")
            return str(server["uuid"]), mu, name

    return None, None, (
        f"No render server found for instance {target} and engine '{engine_keyword}'. "
        "Check active GPU servers in RenderBob."
    )


def refresh_render_server_selection(
    context: bpy.types.Context,
    token: str,
    memory_tier: str = ADDON_INSTANCE_MEMORY_TIER,
) -> Tuple[bool, str]:
    """Fetch /renders/servers and set scene.renderbob server UUIDs like the web UI."""
    props = context.scene.renderbob
    response = fetch_servers(context, token)
    servers = parse_servers_list(response)
    if not servers and response.ok:
        return False, "No render servers returned from API"
    if not response.ok:
        return False, response.error or "Failed to list render servers"

    engine_kw = render_engine_billing_keyword(context.scene)
    su, mu, name_or_err = resolve_default_blender_server(servers, memory_tier, engine_kw)
    if not su or not mu:
        return False, name_or_err or "Could not resolve render server"

    props.server_public_id = su
    props.server_meta_public_id = mu
    log_info(
        f"Resolved render server: name={name_or_err}, server={su}, meta={mu}, tier={memory_tier}"
    )
    return True, f"Using render server: {name_or_err}"


def build_publish_draft_payload(
    context: bpy.types.Context,
    props: bpy.types.PropertyGroup,
    memory_tier: str = ADDON_INSTANCE_MEMORY_TIER,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Build body for POST /jobs/publish (PublishDraftJobDto / CreateJobDto)."""
    scene = context.scene
    if not props.draft_public_id:
        return None, "No draft job"
    if not props.server_public_id or not props.server_meta_public_id:
        return None, "Render server not resolved; use Refresh Account"

    job_name = (props.job_name or "").strip() or Path(bpy.data.filepath).stem
    pct = max(1, min(100, int(scene.render.resolution_percentage))) / 100.0
    w = max(1, int(scene.render.resolution_x * pct))
    h = max(1, int(scene.render.resolution_y * pct))
    resolution = f"{w}x{h}"

    samples = 128
    if scene.render.engine == "CYCLES":
        samples = max(1, int(scene.cycles.samples))

    denoising = None
    if scene.render.engine == "CYCLES":
        denoising = {"enabled": bool(getattr(scene.cycles, "use_denoising", False))}

    instance_type = TIER_INSTANCE_MAP.get(memory_tier, TIER_INSTANCE_MAP[DEFAULT_MEMORY_TIER])

    payload: Dict[str, Any] = {
        "publicId": props.draft_public_id,
        "name": job_name,
        "serverPublicId": props.server_public_id,
        "serverMetaPublicId": props.server_meta_public_id,
        "priority": 50,
        "frames": {"start": int(props.frame_start), "end": int(props.frame_end)},
        "outputFormat": props.output_format,
        "resolution": resolution,
        "samples": samples,
        "instanceType": instance_type,
    }
    if denoising is not None:
        payload["denoising"] = denoising
    return payload, None


def samples_for_scene(scene: bpy.types.Scene) -> int:
    eng = scene.render.engine
    if eng == "CYCLES":
        return max(1, int(scene.cycles.samples))
    if hasattr(scene, "eevee"):
        return max(
            1,
            int(getattr(scene.eevee, "taa_render_samples", 64) or 64),
        )
    return 64


def build_estimate_payload(
    context: bpy.types.Context,
    props: bpy.types.PropertyGroup,
    memory_tier: str = ADDON_INSTANCE_MEMORY_TIER,
) -> Dict[str, Any]:
    """Body for POST /jobs/:publicId/estimate (camelCase, matches web EstimateRequest)."""
    scene = context.scene
    pct = max(1, min(100, int(scene.render.resolution_percentage)))
    samples = samples_for_scene(scene)
    engine_kw = render_engine_billing_keyword(scene)
    render_engine = "cycles" if engine_kw == "cycles" else "eevee"
    denoising = False
    if scene.render.engine == "CYCLES":
        denoising = bool(getattr(scene.cycles, "use_denoising", False))
    instance_type = TIER_INSTANCE_MAP.get(
        memory_tier, TIER_INSTANCE_MAP[ADDON_INSTANCE_MEMORY_TIER]
    )
    return {
        "instanceType": instance_type,
        "frames": {
            "start": int(props.frame_start),
            "end": int(props.frame_end),
        },
        "resolutionScale": pct,
        "samples": samples,
        "renderEngine": render_engine,
        "denoisingEnabled": denoising,
        "outputFormat": props.output_format,
    }


def post_blender_metadata(
    context: bpy.types.Context, token: str, s3_key: str
) -> ApiResponse:
    client = make_client(context, token)
    return client.post("/blender/metadata", {"s3_key": s3_key})


def get_job_logs_status(
    context: bpy.types.Context, token: str, public_id: str
) -> ApiResponse:
    client = make_client(context, token)
    return client.get(f"/jobs/{public_id}/logs/status")


def get_job_log_presigned_url(
    context: bpy.types.Context, token: str, public_id: str
) -> ApiResponse:
    """GET /jobs/:id/log-url — presigned S3 URL for renderbob.log when available."""
    client = make_client(context, token)
    return client.get(f"/jobs/{public_id}/log-url")


def poll_latest_quote_until_ready(
    context: bpy.types.Context,
    token: str,
    public_id: str,
    timeout_sec: float = 180.0,
    interval: float = 2.0,
    after_sleep: Optional[Callable[[], None]] = None,
) -> Tuple[bool, Dict[str, Any], Optional[str]]:
    deadline = time.time() + timeout_sec
    last: Dict[str, Any] = {}
    while time.time() < deadline:
        response = latest_quote(context, token, public_id)
        if not response.ok:
            return False, {}, response.error or "Failed to fetch latest quote"
        data = response.data.get("data", response.data)
        last = data if isinstance(data, dict) else {}
        st = last.get("samplingStatus")
        if st == "done":
            return True, last, None
        if st == "failed":
            return (
                False,
                last,
                str(last.get("samplingError") or "Sampling failed"),
            )
        if after_sleep:
            after_sleep()
        time.sleep(interval)
    return False, last, "Timed out waiting for sampling / quote"


def request_upload_url(
    context: bpy.types.Context,
    token: str,
    file_name: str,
) -> ApiResponse:
    mime = mimetypes.guess_type(file_name)[0] or "application/octet-stream"
    client = make_client(context, token)
    return client.get("/jobs/upload-url", {"fileName": file_name, "fileType": mime})


def multipart_upload_scene(
    context: bpy.types.Context,
    token: str,
    scene_path: Path,
    cancel_flag,
    progress_callback,
    max_retries: int = 2,
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Returns (ok, s3_key, error_message).
    """
    client = make_client(context, token)
    mime = mimetypes.guess_type(scene_path.name)[0] or "application/octet-stream"
    init_response = client.post(
        "/jobs/multipart/init",
        {
            "fileName": scene_path.name,
            "fileType": mime,
            "fileSize": scene_path.stat().st_size,
        },
    )
    if not init_response.ok:
        return False, None, init_response.error or "Failed to initialize multipart upload"

    init_data = init_response.data.get("data", {})
    upload_id = init_data.get("uploadId")
    s3_key = init_data.get("key")
    part_size = int(init_data.get("partSize", 10 * 1024 * 1024))
    if not upload_id or not s3_key:
        return False, None, "Multipart init did not return uploadId/key"

    file_size = scene_path.stat().st_size
    part_count = max(1, (file_size + part_size - 1) // part_size)
    uploaded_parts = []

    with scene_path.open("rb") as stream:
        for part_number in range(1, part_count + 1):
            if cancel_flag():
                _abort_multipart(client, s3_key, upload_id)
                return False, None, "Upload cancelled by user"

            part_bytes = stream.read(part_size)
            if not part_bytes:
                break

            part_url_response = client.post(
                "/jobs/multipart/part-url",
                {"key": s3_key, "uploadId": upload_id, "partNumber": part_number},
            )
            if not part_url_response.ok:
                _abort_multipart(client, s3_key, upload_id)
                return False, None, part_url_response.error or "Failed to get part URL"

            url_data = part_url_response.data.get("data", {})
            part_url = url_data.get("url")
            if not part_url:
                _abort_multipart(client, s3_key, upload_id)
                return False, None, "Multipart part URL missing"

            etag = None
            for attempt in range(max_retries + 1):
                try:
                    request = Request(part_url, data=part_bytes, method="PUT")
                    with urlopen(request, timeout=180) as response:
                        etag = response.headers.get("ETag", "").replace('"', "")
                    break
                except Exception as error:
                    if attempt >= max_retries:
                        _abort_multipart(client, s3_key, upload_id)
                        return False, None, f"Failed uploading part {part_number}: {error}"
            if not etag:
                _abort_multipart(client, s3_key, upload_id)
                return False, None, f"Missing ETag for part {part_number}"

            uploaded_parts.append({"PartNumber": part_number, "ETag": etag})
            progress_callback(part_number / float(part_count))

    complete_response = client.post(
        "/jobs/multipart/complete",
        {"key": s3_key, "uploadId": upload_id, "parts": uploaded_parts},
    )
    if not complete_response.ok:
        _abort_multipart(client, s3_key, upload_id)
        return False, None, complete_response.error or "Failed to complete multipart upload"

    return True, str(s3_key), None


def _abort_multipart(client, key: str, upload_id: str) -> None:
    try:
        client.post("/jobs/multipart/abort", {"key": key, "uploadId": upload_id})
    except Exception as error:
        log_error(f"Multipart abort failed: {error}")


def upload_file_to_s3_presigned_post(
    scene_path: Path,
    upload_data: Dict[str, object],
) -> Tuple[bool, Optional[str]]:
    url = upload_data.get("url")
    fields = upload_data.get("fields")
    if not isinstance(url, str) or not isinstance(fields, dict):
        return False, "Invalid upload payload from backend"

    file_bytes = scene_path.read_bytes()
    content_type = mimetypes.guess_type(scene_path.name)[0] or "application/octet-stream"
    boundary = "----RenderBobBoundary7MA4YWxkTrZu0gW"

    body = bytearray()
    for key, value in fields.items():
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(
            f'Content-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode(
                "utf-8"
            )
        )
    body.extend(f"--{boundary}\r\n".encode("utf-8"))
    body.extend(
        f'Content-Disposition: form-data; name="file"; filename="{scene_path.name}"\r\n'.encode(
            "utf-8"
        )
    )
    body.extend(f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"))
    body.extend(file_bytes)
    body.extend("\r\n".encode("utf-8"))
    body.extend(f"--{boundary}--\r\n".encode("utf-8"))

    request = Request(
        url,
        data=bytes(body),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=120):
            return True, None
    except Exception as error:
        log_error(f"S3 upload failed: {error}")
        return False, f"Upload failed: {error}"


def create_draft_job(
    context: bpy.types.Context,
    token: str,
    name: str,
    file_url: str,
) -> ApiResponse:
    client = make_client(context, token)
    return client.post("/jobs/draft", {"name": name, "fileUrl": file_url})


def publish_job(
    context: bpy.types.Context,
    token: str,
    payload: Dict[str, object],
) -> ApiResponse:
    client = make_client(context, token)
    return client.post("/jobs/publish", payload)


def estimate_job(
    context: bpy.types.Context,
    token: str,
    public_id: str,
    payload: Dict[str, Any],
) -> ApiResponse:
    client = make_client(context, token)
    return client.post(f"/jobs/{public_id}/estimate", payload)


def latest_quote(context: bpy.types.Context, token: str, public_id: str) -> ApiResponse:
    client = make_client(context, token)
    return client.get(f"/jobs/{public_id}/latest-quote")


def pay_job(
    context: bpy.types.Context,
    token: str,
    public_id: str,
    quote_id: str,
) -> ApiResponse:
    client = make_client(context, token)
    try:
        qid = int(str(quote_id).strip())
    except ValueError:
        qid = quote_id
    return client.post(f"/jobs/{public_id}/pay", {"quoteId": qid})


def cancel_payment(
    context: bpy.types.Context,
    token: str,
    public_id: str,
    billing_transaction_id: str,
) -> ApiResponse:
    client = make_client(context, token)
    return client.post(
        f"/jobs/{public_id}/cancel-payment",
        {"billingTransactionId": billing_transaction_id},
    )


def payment_status(context: bpy.types.Context, token: str, public_id: str) -> ApiResponse:
    client = make_client(context, token)
    return client.get(f"/billing/jobs/{public_id}/status")


def get_job(context: bpy.types.Context, token: str, public_id: str) -> ApiResponse:
    client = make_client(context, token)
    return client.get(f"/jobs/{public_id}")


def get_job_progress(context: bpy.types.Context, token: str, public_id: str) -> ApiResponse:
    client = make_client(context, token)
    return client.get(f"/jobs/{public_id}/progress")


def terminate_job(context: bpy.types.Context, token: str, public_id: str) -> ApiResponse:
    client = make_client(context, token)
    return client.post(f"/jobs/{public_id}/terminate", {})


def retry_launch(context: bpy.types.Context, token: str, public_id: str) -> ApiResponse:
    client = make_client(context, token)
    return client.post(f"/jobs/{public_id}/retry-launch", {})


def list_outputs(context: bpy.types.Context, token: str, public_id: str) -> ApiResponse:
    client = make_client(context, token)
    return client.get(f"/jobs/{public_id}/outputs")


def request_output_download(
    context: bpy.types.Context,
    token: str,
    public_id: str,
    file_name: str,
) -> ApiResponse:
    client = make_client(context, token)
    return client.get(f"/jobs/{public_id}/outputs/{file_name}/download")


def request_outputs_zip(context: bpy.types.Context, token: str, public_id: str) -> ApiResponse:
    client = make_client(context, token)
    return client.post(f"/jobs/{public_id}/outputs/zip-request", {})


def zip_request_status(
    context: bpy.types.Context,
    token: str,
    public_id: str,
    zip_request_id: str,
) -> ApiResponse:
    client = make_client(context, token)
    return client.get(f"/jobs/{public_id}/outputs/zip-request/{zip_request_id}")


def download_from_url(url: str, destination_path: Path) -> Tuple[bool, Optional[str]]:
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    request = Request(url, method="GET")
    try:
        with urlopen(request, timeout=180) as response:
            destination_path.write_bytes(response.read())
        log_info(f"Downloaded output to {destination_path}")
        return True, None
    except Exception as error:
        log_error(f"Download failed: {error}")
        return False, str(error)


def parse_json_text(value: str) -> Dict[str, object]:
    try:
        return json.loads(value)
    except Exception:
        return {}
