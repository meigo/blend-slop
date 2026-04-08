from __future__ import annotations

import bpy
import json
import mathutils
import os
import shutil
import urllib.request
import urllib.error
import re
from typing import Any

API_BASE = "https://api.polyhaven.com"
HEADERS = {"User-Agent": "BlenderAIAssistant/1.0"}

# Persistent cache directory for downloaded assets
CACHE_DIR = os.path.join(os.path.expanduser("~"), ".blender_ai_assistant", "polyhaven_cache")

# In-memory caches for asset catalogs
_asset_cache = None
_texture_cache = None
_hdri_cache = None


def _get_cache_dir() -> str:
    os.makedirs(CACHE_DIR, exist_ok=True)
    return CACHE_DIR


def _get_model_cache_path(slug: str, resolution: str) -> str:
    """Return the cache directory for a specific model+resolution."""
    return os.path.join(_get_cache_dir(), f"{slug}_{resolution}")


def _is_cached(slug: str, resolution: str) -> bool:
    """Check if a model is already downloaded to the local cache."""
    cache_path = _get_model_cache_path(slug, resolution)
    if not os.path.isdir(cache_path):
        return False
    # Check that at least one .blend or .gltf exists
    for f in os.listdir(cache_path):
        if f.endswith(".blend") or f.endswith(".gltf"):
            return True
    return False


def _get_cached_main_file(slug: str, resolution: str) -> str | None:
    """Return the path to the cached main file (.blend or .gltf)."""
    cache_path = _get_model_cache_path(slug, resolution)
    for f in os.listdir(cache_path):
        if f.endswith(".blend"):
            return os.path.join(cache_path, f)
    for f in os.listdir(cache_path):
        if f.endswith(".gltf"):
            return os.path.join(cache_path, f)
    return None


def _api_get(path: str) -> Any:
    url = f"{API_BASE}{path}"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_all_models() -> dict[str, Any]:
    """Fetch and cache the full model catalog from Polyhaven."""
    global _asset_cache
    if _asset_cache is not None:
        return _asset_cache
    _asset_cache = _api_get("/assets?type=models")
    return _asset_cache


def search_models(query: str, max_results: int = 10) -> list[dict[str, Any]]:
    """Search models by matching query against name, tags, and categories."""
    assets = get_all_models()
    query_lower = query.lower()
    query_words = query_lower.split()

    scored = []
    for slug, info in assets.items():
        name = info.get("name", "").lower()
        tags = [t.lower() for t in info.get("tags", [])]
        categories = [c.lower() for c in info.get("categories", [])]
        all_text = name + " " + " ".join(tags) + " " + " ".join(categories)

        score = sum(1 for w in query_words if re.search(r'\b' + re.escape(w) + r'\b', all_text))
        if score > 0:
            scored.append((score, info.get("download_count", 0), slug, info))

    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)

    results = []
    for score, _, slug, info in scored[:max_results]:
        results.append({
            "slug": slug,
            "name": info.get("name", slug),
            "categories": info.get("categories", []),
            "tags": info.get("tags", []),
            "polycount": info.get("polycount", 0),
        })
    return results


def _find_best_entry(files: dict[str, Any], fmt: str, resolution: str) -> dict[str, Any] | None:
    """Find the best available entry for a format, trying fallback resolutions."""
    if fmt not in files:
        return None
    for res in [resolution, "2k", "1k", "4k"]:
        if res in files[fmt]:
            entry = files[fmt][res].get(fmt)
            if entry and "url" in entry:
                return entry
    return None


def get_download_url(slug: str, fmt: str = "blend", resolution: str = "2k") -> tuple[str | None, list[tuple[str, str]]]:
    """Get the direct download URL and included texture URLs for a model."""
    files = _api_get(f"/files/{slug}")

    entry = _find_best_entry(files, fmt, resolution)

    if entry is None and fmt != "gltf":
        entry = _find_best_entry(files, "gltf", resolution)

    if entry is None:
        return None, []

    includes = []
    for tex_path, tex_info in entry.get("include", {}).items():
        includes.append((tex_path, tex_info["url"]))

    return entry["url"], includes


