import bpy


def get_scene_summary(max_objects: int = 30) -> str:
    scene = bpy.context.scene
    parts = []

    # Scene basics
    parts.append(f"Scene: {scene.name}")
    parts.append(f"Render engine: {scene.render.engine}")
    parts.append(f"Frame: {scene.frame_current} (range {scene.frame_start}-{scene.frame_end})")
    parts.append(f"FPS: {scene.render.fps}")
    parts.append(f"Resolution: {scene.render.resolution_x}x{scene.render.resolution_y} ({scene.render.resolution_percentage}%)")

    # Render settings
    if scene.render.engine == "CYCLES":
        cycles = scene.cycles
        parts.append(f"Cycles: device={cycles.device}, samples={cycles.samples}, preview_samples={cycles.preview_samples}")
    elif scene.render.engine == "BLENDER_EEVEE_NEXT":
        eevee = scene.eevee
        parts.append(f"EEVEE: samples={eevee.taa_render_samples}")

    # World
    if scene.world:
        w = scene.world
        parts.append(f"World: {w.name} (use_nodes={w.use_nodes})")
        if w.use_nodes and w.node_tree:
            bg = next((n for n in w.node_tree.nodes if n.type == "BACKGROUND"), None)
            if bg:
                color_input = bg.inputs.get("Color")
                strength_input = bg.inputs.get("Strength")
                if color_input and not color_input.is_linked:
                    c = color_input.default_value
                    parts.append(f"  Background color: ({c[0]:.2f}, {c[1]:.2f}, {c[2]:.2f})")
                if strength_input and not strength_input.is_linked:
                    parts.append(f"  Background strength: {strength_input.default_value:.2f}")

    # Active object and selection
    active = bpy.context.active_object
    selected = bpy.context.selected_objects
    mode = bpy.context.mode
    parts.append(f"\nMode: {mode}")
    if active:
        parts.append(f"Active object: {active.name} (type={active.type})")
    if selected:
        names = [o.name for o in selected[:10]]
        parts.append(f"Selected ({len(selected)}): {', '.join(names)}")
        if len(selected) > 10:
            parts.append(f"  ...and {len(selected) - 10} more")

    # Objects
    objects = list(scene.objects)
    parts.append(f"\nObjects ({len(objects)}):")
    for obj in objects[:max_objects]:
        parts.append(_describe_object(obj))
    if len(objects) > max_objects:
        parts.append(f"  ...and {len(objects) - max_objects} more objects")

    # Materials with node details
    materials = [m for m in bpy.data.materials if m.users > 0]
    if materials:
        parts.append(f"\nMaterials ({len(materials)}):")
        for mat in materials[:15]:
            parts.append(_describe_material(mat))

    # Collections hierarchy
    parts.append("\nCollections:")
    _describe_collection(scene.collection, parts, indent=1)

    # Cameras
    cameras = [o for o in scene.objects if o.type == "CAMERA"]
    if cameras:
        parts.append("\nCameras:")
        for cam in cameras:
            cam_data = cam.data
            active_marker = " (ACTIVE)" if scene.camera == cam else ""
            parts.append(f"  - {cam.name}{active_marker}: type={cam_data.type}, focal_length={cam_data.lens:.1f}mm")

    # Lights
    lights = [o for o in scene.objects if o.type == "LIGHT"]
    if lights:
        parts.append("\nLights:")
        for light in lights:
            ld = light.data
            parts.append(f"  - {light.name}: type={ld.type}, color=({ld.color.r:.2f},{ld.color.g:.2f},{ld.color.b:.2f}), energy={ld.energy:.1f}")

    # Enabled addons
    enabled_addons = []
    for mod_name in bpy.context.preferences.addons.keys():
        # Skip our own addon and internal ones
        if mod_name.startswith("bl_") or mod_name == __package__:
            continue
        enabled_addons.append(mod_name)
    if enabled_addons:
        parts.append(f"\nEnabled addons ({len(enabled_addons)}):")
        for name in sorted(enabled_addons):
            parts.append(f"  - {name}")

    return "\n".join(parts)


