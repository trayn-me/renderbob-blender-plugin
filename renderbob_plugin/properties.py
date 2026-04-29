import bpy


class RenderBobSceneProperties(bpy.types.PropertyGroup):
    api_token: bpy.props.StringProperty(
        name="API Token",
        description="RenderBob API token (RB2-...)",
        subtype="PASSWORD",
    )
    job_name: bpy.props.StringProperty(name="Job Name", default="")
    frame_start: bpy.props.IntProperty(name="Frame Start", default=1, min=1)
    frame_end: bpy.props.IntProperty(name="Frame End", default=250, min=1)
    frame_step: bpy.props.IntProperty(name="Frame Step", default=1, min=1)
    output_format: bpy.props.EnumProperty(
        name="Output Format",
        items=[
            ("png", "PNG", "PNG sequence"),
            ("exr", "OpenEXR", "EXR sequence"),
            ("jpeg", "JPEG", "JPEG sequence"),
        ],
        default="png",
    )
    upload_s3_key: bpy.props.StringProperty(name="Uploaded S3 Key", default="")
    draft_public_id: bpy.props.StringProperty(name="Draft Job Public ID", default="")
    # Resolved automatically from /renders/servers (same rules as RenderBob web JobSetupCard).
    server_public_id: bpy.props.StringProperty(name="Server UUID", default="")
    server_meta_public_id: bpy.props.StringProperty(name="Server Meta UUID", default="")
    quote_id: bpy.props.StringProperty(name="Quote ID", default="")
    billing_transaction_id: bpy.props.StringProperty(
        name="Billing Transaction ID",
        default="",
    )
    zip_request_id: bpy.props.StringProperty(name="ZIP Request ID", default="")
    selected_output_file: bpy.props.StringProperty(name="Output File", default="")
    auto_poll: bpy.props.BoolProperty(name="Auto Poll", default=False)
    progress: bpy.props.FloatProperty(name="Progress", min=0.0, max=1.0, default=0.0)