def download_file(url: str, dest_dir: str, filename: str | None = None) -> str:
    """Download a file to a specific directory, return the local path."""
    if filename is None:
        filename = url.split("/")[-1]
    filepath = os.path.join(dest_dir, filename)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=120) as resp:
        with open(filepath, "wb") as f:
            f.write(resp.read())
    return filepath


def _find_file(directory: str, filename: str) -> str | None:
    """Search for a file by name in a directory tree."""
    for root, _dirs, files in os.walk(directory):
        if filename in files:
            return os.path.join(root, filename)
    return None


def _find_existing_in_scene(slug: str) -> bpy.types.Object | None:
    """Check if this Polyhaven model is already in the scene. Returns the empty parent or None."""
    for obj in bpy.data.objects:
        if obj.type == "EMPTY" and obj.name.startswith(slug):
            # Verify it has children (is actually a polyhaven import parent)
            if obj.children:
                return obj
    return None


def _duplicate_from_scene(existing_empty: bpy.types.Object) -> str:
    """Duplicate an existing Polyhaven model (empty + all children). Returns (empty_name, message)."""
    # Duplicate the empty
    new_empty = existing_empty.copy()
    bpy.context.collection.objects.link(new_empty)

    # Duplicate all children (deep copy mesh data)
    for child in existing_empty.children:
        new_child = child.copy()
        if child.data:
            new_child.data = child.data.copy()
        bpy.context.collection.objects.link(new_child)
        new_child.parent = new_empty

    return new_empty.name


def _import_from_file(filepath: str, cache_dir: str) -> list[bpy.types.Object]:
    """Import a .blend or .gltf file. Returns list of imported objects."""
    is_blend = filepath.endswith(".blend")
    is_gltf = filepath.endswith(".gltf")

    existing_images = set(bpy.data.images.keys())
    existing_objects = set(bpy.data.objects.keys())

    if is_blend:
        with bpy.data.libraries.load(filepath, link=False) as (data_from, data_to):
            data_to.objects = data_from.objects
            data_to.materials = data_from.materials
            data_to.images = data_from.images
            data_to.node_groups = data_from.node_groups

        imported = []
        for obj in data_to.objects:
            if obj is not None:
                bpy.context.collection.objects.link(obj)
                imported.append(obj)

        # Fix image paths and pack textures
        for img in bpy.data.images:
            if img.name not in existing_images and img.filepath:
                img_filename = os.path.basename(bpy.path.abspath(img.filepath))
                found = _find_file(cache_dir, img_filename)
                if found:
                    img.filepath = found
                    img.reload()
                try:
                    img.pack()
                except Exception:
                    pass

        return imported

    elif is_gltf:
        bpy.ops.import_scene.gltf(filepath=filepath)
        return [o for o in bpy.data.objects if o.name not in existing_objects]

    return []


def _parent_under_empty(slug: str, imported: list[bpy.types.Object], existing_objects: set[str]) -> str:
    """Create an empty and parent all imported objects under it. Returns empty name."""
    empty = bpy.data.objects.new(slug, None)
    empty.empty_display_type = "PLAIN_AXES"
    empty.empty_display_size = 0.25
    bpy.context.collection.objects.link(empty)

    for obj in imported:
        if obj.parent is None or obj.parent.name in existing_objects:
            obj.parent = empty

    return empty.name


def _scale_to_height(empty_name: str, target_height: float) -> None:
    """Scale the empty (and all children) so the model's bounding box height matches target_height."""
    empty = bpy.data.objects.get(empty_name)
    if not empty or not empty.children:
        return

    bpy.context.view_layer.update()

    min_z = float("inf")
    max_z = float("-inf")
    for child in empty.children:
        if hasattr(child, "bound_box"):
            for corner in child.bound_box:
                world_z = (child.matrix_world @ mathutils.Vector(corner)).z
                min_z = min(min_z, world_z)
                max_z = max(max_z, world_z)

    current_height = max_z - min_z
    if current_height <= 0.001:
        return

    scale_factor = target_height / current_height
    empty.scale = (scale_factor, scale_factor, scale_factor)


