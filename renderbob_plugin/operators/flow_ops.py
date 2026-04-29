"""Simplified submit flow: upload + estimate, start render + pay, results dialog."""
from __future__ import annotations

from pathlib import Path

import bpy

from ..job_lifecycle import (
    render_panel_phase_from_context,
    should_allow_upload_and_estimate,
    should_show_start_render_operator,
)
from ..logging_utils import log_error, log_info
from ..polling import sync_job_snapshot_once
from ..quote_poll import start_quote_poll_timer
from ..state import STATE
from ..submit_utils import (
    apply_quote_block_to_props,
    safe_progress_end,
    tag_renderbob_sidebar_redraw,
)
from ..workflows import (
    build_estimate_payload,
    build_publish_draft_payload,
    create_draft_job,
    estimate_job,
    list_outputs,
    multipart_upload_scene,
    pay_job,
    post_blender_metadata,
    preflight_validate,
    publish_job,
    refresh_render_server_selection,
    scene_file_path,
)


def _token(context: bpy.types.Context) -> str:
    return context.scene.renderbob.api_token.strip()


def _require_auth(context: bpy.types.Context, op: bpy.types.Operator) -> bool:
    if not _token(context):
        op.report({"ERROR"}, "API token is required")
        return False
    return True


class RENDERBOB_OT_upload_and_estimate_disabled(bpy.types.Operator):
    """Shown greyed out while the job is queued so users see Upload is unavailable."""

    bl_idname = "renderbob.upload_and_estimate_disabled"
    bl_label = "Upload and Estimate"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        if STATE.upload_estimate_stage != "idle":
            return False
        return render_panel_phase_from_context(context) == "pending"

    def execute(self, context):
        return {"CANCELLED"}


class RENDERBOB_OT_upload_and_estimate(bpy.types.Operator):
    bl_idname = "renderbob.upload_and_estimate"
    bl_label = "Upload and Estimate"

    @classmethod
    def poll(cls, context):
        if STATE.upload_estimate_stage != "idle":
            return False
        return should_allow_upload_and_estimate(context)

    def execute(self, context: bpy.types.Context):
        wm = context.window_manager
        props = context.scene.renderbob

        def finish_idle():
            STATE.upload_estimate_stage = "idle"
            safe_progress_end(wm)
            tag_renderbob_sidebar_redraw()

        if not _require_auth(context, self):
            return {"CANCELLED"}
        if not should_allow_upload_and_estimate(context):
            self.report(
                {"ERROR"},
                "Upload and Estimate is not available while this job is queued or rendering.",
            )
            return {"CANCELLED"}
        STATE.awaiting_stripe_checkout = False
        ok, message = preflight_validate(context)
        if not ok:
            self.report({"ERROR"}, message)
            return {"CANCELLED"}

        token = _token(context)
        scene_path = scene_file_path()
        if not scene_path:
            self.report({"ERROR"}, "Save your .blend file first")
            return {"CANCELLED"}

        ok_srv, srv_msg = refresh_render_server_selection(context, token)
        if not ok_srv:
            self.report({"ERROR"}, srv_msg)
            return {"CANCELLED"}

        STATE.diagnostics["cancel_upload"] = False
        props.progress = 0.0
        STATE.upload_progress = 0.0
        STATE.upload_estimate_stage = "uploading"
        tag_renderbob_sidebar_redraw()

        success = False
        s3_key = None
        upload_error = None
        wm.progress_begin(0, 100)
        try:

            def cancel_flag():
                return bool(STATE.diagnostics.get("cancel_upload"))

            def progress_callback(factor: float):
                f = max(0.0, min(1.0, factor))
                props.progress = f
                STATE.upload_progress = f
                try:
                    wm.progress_update(min(99, int(f * 100)))
                except Exception:
                    pass
                tag_renderbob_sidebar_redraw()

            success, s3_key, upload_error = multipart_upload_scene(
                context,
                token,
                scene_path,
                cancel_flag,
                progress_callback,
            )
        finally:
            safe_progress_end(wm)

        s3_key = s3_key or ""

        if not success:
            finish_idle()
            self.report({"ERROR"}, upload_error or "Upload failed")
            return {"CANCELLED"}

        props.upload_s3_key = s3_key or ""
        props.progress = 1.0
        STATE.upload_progress = 1.0
        STATE.upload_estimate_stage = "estimating"
        tag_renderbob_sidebar_redraw()

        meta = post_blender_metadata(context, token, s3_key or "")
        if not meta.ok:
            log_error(meta.error or "metadata extract failed (continuing)")

        job_name = props.job_name.strip() or Path(bpy.data.filepath).stem
        draft = create_draft_job(context, token, job_name, s3_key or "")
        if not draft.ok:
            finish_idle()
            self.report({"ERROR"}, draft.error or "Draft creation failed")
            return {"CANCELLED"}

        public_id = (
            draft.data.get("public_id")
            or draft.data.get("publicId")
            or draft.data.get("data", {}).get("public_id")
            or draft.data.get("data", {}).get("publicId")
        )
        props.draft_public_id = str(public_id or "")
        STATE.active_job_public_id = props.draft_public_id

        payload = build_estimate_payload(context, props)
        est = estimate_job(context, token, props.draft_public_id, payload)
        if not est.ok:
            finish_idle()
            self.report({"ERROR"}, est.error or "Estimate failed")
            return {"CANCELLED"}

        data = est.data.get("data", est.data)
        status = data.get("status")
        if status == "done":
            apply_quote_block_to_props(props, data)
        elif status == "resampling":
            # Do not block the main thread with time.sleep loops — freezes Blender.
            start_quote_poll_timer(props.draft_public_id)
            self.report(
                {"INFO"},
                "Sampling in progress — estimate will appear when ready (you can keep working).",
            )
            log_info(f"upload_and_estimate job={props.draft_public_id} resampling async")
            tag_renderbob_sidebar_redraw()
            return {"FINISHED"}
        else:
            finish_idle()
            self.report({"ERROR"}, f"Unexpected estimate status: {status}")
            return {"CANCELLED"}

        finish_idle()
        STATE.status_message = "Estimate ready — review cost, then Start render"
        self.report({"INFO"}, "Upload and estimate complete")
        log_info(f"upload_and_estimate job={props.draft_public_id}")
        return {"FINISHED"}


