import bpy

from ..client import RenderBobClient
from ..context import get_frontend_base_url, make_client
from ..logging_utils import log_error, log_info
from ..state import STATE
from ..storage import load_settings, save_settings
from ..workflows import fetch_credits, refresh_render_server_selection


class RENDERBOB_OT_verify_api_token(bpy.types.Operator):
    bl_idname = "renderbob.verify_api_token"
    bl_label = "Verify Token"

    def execute(self, context):
        token = RenderBobClient.normalize_api_token(context.scene.renderbob.api_token)
        if not token:
            self.report({"ERROR"}, "API token is required")
            return {"CANCELLED"}

        context.scene.renderbob.api_token = token
        if not token.startswith("RB2-"):
            self.report(
                {"WARNING"},
                "Token does not look like RenderBob API token (RB2-...); attempting bearer auth",
            )

        client = make_client(context, token)
        response = client.get("/api/v1/users/me")
        if not response.ok:
            message = response.error or "Failed to verify token"
            STATE.auth_ok = False
            STATE.status_message = message
            STATE.last_error = message
            log_error(message)
            self.report({"ERROR"}, message)
            return {"CANCELLED"}

        user_data = response.data.get("data", {})
        STATE.auth_ok = True
        STATE.user_email = user_data.get("email")
        STATE.status_message = f"Authenticated as {STATE.user_email or 'user'}"
        STATE.last_error = None
        save_settings({**load_settings(), "api_token": token})
        log_info("API token verification succeeded")
        credits_response = fetch_credits(context, token)
        if credits_response.ok:
            credits_eur = credits_response.data.get("creditsAvailableEur")
            STATE.credits_eur = str(credits_eur) if credits_eur is not None else None
        refresh_render_server_selection(context, token)
        self.report({"INFO"}, STATE.status_message)
        return {"FINISHED"}


class RENDERBOB_OT_setup_account(bpy.types.Operator):
    bl_idname = "renderbob.setup_account"
    bl_label = "Setup RenderBob account"

    def execute(self, context):
        base = get_frontend_base_url(context)
        if not base:
            self.report({"ERROR"}, "Set RenderBob web app URL in addon preferences")
            return {"CANCELLED"}
        url = f"{base}/user-management"
        bpy.ops.wm.url_open(url=url)
        STATE.setup_launched = True
        STATE.status_message = (
            "Browser opened: create or regenerate an API key, copy it, "
            "return here → Authentication → paste token → Verify."
        )
        self.report({"INFO"}, STATE.status_message)
        return {"FINISHED"}


class RENDERBOB_OT_logout(bpy.types.Operator):
    bl_idname = "renderbob.logout"
    bl_label = "Logout"

    def execute(self, context):
        scene_props = context.scene.renderbob
        scene_props.api_token = ""
        STATE.auth_ok = False
        STATE.user_email = None
        STATE.setup_launched = False
        STATE.awaiting_stripe_checkout = False
        STATE.status_message = "Logged out"
        save_settings({**load_settings(), "api_token": ""})
        log_info("User logged out from RenderBob plugin")
        self.report({"INFO"}, "Logged out")
        return {"FINISHED"}