def download_and_import(slug: str, resolution: str = "2k", target_height: float = 0.0) -> tuple[bool, str | None, str]:
    """Download a model from Polyhaven and import it into the current scene.

    - If the model is already in the scene, duplicates it (no download).
    - If cached on disk, imports from cache (no download).
    - Otherwise downloads to persistent cache, then imports.
    - If target_height > 0, scales the model so its bounding box height matches.

    All parts are parented under a single empty.
    Returns (success, empty_name, message).
    """
    existing_objects = set(bpy.data.objects.keys())

    # 1. Check if already in scene -> duplicate
    existing = _find_existing_in_scene(slug)
    if existing:
        new_name = _duplicate_from_scene(existing)
        if target_height > 0:
            _scale_to_height(new_name, target_height)
        return True, new_name, f"Duplicated '{slug}' from scene (parent: {new_name})"

    # 2. Check local cache
    if _is_cached(slug, resolution):
        cache_dir = _get_model_cache_path(slug, resolution)
        filepath = _get_cached_main_file(slug, resolution)
        if filepath:
            try:
                imported = _import_from_file(filepath, cache_dir)
                if imported:
                    empty_name = _parent_under_empty(slug, imported, existing_objects)
                    if target_height > 0:
                        _scale_to_height(empty_name, target_height)
                    return True, empty_name, f"Imported '{slug}' from cache ({len(imported)} objects, parent: {empty_name})"
            except Exception:
                # Cache might be corrupted, fall through to re-download
                pass

    # 3. Download to cache
    url, includes = get_download_url(slug, fmt="blend", resolution=resolution)
    if url is None:
        return False, None, f"No downloadable file found for '{slug}'"

    try:
        cache_dir = _get_model_cache_path(slug, resolution)
        # Clear any partial cache
        if os.path.exists(cache_dir):
            shutil.rmtree(cache_dir, ignore_errors=True)
        os.makedirs(cache_dir, exist_ok=True)

        filepath = download_file(url, cache_dir)

        for tex_path, tex_url in includes:
            download_file(tex_url, cache_dir, filename=tex_path)

        imported = _import_from_file(filepath, cache_dir)

        if not imported:
            return False, None, "Import completed but no new objects found"

        empty_name = _parent_under_empty(slug, imported, existing_objects)
        if target_height > 0:
            _scale_to_height(empty_name, target_height)
        return True, empty_name, f"Imported '{slug}' from Polyhaven ({len(imported)} objects, parent: {empty_name})"

    except Exception as e:
        return False, None, f"Download/import failed: {e}"


def clear_cache() -> tuple[int, float]:
    """Delete all cached Polyhaven downloads. Returns (count, size_mb)."""
    cache_dir = _get_cache_dir()
    count = 0
    total_size = 0
    if os.path.isdir(cache_dir):
        for entry in os.listdir(cache_dir):
            entry_path = os.path.join(cache_dir, entry)
            if os.path.isdir(entry_path):
                for root, _dirs, files in os.walk(entry_path):
                    for f in files:
                        total_size += os.path.getsize(os.path.join(root, f))
                count += 1
                shutil.rmtree(entry_path, ignore_errors=True)
    return count, total_size / (1024 * 1024)


# ---------------------------------------------------------------------------
# Polyhaven PBR textures
# ---------------------------------------------------------------------------

# Map type -> (BSDF input name, colorspace, special node needed)
_TEXTURE_MAP_CONFIG: dict[str, dict[str, Any]] = {
    "Diffuse":      {"input": "Base Color", "colorspace": "sRGB"},
    "nor_gl":       {"input": "Normal", "colorspace": "Non-Color", "normal_map": True},
    "Rough":        {"input": "Roughness", "colorspace": "Non-Color"},
    "Displacement":  {"colorspace": "Non-Color", "displacement": True},
    "AO":           {"colorspace": "Non-Color", "ao_mix": True},
}

_TEXTURE_MAP_TYPES = list(_TEXTURE_MAP_CONFIG.keys())


def _get_texture_cache_path(slug: str, resolution: str) -> str:
    return os.path.join(_get_cache_dir(), f"tex_{slug}_{resolution}")


def _is_texture_cached(slug: str, resolution: str) -> bool:
    cache_path = _get_texture_cache_path(slug, resolution)
    if not os.path.isdir(cache_path):
        return False
    return any(f.endswith((".jpg", ".png", ".exr")) for f in os.listdir(cache_path))


