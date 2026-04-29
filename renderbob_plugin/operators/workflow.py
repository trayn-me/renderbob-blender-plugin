from pathlib import Path

import bpy

from ..constants import ADDON_ID
from ..job_lifecycle import (
    render_panel_phase_from_context,
    should_allow_terminate_job,
)
from ..logging_utils import log_info
from ..state import STATE
from ..workflows import (
    download_from_url,
    fetch_credits,
    get_job_log_presigned_url,
    list_outputs,
    refresh_render_server_selection,
    request_output_download,
    terminate_job,
)


def _token(context: bpy.types.Context) -> str:
    return context.scene.renderbob.api_token.strip()


def _require_auth(context: bpy.types.Context, operator: bpy.types.Operator) -> bool:
    if not _token(context):
        operator.report({"ERROR"}, "API token is required")
        return False
    return True


class RENDERBOB_OT_refresh_account_context(bpy.types.Operator):
    bl_idname = "renderbob.refresh_account_context"
    bl_label = "Refresh Account"

    def execute(self, context):
        if not _require_auth(context, self):
            return {"CANCELLED"}

        token = _token(context)
        credits_response = fetch_credits(context, token)
        if not credits_response.ok:
            message = credits_response.error or "Failed to fetch credits"
            STATE.last_error = message
            STATE.status_message = message
            self.report({"ERROR"}, message)
            return {"CANCELLED"}

        credits_eur = credits_response.data.get("creditsAvailableEur")
        STATE.credits_eur = str(credits_eur) if credits_eur is not None else None

        srv_ok, srv_msg = refresh_render_server_selection(context, token)
        if not srv_ok:
            STATE.last_error = srv_msg
            STATE.status_message = srv_msg
            self.report({"ERROR"}, srv_msg)
            return {"CANCELLED"}

        STATE.diagnostics["resolved_server_message"] = srv_msg
        STATE.last_error = None
        STATE.status_message = f"{srv_msg} Credits refreshed."
        self.report({"INFO"}, STATE.status_message)
        return {"FINISHED"}


class RENDERBOB_OT_queue_waiting(bpy.types.Operator):
    """Disabled-looking control while the paid job waits in the farm queue."""

    bl_idname = "renderbob.queue_waiting"
    bl_label = "Waiting to be picked up"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return render_panel_phase_from_context(context) == "pending"

    def execute(self, context):
        self.report({"INFO"}, "Job is waiting in the render queue.")
        return {"FINISHED"}


class RENDERBOB_OT_download_job_logs(bpy.types.Operator):
    bl_idname = "renderbob.download_job_logs"
    bl_label = "Download logs"

    @classmethod
    def poll(cls, context):
        if not _token(context):
            return False
        return render_panel_phase_from_context(context) == "failed"

    def execute(self, context):
        if not _require_auth(context, self):
            return {"CANCELLED"}
        public_id = context.scene.renderbob.draft_public_id or STATE.active_job_public_id
        if not public_id:
            self.report({"ERROR"}, "No job selected")
            return {"CANCELLED"}
        response = get_job_log_presigned_url(context, _token(context), public_id)
        if not response.ok:
            self.report({"ERROR"}, response.error or "Could not request log URL")
            return {"CANCELLED"}
        data = response.data if isinstance(response.data, dict) else {}
        if data.get("success") is False:
            err = data.get("error") or "No log file available yet"
            self.report({"ERROR"}, str(err))
            return {"CANCELLED"}
        url = data.get("url")
        if not url:
            self.report({"ERROR"}, "No log download URL returned by backend")
            return {"CANCELLED"}

        addon_prefs = context.preferences.addons[ADDON_ID].preferences
        out_dir = Path(bpy.path.abspath(addon_prefs.download_path or "//"))
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"renderbob-{public_id}-renderbob.log"
        success, error = download_from_url(str(url), out_path)
        if not success:
            self.report({"ERROR"}, error or "Download failed")
            return {"CANCELLED"}
        log_info(f"Downloaded job logs to {out_path.name}")
        self.report({"INFO"}, f"Saved logs to {out_path}")
        return {"FINISHED"}


class RENDERBOB_OT_terminate_job(bpy.types.Operator):
    bl_idname = "renderbob.terminate_job"
    bl_label = "Terminate"

    @classmethod
    def poll(cls, context):
        if not _token(context):
            return False
        return should_allow_terminate_job(context)

    def execute(self, context):
        if not _require_auth(context, self):
            return {"CANCELLED"}
        public_id = context.scene.renderbob.draft_public_id or STATE.active_job_public_id
        if not public_id:
            self.report({"ERROR"}, "No job selected")
            return {"CANCELLED"}
        response = terminate_job(context, _token(context), public_id)
        if not response.ok:
            self.report({"ERROR"}, response.error or "Terminate failed")
            return {"CANCELLED"}
        STATE.status_message = "Termination requested"
        self.report({"INFO"}, STATE.status_message)
        return {"FINISHED"}


class RENDERBOB_OT_list_outputs(bpy.types.Operator):
    bl_idname = "renderbob.list_outputs"
    bl_label = "List Outputs"

    def execute(self, context):
        if not _require_auth(context, self):
            return {"CANCELLED"}
        public_id = context.scene.renderbob.draft_public_id or STATE.active_job_public_id
        if not public_id:
            self.report({"ERROR"}, "No job selected")
            return {"CANCELLED"}
        response = list_outputs(context, _token(context), public_id)
        if not response.ok:
            self.report({"ERROR"}, response.error or "Failed to list outputs")
            return {"CANCELLED"}

        data = response.data.get("data", response.data)
        if isinstance(data, list):
            files = [
                str(item.get("fileName", item)) if isinstance(item, dict) else str(item)
                for item in data
            ]
        else:
            files = []
        STATE.output_files = files
        if files:
            context.scene.renderbob.selected_output_file = files[0]
        STATE.status_message = f"Loaded {len(files)} outputs"
        self.report({"INFO"}, STATE.status_message)
        return {"FINISHED"}


class RENDERBOB_OT_download_output(bpy.types.Operator):
    bl_idname = "renderbob.download_output"
    bl_label = "Download Output"

    def execute(self, context):
        if not _require_auth(context, self):
            return {"CANCELLED"}
        props = context.scene.renderbob
        public_id = props.draft_public_id or STATE.active_job_public_id
        file_name = props.selected_output_file.strip()
        if not public_id or not file_name:
            self.report({"ERROR"}, "Job ID and output file are required")
            return {"CANCELLED"}
        response = request_output_download(context, _token(context), public_id, file_name)
        if not response.ok:
            self.report({"ERROR"}, response.error or "Failed to request output download URL")
            return {"CANCELLED"}

        data = response.data.get("data", response.data)
        url = data.get("url") or data.get("downloadUrl")
        if not url:
            self.report({"ERROR"}, "No download URL returned by backend")
            return {"CANCELLED"}

        addon_prefs = context.preferences.addons[ADDON_ID].preferences
        out_dir = bpy.path.abspath(addon_prefs.download_path or "//")
        out_path = Path(out_dir) / Path(file_name).name
        success, error = download_from_url(url, out_path)
        if not success:
            self.report({"ERROR"}, error or "Download failed")
            return {"CANCELLED"}
        log_info(f"Downloaded {out_path.name}")
        self.report({"INFO"}, f"Downloaded {out_path.name}")
        return {"FINISHED"}
