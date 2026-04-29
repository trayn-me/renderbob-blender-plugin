import bpy

from .client import RenderBobClient
from .constants import ADDON_ID, DEFAULT_API_BASE_URL, DEFAULT_FRONTEND_BASE_URL


def get_addon_preferences(context: bpy.types.Context):
    addon = context.preferences.addons.get(ADDON_ID)
    if not addon:
        return None
    return addon.preferences


def get_frontend_base_url(context: bpy.types.Context) -> str:
    prefs = get_addon_preferences(context)
    if prefs and getattr(prefs, "frontend_base_url", "").strip():
        return str(prefs.frontend_base_url).strip().rstrip("/")
    return DEFAULT_FRONTEND_BASE_URL.rstrip("/")


def make_client(context: bpy.types.Context, api_token: str = "") -> RenderBobClient:
    prefs = get_addon_preferences(context)
    base_url = prefs.api_base_url if prefs else DEFAULT_API_BASE_URL
    return RenderBobClient(base_url=base_url, api_token=api_token)