def _get_cached_texture_maps(slug: str, resolution: str) -> dict[str, str]:
    """Return {map_type: filepath} for all cached texture maps."""
    cache_path = _get_texture_cache_path(slug, resolution)
    result: dict[str, str] = {}
    if not os.path.isdir(cache_path):
        return result
    for f in os.listdir(cache_path):
        for map_type in _TEXTURE_MAP_TYPES:
            if f.startswith(map_type + ".") or f.startswith(map_type + "_"):
                result[map_type] = os.path.join(cache_path, f)
                break
    return result


def get_all_textures() -> dict[str, Any]:
    """Fetch and cache the full texture catalog from Polyhaven."""
    global _texture_cache
    if _texture_cache is not None:
        return _texture_cache
    _texture_cache = _api_get("/assets?type=textures")
    return _texture_cache


def search_textures(query: str, max_results: int = 10) -> list[dict[str, Any]]:
    """Search textures by matching query against name, tags, and categories."""
    assets = get_all_textures()
    query_lower = query.lower()
    query_words = query_lower.split()

    scored = []
    for slug, info in assets.items():
        name = info.get("name", "").lower()
        tags = [t.lower() for t in info.get("tags", [])]
        categories = [c.lower() for c in info.get("categories", [])]
        all_text = name + " " + " ".join(tags) + " " + " ".join(categories)

        score = sum(1 for w in query_words if re.search(r'\b' + re.escape(w) + r'\b', all_text))
        if score > 0:
            scored.append((score, info.get("download_count", 0), slug, info))

    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)

    results = []
    for score, _, slug, info in scored[:max_results]:
        results.append({
            "slug": slug,
            "name": info.get("name", slug),
            "categories": info.get("categories", []),
            "tags": info.get("tags", []),
        })
    return results


def get_texture_download_urls(slug: str, resolution: str = "2k") -> dict[str, str]:
    """Get download URLs for each PBR map type. Returns {map_type: url}."""
    files = _api_get(f"/files/{slug}")
    urls: dict[str, str] = {}

    for map_type in _TEXTURE_MAP_TYPES:
        if map_type not in files:
            continue
        # Try requested resolution, then fallbacks
        for res in [resolution, "2k", "1k", "4k"]:
            res_data = files[map_type].get(res)
            if not res_data:
                continue
            # Prefer png for normal maps, jpg for others
            preferred = "png" if map_type == "nor_gl" else "jpg"
            fallback = "jpg" if preferred == "png" else "png"
            entry = res_data.get(preferred) or res_data.get(fallback) or res_data.get("exr")
            if entry and "url" in entry:
                urls[map_type] = entry["url"]
                break

    return urls


