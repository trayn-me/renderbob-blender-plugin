import bpy

from .constants import ADDON_ID, DEFAULT_API_BASE_URL, DEFAULT_FRONTEND_BASE_URL
from .storage import load_settings, save_settings


class RenderBobAddonPreferences(bpy.types.AddonPreferences):
    bl_idname = ADDON_ID

    api_base_url: bpy.props.StringProperty(
        name="RenderBob API URL",
        default=DEFAULT_API_BASE_URL,
    )
    frontend_base_url: bpy.props.StringProperty(
        name="RenderBob web app URL",
        description="Origin of the RenderBob frontend (for account setup and Stripe checkout)",
        default=DEFAULT_FRONTEND_BASE_URL,
    )
    download_path: bpy.props.StringProperty(
        name="Output Download Folder",
        subtype="DIR_PATH",
        default="//",
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "api_base_url")
        layout.prop(self, "frontend_base_url")
        layout.prop(self, "download_path")
        layout.operator("renderbob.save_addon_prefs", text="Save connection settings")


def load_preferences_into_addon(addon_preferences: RenderBobAddonPreferences) -> None:
    stored = load_settings()
    addon_preferences.api_base_url = stored.get(
        "api_base_url",
        addon_preferences.api_base_url,
    )
    addon_preferences.frontend_base_url = stored.get(
        "frontend_base_url",
        getattr(
            addon_preferences,
            "frontend_base_url",
            DEFAULT_FRONTEND_BASE_URL,
        ),
    )
    addon_preferences.download_path = stored.get(
        "download_path",
        addon_preferences.download_path,
    )


def persist_preferences(addon_preferences: RenderBobAddonPreferences) -> None:
    merged = {**load_settings()}
    merged["api_base_url"] = addon_preferences.api_base_url
    merged["frontend_base_url"] = getattr(
        addon_preferences, "frontend_base_url", DEFAULT_FRONTEND_BASE_URL
    )
    merged["download_path"] = addon_preferences.download_path
    save_settings(merged)


class RENDERBOB_OT_save_addon_prefs(bpy.types.Operator):
    bl_idname = "renderbob.save_addon_prefs"
    bl_label = "Save connection settings"

    def execute(self, context):
        addon = context.preferences.addons.get(ADDON_ID)
        if not addon:
            return {"CANCELLED"}
        persist_preferences(addon.preferences)
        self.report({"INFO"}, "Connection settings saved")
        return {"FINISHED"}


PREFERENCE_OPERATOR_CLASSES = (RENDERBOB_OT_save_addon_prefs,)