def _describe_object(obj: bpy.types.Object) -> str:
    loc = obj.location
    info = f"  - {obj.name} (type={obj.type}"
    info += f", loc=({loc.x:.2f}, {loc.y:.2f}, {loc.z:.2f})"

    scale = obj.scale
    if scale.x != 1.0 or scale.y != 1.0 or scale.z != 1.0:
        info += f", scale=({scale.x:.2f}, {scale.y:.2f}, {scale.z:.2f})"

    if obj.type == "MESH" and obj.data:
        mesh = obj.data
        info += f", verts={len(mesh.vertices)}, faces={len(mesh.polygons)}"

    if obj.material_slots:
        mats = [s.material.name for s in obj.material_slots if s.material]
        if mats:
            info += f", materials=[{', '.join(mats)}]"

    if obj.modifiers:
        mod_descs = []
        for m in obj.modifiers:
            mod_descs.append(_describe_modifier(m))
        info += f", modifiers=[{', '.join(mod_descs)}]"

    if obj.parent:
        info += f", parent={obj.parent.name}"

    if not obj.visible_get():
        info += ", HIDDEN"

    info += ")"
    return info


def _describe_modifier(mod: bpy.types.Modifier) -> str:
    desc = f"{mod.name}({mod.type})"
    # Add key parameters for common modifiers
    if mod.type == "SUBSURF":
        desc = f"{mod.name}(SUBSURF levels={mod.levels} render={mod.render_levels})"
    elif mod.type == "ARRAY":
        desc = f"{mod.name}(ARRAY count={mod.count})"
    elif mod.type == "MIRROR":
        axes = [
            label for label, used in zip("XYZ", mod.use_axis) if used
        ]
        desc = f"{mod.name}(MIRROR axes={'+'.join(axes)})"
    elif mod.type == "SOLIDIFY":
        desc = f"{mod.name}(SOLIDIFY thickness={mod.thickness:.3f})"
    elif mod.type == "BEVEL":
        desc = f"{mod.name}(BEVEL width={mod.width:.3f} segments={mod.segments})"
    elif mod.type == "BOOLEAN":
        obj_name = mod.object.name if mod.object else "None"
        desc = f"{mod.name}(BOOLEAN op={mod.operation} object={obj_name})"
    elif mod.type == "NODES":
        ng = mod.node_group
        desc = f"{mod.name}(GEOMETRY_NODES group={ng.name if ng else 'None'})"
    elif mod.type == "ARMATURE":
        arm = mod.object
        desc = f"{mod.name}(ARMATURE object={arm.name if arm else 'None'})"
    elif mod.type == "SHRINKWRAP":
        target = mod.target
        desc = f"{mod.name}(SHRINKWRAP target={target.name if target else 'None'})"
    return desc


def _describe_material(mat: bpy.types.Material) -> str:
    desc = f"  - {mat.name} (use_nodes={mat.use_nodes})"
    if not mat.use_nodes:
        return desc

    nodes = mat.node_tree.nodes
    bsdf = next((n for n in nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf:
        props = []
        for input_name in ["Base Color", "Metallic", "Roughness", "Alpha", "Emission Strength",
                           "Coat Weight", "Transmission Weight", "Subsurface Weight"]:
            inp = bsdf.inputs.get(input_name)
            if inp is None:
                continue
            if inp.is_linked:
                link = inp.links[0]
                props.append(f"{input_name}=<linked:{link.from_node.type}>")
            else:
                val = inp.default_value
                if hasattr(val, "__len__"):
                    props.append(f"{input_name}=({val[0]:.2f},{val[1]:.2f},{val[2]:.2f},{val[3]:.2f})")
                elif isinstance(val, float) and val != (1.0 if input_name == "Alpha" else 0.0):
                    props.append(f"{input_name}={val:.3f}")
        if props:
            desc += "\n      " + ", ".join(props)

    # List other notable nodes
    other_nodes = [n for n in nodes if n.type not in ("BSDF_PRINCIPLED", "OUTPUT_MATERIAL")]
    if other_nodes:
        node_types = [f"{n.name}({n.type})" for n in other_nodes[:6]]
        desc += f"\n      Other nodes: {', '.join(node_types)}"

    return desc


def _describe_collection(col: bpy.types.Collection, parts: list[str], indent: int = 1) -> None:
    prefix = "  " * indent
    obj_count = len(col.objects)
    hidden = " [HIDDEN]" if col.hide_viewport else ""
    parts.append(f"{prefix}- {col.name} ({obj_count} objects){hidden}")
    for child in col.children:
        _describe_collection(child, parts, indent + 1)