def _create_pbr_material(slug: str, map_paths: dict[str, str]) -> bpy.types.Material:
    """Create a Principled BSDF material with PBR texture maps connected."""
    mat = bpy.data.materials.new(slug)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links

    # Get existing nodes
    bsdf = next((n for n in nodes if n.type == 'BSDF_PRINCIPLED'), None)
    output = next((n for n in nodes if n.type == 'OUTPUT_MATERIAL'), None)

    if bsdf:
        bsdf.location = (0, 0)
    if output:
        output.location = (300, 0)

    # Texture Coordinate -> Mapping
    tex_coord = nodes.new('ShaderNodeTexCoord')
    tex_coord.location = (-800, 0)
    mapping = nodes.new('ShaderNodeMapping')
    mapping.location = (-600, 0)
    links.new(tex_coord.outputs["UV"], mapping.inputs["Vector"])

    y_offset = 300
    diffuse_color_output = None

    for i, (map_type, filepath) in enumerate(map_paths.items()):
        config = _TEXTURE_MAP_CONFIG.get(map_type)
        if not config:
            continue

        # Create image texture node
        tex_node = nodes.new('ShaderNodeTexImage')
        tex_node.location = (-400, y_offset - i * 300)
        tex_node.image = bpy.data.images.load(filepath)
        tex_node.label = map_type

        # Set colorspace
        cs = config.get("colorspace", "sRGB")
        try:
            tex_node.image.colorspace_settings.name = cs
        except Exception:
            if cs == "Non-Color":
                try:
                    tex_node.image.colorspace_settings.name = "Raw"
                except Exception:
                    pass

        # Connect mapping -> texture
        links.new(mapping.outputs["Vector"], tex_node.inputs["Vector"])

        if map_type == "Diffuse":
            diffuse_color_output = tex_node.outputs["Color"]

        # Connect to BSDF based on map type
        if not bsdf:
            continue

        if config.get("normal_map"):
            normal_node = nodes.new('ShaderNodeNormalMap')
            normal_node.location = (-200, tex_node.location.y)
            links.new(tex_node.outputs["Color"], normal_node.inputs["Color"])
            links.new(normal_node.outputs["Normal"], bsdf.inputs["Normal"])

        elif config.get("displacement"):
            disp_node = nodes.new('ShaderNodeDisplacement')
            disp_node.location = (-200, tex_node.location.y)
            disp_node.inputs["Scale"].default_value = 0.1
            disp_node.inputs["Midlevel"].default_value = 0.5
            links.new(tex_node.outputs["Color"], disp_node.inputs["Height"])
            if output:
                links.new(disp_node.outputs["Displacement"], output.inputs["Displacement"])
            mat.displacement_method = 'BOTH'

        elif config.get("ao_mix") and diffuse_color_output is not None:
            mix_node = nodes.new('ShaderNodeMix')
            mix_node.data_type = 'RGBA'
            mix_node.blend_type = 'MULTIPLY'
            mix_node.location = (-200, tex_node.location.y)
            mix_node.inputs["Factor"].default_value = 1.0
            links.new(diffuse_color_output, mix_node.inputs[6])
            links.new(tex_node.outputs["Color"], mix_node.inputs[7])
            links.new(mix_node.outputs[2], bsdf.inputs["Base Color"])

        elif "input" in config:
            bsdf_input = bsdf.inputs.get(config["input"])
            if bsdf_input:
                links.new(tex_node.outputs["Color"], bsdf_input)

    # If we have diffuse but no AO, connect diffuse directly
    if diffuse_color_output is not None and "AO" not in map_paths and bsdf:
        links.new(diffuse_color_output, bsdf.inputs["Base Color"])

    return mat


def download_and_apply_texture(slug: str, resolution: str = "2k",
                               object_name: str = "") -> tuple[bool, str | None, str]:
    """Download PBR textures from Polyhaven and apply as a material.

    Args:
        slug: Polyhaven texture slug.
        resolution: "1k", "2k", or "4k".
        object_name: Target object name. Empty = active object.

    Returns (success, material_name, message).
    """
    # Resolve target object
    if object_name:
        obj = bpy.data.objects.get(object_name)
        if not obj:
            return False, None, f"Object '{object_name}' not found"
    else:
        obj = bpy.context.active_object
        if not obj:
            return False, None, "No active object selected"

    if not hasattr(obj.data, "materials"):
        return False, None, f"Object '{obj.name}' does not support materials"

    # Check cache first
    map_paths = _get_cached_texture_maps(slug, resolution)

    if not map_paths:
        # Download texture maps
        try:
            urls = get_texture_download_urls(slug, resolution)
            if not urls:
                return False, None, f"No texture maps found for '{slug}'"

            cache_dir = _get_texture_cache_path(slug, resolution)
            if os.path.exists(cache_dir):
                shutil.rmtree(cache_dir, ignore_errors=True)
            os.makedirs(cache_dir, exist_ok=True)

            for map_type, url in urls.items():
                ext = url.split(".")[-1].split("?")[0]
                filename = f"{map_type}.{ext}"
                filepath = download_file(url, cache_dir, filename=filename)
                map_paths[map_type] = filepath

        except Exception as e:
            return False, None, f"Download failed: {e}"

    if not map_paths:
        return False, None, f"No texture maps available for '{slug}'"

    # Create material and apply
    mat = _create_pbr_material(slug, map_paths)
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)

    map_names = ", ".join(map_paths.keys())
    return True, mat.name, f"Applied '{slug}' to '{obj.name}' ({map_names})"


# ---------------------------------------------------------------------------
# Polyhaven HDRIs (environment lighting)
# ---------------------------------------------------------------------------


def _get_hdri_cache_path(slug: str, resolution: str) -> str:
    return os.path.join(_get_cache_dir(), f"hdri_{slug}_{resolution}")


