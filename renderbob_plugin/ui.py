import bpy

from .constants import ADDON_ID
from .job_lifecycle import render_panel_phase_from_context
from .preferences import load_preferences_into_addon
from .polling import needs_onboarding
from .state import STATE
from .storage import load_settings

_deferred_disk_hydrate_armed = False


def _deferred_disk_hydrate_timer():
    """Apply disk settings outside Panel.draw (Blender 5+ restricts Scene RNA writes in draw)."""
    global _deferred_disk_hydrate_armed
    _deferred_disk_hydrate_armed = False
    try:
        settings = load_settings()
        token = (settings.get("api_token", "") or "").strip()
        scene = bpy.context.scene
        if scene and hasattr(scene, "renderbob") and token:
            if not (scene.renderbob.api_token or "").strip():
                scene.renderbob.api_token = token
        addon = bpy.context.preferences.addons.get(ADDON_ID)
        if addon and addon.preferences:
            load_preferences_into_addon(addon.preferences)
    except Exception:
        pass
    return None


def _schedule_deferred_disk_hydrate() -> None:
    global _deferred_disk_hydrate_armed
    if _deferred_disk_hydrate_armed:
        return
    _deferred_disk_hydrate_armed = True
    bpy.app.timers.register(_deferred_disk_hydrate_timer, first_interval=0.0)


def _bootstrap_from_settings(context):
    if STATE.bootstrapped:
        return
    settings = load_settings()
    need_deferred = False

    if context.scene and hasattr(context.scene, "renderbob"):
        token = (settings.get("api_token", "") or "").strip()
        if token and not (context.scene.renderbob.api_token or "").strip():
            try:
                context.scene.renderbob.api_token = token
            except AttributeError:
                need_deferred = True

    addon = context.preferences.addons.get(ADDON_ID)
    if addon and addon.preferences:
        try:
            load_preferences_into_addon(addon.preferences)
        except AttributeError:
            need_deferred = True

    if need_deferred:
        _schedule_deferred_disk_hydrate()

    STATE.bootstrapped = True


def _draw_job_status_box(layout: bpy.types.UILayout, context: bpy.types.Context) -> None:
    scene_props = context.scene.renderbob
    phase = render_panel_phase_from_context(context)

    if not (STATE.auth_ok and phase != "idle"):
        return

    box = layout.box()
    row = box.row(align=True)
    row.label(text=f"Job: {phase}", icon="RENDER_RESULT")
    if STATE.active_job_public_id or scene_props.draft_public_id:
        pid = scene_props.draft_public_id or STATE.active_job_public_id or ""
        row.label(text=str(pid)[:36])
    if phase == "active":
        if bpy.app.version >= (4, 0, 0):
            box.prop(scene_props, "progress", slider=True, text="Progress")
        if STATE.log_status_line:
            box.label(text=STATE.log_status_line)
        box.operator("renderbob.terminate_job", text="Terminate render")
    elif phase == "failed":
        box.operator("renderbob.download_job_logs", text="Download logs")
    elif phase == "completed":
        box.operator("renderbob.show_results", text="See results")
    elif phase == "pending":
        box.label(text="Waiting in queue…")
    elif STATE.upload_estimate_stage == "uploading":
        if bpy.app.version >= (4, 0, 0):
            box.prop(scene_props, "progress", slider=True, text="Upload")
        box.label(text="Uploading scene…")
    elif STATE.upload_estimate_stage == "estimating":
        box.label(text="Fetching estimate…")
    if STATE.awaiting_stripe_checkout and phase == "draft":
        box.label(text="Complete payment in the browser if prompted…")


def _draw_cloud_job_fields(layout: bpy.types.UILayout, context: bpy.types.Context) -> None:
    scene_props = context.scene.renderbob
    phase = render_panel_phase_from_context(context)
    jbox = layout.box()
    jbox.label(text="Cloud job fields", icon="SETTINGS")
    jbox.prop(scene_props, "job_name")
    rowf = jbox.row(align=True)
    rowf.prop(scene_props, "frame_start", text="Start")
    rowf.prop(scene_props, "frame_end", text="End")
    rowf.prop(scene_props, "frame_step", text="Step")
    jbox.prop(scene_props, "output_format")
    rowu = jbox.row()
    rowu.enabled = STATE.upload_estimate_stage == "idle" and phase not in (
        "pending",
        "active",
        "completed",
    )
    rowu.operator("renderbob.use_scene_range", text="Use scene frame range")


def _draw_quote_summary(layout: bpy.types.UILayout) -> None:
    if not (STATE.estimate_line1 or STATE.estimate_line2):
        return
    qbox = layout.box()
    qbox.label(text="Last quote", icon="INFO")
    if STATE.estimate_line1:
        qbox.label(text=STATE.estimate_line1)
    if STATE.estimate_line2:
        qbox.label(text=STATE.estimate_line2)


def _draw_upload_render_actions(layout: bpy.types.UILayout, context: bpy.types.Context) -> None:
    phase = render_panel_phase_from_context(context)
    row = layout.row(align=True)
    row.scale_y = 1.2
    row.operator("renderbob.upload_and_estimate", text="Upload and Estimate")
    row.operator("renderbob.start_render", text="Start render")

    if phase == "pending" and STATE.upload_estimate_stage == "idle":
        layout.separator()
        layout.label(
            icon="LOCKED",
            text="Upload and Estimate is unavailable while the job is queued.",
        )


class RENDERBOB_PT_main(bpy.types.Panel):
    bl_label = "RenderBob"
    bl_idname = "RENDERBOB_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "RenderBob"
    bl_ui_units_x = 40

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

        if not STATE.auth_ok:
            layout.label(text="Cloud renders require a verified API token.")
            layout.label(text="Use Authentication below.")
            return

        layout.label(text=STATE.status_message, icon="INFO")
        layout.separator()
        _draw_job_status_box(layout, context)
        layout.separator()
        _draw_cloud_job_fields(layout, context)
        layout.separator()
        _draw_quote_summary(layout)
        layout.separator()
        _draw_upload_render_actions(layout, context)


class RENDERBOB_PT_authentication(bpy.types.Panel):
    bl_label = "Authentication"
    bl_idname = "RENDERBOB_PT_authentication"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "RenderBob"
    bl_parent_id = "RENDERBOB_PT_main"
    bl_order = 10
    bl_ui_units_x = 40

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


UI_CLASSES = (
    RENDERBOB_PT_main,
    RENDERBOB_PT_authentication,
)
