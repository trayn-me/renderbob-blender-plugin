import bpy

from .client import RenderBobClient
from .constants import ADDON_ID, DEFAULT_API_BASE_URL, DEFAULT_FRONTEND_BASE_URL


def get_addon_preferences(context: bpy.types.Context):
    """Resolve add-on preferences for legacy installs and Blender extensions.

    Extensions register under a namespaced module key (e.g. ``bl_ext.user_default.renderbob``),
    not plain ``renderbob``, so ``addons.get("renderbob")`` alone raises KeyError elsewhere.
    """
    addons = context.preferences.addons
    addon = addons.get(ADDON_ID)
    if addon is not None:
        return addon.preferences
    for key in addons.keys():
        if key == ADDON_ID or key.endswith(f".{ADDON_ID}"):
            return addons[key].preferences
    return None


def get_frontend_base_url(context: bpy.types.Context) -> str:
    prefs = get_addon_preferences(context)
    if prefs and getattr(prefs, "frontend_base_url", "").strip():
        return str(prefs.frontend_base_url).strip().rstrip("/")
    return DEFAULT_FRONTEND_BASE_URL.rstrip("/")


def make_client(context: bpy.types.Context, api_token: str = "") -> RenderBobClient:
    prefs = get_addon_preferences(context)
    base_url = prefs.api_base_url if prefs else DEFAULT_API_BASE_URL
    return RenderBobClient(base_url=base_url, api_token=api_token)
