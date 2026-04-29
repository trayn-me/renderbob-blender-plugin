import bpy

from .constants import ADDON_ID
from .job_lifecycle import (
    render_panel_phase_from_context,
    should_allow_upload_and_estimate,
    should_show_start_render_operator,
)
from .preferences import load_preferences_into_addon
from .polling import needs_onboarding
from .state import STATE
from .storage import load_settings


def _bootstrap_from_settings(context):
    if STATE.bootstrapped:
        return
    settings = load_settings()

    if context.scene and hasattr(context.scene, "renderbob"):
        token = settings.get("api_token", "")
        if token and not context.scene.renderbob.api_token:
            context.scene.renderbob.api_token = token

    addon = context.preferences.addons.get(ADDON_ID)
    if addon and addon.preferences:
        load_preferences_into_addon(addon.preferences)

    STATE.bootstrapped = True


def _job_dict():
    job = STATE.job_snapshot.get("job")
    return job if isinstance(job, dict) else None


def _draw_render_primary_block(layout, context, phase: str):
    """Primary actions live at the top of the Render panel."""
    scene_props = context.scene.renderbob

    if phase == "active":
        if bpy.app.version >= (4, 0, 0):
            layout.progress(factor=scene_props.progress, type="BAR")
        layout.label(text=f"Render progress: {scene_props.progress * 100:.0f}%")
        if STATE.log_status_line:
            layout.label(text=STATE.log_status_line)
        layout.separator()
        layout.operator("renderbob.terminate_job", text="Terminate")
        return

    if phase == "failed":
        layout.operator("renderbob.download_job_logs", text="Download logs")
        return

    if phase == "completed":
        layout.operator("renderbob.show_results", text="See results")
        return

    if phase == "pending":
        row = layout.row()
        row.enabled = False
        row.operator("renderbob.queue_waiting", text="Waiting to be picked up")
        row2 = layout.row()
        row2.enabled = False
        row2.operator("renderbob.upload_and_estimate_disabled", text="Upload and Estimate")
        return

    if phase == "syncing":
        layout.label(text="Fetching job status…")
        return

    # idle — no linked job id
    if phase == "idle":
        upload_ok = (
            STATE.upload_estimate_stage == "idle"
            and should_allow_upload_and_estimate(context)
        )
        if upload_ok:
            big = layout.row()
            big.scale_y = 1.25
            big.operator("renderbob.upload_and_estimate", text="Upload and Estimate")
        return

    # draft
    if STATE.estimate_line1:
        layout.label(text=STATE.estimate_line1)
    if STATE.estimate_line2:
        layout.label(text=STATE.estimate_line2)

    upload_ok = (
        STATE.upload_estimate_stage == "idle"
        and should_allow_upload_and_estimate(context)
    )
    start_ok = should_show_start_render_operator(context)

    big = layout.row()
    big.scale_y = 1.25
    if start_ok:
        big.operator("renderbob.start_render", text="Start render")
    elif upload_ok:
        big.operator("renderbob.upload_and_estimate", text="Upload and Estimate")

    if start_ok and upload_ok:
        layout.operator("renderbob.upload_and_estimate", text="Upload and Estimate")


class RENDERBOB_PT_main(bpy.types.Panel):
    bl_label = "RenderBob"
    bl_idname = "RENDERBOB_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "RenderBob"

    def draw(self, context):
        _bootstrap_from_settings(context)
        layout = self.layout
        if needs_onboarding():
            layout.label(text="Welcome to RenderBob")
            layout.operator("renderbob.setup_account", text="Setup RenderBob account")
            layout.label(text="Opens User Management in your browser.")
            layout.label(text="Create or regenerate an API key, then")
            layout.label(text="paste it under Authentication → Verify.")
            return

        layout.label(text=STATE.status_message)
        if STATE.active_job_public_id:
            layout.label(text=f"Job: {STATE.active_job_public_id}")
        if STATE.active_job_status:
            layout.label(text=f"Status: {STATE.active_job_status}")


class RENDERBOB_PT_authentication(bpy.types.Panel):
    bl_label = "Authentication"
    bl_idname = "RENDERBOB_PT_authentication"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "RenderBob"
    bl_parent_id = "RENDERBOB_PT_main"

    @classmethod
    def poll(cls, context):
        return not needs_onboarding()

    def draw(self, context):
        _bootstrap_from_settings(context)
        layout = self.layout
        scene_props = context.scene.renderbob
        layout.prop(scene_props, "api_token")
        row = layout.row(align=True)
        row.operator("renderbob.verify_api_token", text="Verify")
        row.operator("renderbob.logout", text="Logout")
        layout.operator("renderbob.refresh_account_context", text="Refresh Account")
        if STATE.credits_eur is not None:
            layout.label(text=f"Credits: EUR {STATE.credits_eur}")


class RENDERBOB_PT_render(bpy.types.Panel):
    bl_label = "Render"
    bl_idname = "RENDERBOB_PT_render"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "RenderBob"
    bl_parent_id = "RENDERBOB_PT_main"

    @classmethod
    def poll(cls, context):
        return not needs_onboarding() and STATE.auth_ok

    def draw(self, context):
        _bootstrap_from_settings(context)
        layout = self.layout
        scene_props = context.scene.renderbob
        phase = render_panel_phase_from_context(context)
        job = _job_dict() or {}

        _draw_render_primary_block(layout, context, phase)

        if STATE.awaiting_stripe_checkout and phase == "draft":
            layout.label(text="Complete payment in the browser…")

        if STATE.upload_estimate_stage == "uploading":
            layout.separator()
            if bpy.app.version >= (4, 0, 0):
                layout.progress(factor=scene_props.progress, type="BAR")
            layout.label(text=f"Uploading scene… {scene_props.progress * 100:.0f}%")
        elif STATE.upload_estimate_stage == "estimating":
            layout.separator()
            layout.label(text="Creating draft and fetching estimate…")

        if phase == "failed":
            err = job.get("error_summary") or job.get("errorSummary")
            if err:
                layout.label(text=str(err)[:200])
            elif STATE.last_error:
                layout.label(text=str(STATE.last_error)[:120])

        layout.separator()

        if phase in ("idle", "draft", "syncing", "failed"):
            layout.prop(scene_props, "job_name")
            layout.prop(scene_props, "frame_start")
            layout.prop(scene_props, "frame_end")
            layout.prop(scene_props, "frame_step")
            layout.prop(scene_props, "output_format")
            row_sr = layout.row()
            row_sr.enabled = STATE.upload_estimate_stage == "idle" and phase not in (
                "pending",
                "active",
                "completed",
            )
            row_sr.operator("renderbob.use_scene_range", text="Use Scene Frame Range")


UI_CLASSES = (
    RENDERBOB_PT_main,
    RENDERBOB_PT_authentication,
    RENDERBOB_PT_render,
)
