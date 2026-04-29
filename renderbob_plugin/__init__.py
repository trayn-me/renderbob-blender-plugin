bl_info = {
    "name": "RenderBob",
    "author": "RenderBob Team",
    "version": (0, 4, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > RenderBob",
    "description": "Submit and monitor RenderBob render jobs",
    "category": "Render",
}

import bpy

from .operators import CLASSES as OPERATOR_CLASSES
from .polling import renderbob_background_poll
from .quote_poll import stop_quote_poll_timer
from .preferences import PREFERENCE_OPERATOR_CLASSES, RenderBobAddonPreferences
from .properties import RenderBobSceneProperties
from .state import STATE
from .ui import UI_CLASSES


CLASSES = (
    RenderBobAddonPreferences,
    *PREFERENCE_OPERATOR_CLASSES,
    RenderBobSceneProperties,
    *OPERATOR_CLASSES,
    *UI_CLASSES,
)


def _safe_register_class(cls):
    try:
        bpy.utils.register_class(cls)
        return
    except ValueError:
        pass

    # First try unregistering the exact class object.
    try:
        bpy.utils.unregister_class(cls)
    except Exception:
        pass

    # Then try unregistering any stale class object with the same name.
    stale_cls = getattr(bpy.types, cls.__name__, None)
    if stale_cls is not None:
        try:
            bpy.utils.unregister_class(stale_cls)
        except Exception:
            pass

    bpy.utils.register_class(cls)


def register():
    for cls in CLASSES:
        _safe_register_class(cls)
    if hasattr(bpy.types.Scene, "renderbob"):
        del bpy.types.Scene.renderbob
    bpy.types.Scene.renderbob = bpy.props.PointerProperty(type=RenderBobSceneProperties)

    # Avoid accessing bpy.context.scene during register; Blender can run this in
    # a restricted context where scene is unavailable.
    STATE.bootstrapped = False
    STATE.status_message = "Ready"
    try:
        bpy.app.timers.unregister(renderbob_background_poll)
    except Exception:
        pass
    bpy.app.timers.register(renderbob_background_poll, first_interval=2.0, persistent=True)


def unregister():
    try:
        bpy.app.timers.unregister(renderbob_background_poll)
    except Exception:
        pass
    stop_quote_poll_timer()
    if hasattr(bpy.types.Scene, "renderbob"):
        del bpy.types.Scene.renderbob
    for cls in reversed(CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
