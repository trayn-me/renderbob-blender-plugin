import bpy

from ..state import STATE


class RENDERBOB_OT_set_frame_range_from_scene(bpy.types.Operator):
    bl_idname = "renderbob.use_scene_range"
    bl_label = "Use Scene Frame Range"

    def execute(self, context):
        scene = context.scene
        props = scene.renderbob
        props.frame_start = int(scene.frame_start)
        props.frame_end = int(scene.frame_end)
        STATE.status_message = "Frame range copied from scene"
        return {"FINISHED"}