def _get_cached_hdri(slug: str, resolution: str) -> str | None:
    """Return the cached HDRI file path, or None if not cached."""
    cache_path = _get_hdri_cache_path(slug, resolution)
    if not os.path.isdir(cache_path):
        return None
    for f in os.listdir(cache_path):
        if f.endswith((".hdr", ".exr")):
            return os.path.join(cache_path, f)
    return None


def get_all_hdris() -> dict[str, Any]:
    """Fetch and cache the full HDRI catalog from Polyhaven."""
    global _hdri_cache
    if _hdri_cache is not None:
        return _hdri_cache
    _hdri_cache = _api_get("/assets?type=hdris")
    return _hdri_cache


def search_hdris(query: str, max_results: int = 10) -> list[dict[str, Any]]:
    """Search HDRIs by matching query against name, tags, and categories."""
    assets = get_all_hdris()
    query_lower = query.lower()
    query_words = query_lower.split()

    scored = []
    for slug, info in assets.items():
        name = info.get("name", "").lower()
        tags = [t.lower() for t in info.get("tags", [])]
        categories = [c.lower() for c in info.get("categories", [])]
        all_text = name + " " + " ".join(tags) + " " + " ".join(categories)

        score = sum(1 for w in query_words if re.search(r'\b' + re.escape(w) + r'\b', all_text))
        if score > 0:
            scored.append((score, info.get("download_count", 0), slug, info))

    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)

    results = []
    for score, _, slug, info in scored[:max_results]:
        results.append({
            "slug": slug,
            "name": info.get("name", slug),
            "categories": info.get("categories", []),
            "tags": info.get("tags", []),
        })
    return results


def get_hdri_download_url(slug: str, resolution: str = "2k") -> str | None:
    """Get the direct download URL for an HDRI. Prefers .hdr format."""
    files = _api_get(f"/files/{slug}")
    hdri_files = files.get("hdri")
    if not hdri_files:
        return None

    for res in [resolution, "2k", "1k", "4k"]:
        res_data = hdri_files.get(res)
        if not res_data:
            continue
        # Prefer .hdr (smaller than .exr, works great in Blender)
        entry = res_data.get("hdr") or res_data.get("exr")
        if entry and "url" in entry:
            return entry["url"]

    return None


def download_and_apply_hdri(slug: str, resolution: str = "2k",
                            strength: float = 1.0) -> tuple[bool, str]:
    """Download an HDRI from Polyhaven and set it as the world environment.

    Args:
        slug: Polyhaven HDRI slug.
        resolution: "1k", "2k", or "4k".
        strength: Background light strength (default 1.0).

    Returns (success, message).
    """
    # Check cache first
    cached = _get_cached_hdri(slug, resolution)

    if not cached:
        url = get_hdri_download_url(slug, resolution)
        if not url:
            return False, f"No HDRI file found for '{slug}'"

        try:
            cache_dir = _get_hdri_cache_path(slug, resolution)
            if os.path.exists(cache_dir):
                shutil.rmtree(cache_dir, ignore_errors=True)
            os.makedirs(cache_dir, exist_ok=True)

            cached = download_file(url, cache_dir)
        except Exception as e:
            return False, f"Download failed: {e}"

    # Set up world environment nodes
    world = bpy.data.worlds.get("World")
    if not world:
        world = bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.use_nodes = True

    nodes = world.node_tree.nodes
    links = world.node_tree.links
    nodes.clear()

    tex_coord = nodes.new('ShaderNodeTexCoord')
    tex_coord.location = (-800, 0)

    mapping = nodes.new('ShaderNodeMapping')
    mapping.location = (-600, 0)

    env_tex = nodes.new('ShaderNodeTexEnvironment')
    env_tex.location = (-300, 0)
    env_tex.image = bpy.data.images.load(cached)

    bg = nodes.new('ShaderNodeBackground')
    bg.location = (0, 0)
    bg.inputs["Strength"].default_value = strength

    output = nodes.new('ShaderNodeOutputWorld')
    output.location = (200, 0)

    links.new(tex_coord.outputs["Generated"], mapping.inputs["Vector"])
    links.new(mapping.outputs["Vector"], env_tex.inputs["Vector"])
    links.new(env_tex.outputs["Color"], bg.inputs["Color"])
    links.new(bg.outputs["Background"], output.inputs["Surface"])

    return True, f"Applied HDRI '{slug}' as world environment (strength={strength})"