class RENDERBOB_OT_start_render(bpy.types.Operator):
    bl_idname = "renderbob.start_render"
    bl_label = "Start render"

    @classmethod
    def poll(cls, context):
        return should_show_start_render_operator(context)

    def execute(self, context: bpy.types.Context):
        if not _require_auth(context, self):
            return {"CANCELLED"}
        if render_panel_phase_from_context(context) != "draft":
            self.report(
                {"ERROR"},
                "Start render is only available while the job is still a draft with a quote.",
            )
            return {"CANCELLED"}
        props = context.scene.renderbob
        if not props.draft_public_id:
            self.report({"ERROR"}, "Run Upload and Estimate first")
            return {"CANCELLED"}
        if not props.quote_id:
            self.report({"ERROR"}, "No quote — run Upload and Estimate first")
            return {"CANCELLED"}

        token = _token(context)
        if not props.server_public_id or not props.server_meta_public_id:
            ok, msg = refresh_render_server_selection(context, token)
            if not ok:
                self.report({"ERROR"}, msg)
                return {"CANCELLED"}

        payload, err = build_publish_draft_payload(context, props)
        if err or not payload:
            self.report({"ERROR"}, err or "Could not build publish payload")
            return {"CANCELLED"}

        pub = publish_job(context, token, payload)
        if not pub.ok:
            self.report({"ERROR"}, pub.error or "Publish failed")
            return {"CANCELLED"}

        pay = pay_job(context, token, props.draft_public_id, props.quote_id)
        if not pay.ok:
            self.report({"ERROR"}, pay.error or "Payment failed")
            return {"CANCELLED"}

        pdata = pay.data.get("data", pay.data)
        props.billing_transaction_id = str(pdata.get("billingTransactionId", "") or "")

        if pdata.get("paid"):
            STATE.awaiting_stripe_checkout = False
            STATE.status_message = "Paid with credits — render starting"
            sync_job_snapshot_once(context, token, props.draft_public_id)
            self.report({"INFO"}, STATE.status_message)
            return {"FINISHED"}

        checkout = pdata.get("stripeCheckoutUrl")
        if checkout:
            STATE.awaiting_stripe_checkout = True
            bpy.ops.wm.url_open(url=str(checkout))
            STATE.status_message = (
                "Stripe checkout opened in your browser. "
                "Complete payment and return to Blender when ready."
            )
            sync_job_snapshot_once(context, token, props.draft_public_id)
            self.report({"INFO"}, STATE.status_message)
            return {"FINISHED"}

        STATE.status_message = "Payment response received — waiting for confirmation"
        sync_job_snapshot_once(context, token, props.draft_public_id)
        self.report({"INFO"}, STATE.status_message)
        return {"FINISHED"}


class RENDERBOB_OT_download_named_output(bpy.types.Operator):
    bl_idname = "renderbob.download_named_output"
    bl_label = "Download"
    file: bpy.props.StringProperty(options={"SKIP_SAVE"})

    def execute(self, context: bpy.types.Context):
        context.scene.renderbob.selected_output_file = self.file
        return bpy.ops.renderbob.download_output("EXEC_DEFAULT")


class RENDERBOB_OT_show_results(bpy.types.Operator):
    bl_idname = "renderbob.show_results"
    bl_label = "See results"

    def _refresh(self, context: bpy.types.Context) -> bool:
        if not _require_auth(context, self):
            return False
        public_id = context.scene.renderbob.draft_public_id or STATE.active_job_public_id
        if not public_id:
            return False
        response = list_outputs(context, _token(context), public_id)
        if not response.ok:
            return False
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
        return True

    def invoke(self, context: bpy.types.Context, event):
        self._refresh(context)
        return context.window_manager.invoke_props_dialog(self, width=520)

    def draw(self, context: bpy.types.Context):
        layout = self.layout
        layout.operator("renderbob.refresh_results_list", text="Refresh outputs")
        layout.separator()
        if not STATE.output_files:
            layout.label(text="No outputs yet — try Refresh.")
            return
        for name in STATE.output_files:
            r = layout.row(align=True)
            r.label(text=name)
            d = r.operator("renderbob.download_named_output", text="Download")
            d.file = name

    def execute(self, context: bpy.types.Context):
        return {"FINISHED"}


class RENDERBOB_OT_refresh_results_list(bpy.types.Operator):
    bl_idname = "renderbob.refresh_results_list"
    bl_label = "Refresh outputs"

    def execute(self, context: bpy.types.Context):
        public_id = context.scene.renderbob.draft_public_id or STATE.active_job_public_id
        if not public_id or not _token(context):
            return {"CANCELLED"}
        response = list_outputs(context, _token(context), public_id)
        if not response.ok:
            return {"CANCELLED"}
        data = response.data.get("data", response.data)
        if isinstance(data, list):
            STATE.output_files = [
                str(item.get("fileName", item)) if isinstance(item, dict) else str(item)
                for item in data
            ]
        return {"FINISHED"}
