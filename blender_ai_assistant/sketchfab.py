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

API_BASE = "https://api.sketchfab.com/v3"
HEADERS = {"User-Agent": "BlenderAIAssistant/1.0"}

# Persistent cache directory
CACHE_DIR = os.path.join(os.path.expanduser("~"), ".blender_ai_assistant", "sketchfab_cache")


def _get_cache_dir() -> str:
    os.makedirs(CACHE_DIR, exist_ok=True)
    return CACHE_DIR


def _get_model_cache_path(uid: str) -> str:
    return os.path.join(_get_cache_dir(), uid)


def _is_cached(uid: str) -> bool:
    cache_path = _get_model_cache_path(uid)
    if not os.path.isdir(cache_path):
        return False
    for f in os.listdir(cache_path):
        if f.endswith(".glb") or f.endswith(".gltf"):
            return True
    return False


def _get_cached_main_file(uid: str) -> str | None:
    cache_path = _get_model_cache_path(uid)
    for f in os.listdir(cache_path):
        if f.endswith(".glb"):
            return os.path.join(cache_path, f)
    for f in os.listdir(cache_path):
        if f.endswith(".gltf"):
            return os.path.join(cache_path, f)
    return None


def _api_get(path: str, token: str | None = None) -> Any:
    url = path if path.startswith("http") else f"{API_BASE}{path}"
    headers = dict(HEADERS)
    if token:
        headers["Authorization"] = f"Token {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def search_models(query: str, token: str | None = None, max_results: int = 10,
                  license_filter: str = "", sort_by: str = "-likeCount") -> list[dict[str, Any]]:
    """Search Sketchfab for downloadable models.

    Args:
        query: Search keywords.
        token: Optional API token (search works without it).
        max_results: Max results to return.
        license_filter: "cc0", "by", "by-sa", "by-nc", or "" for all.
        sort_by: "-likeCount", "-viewCount", "-publishedAt".

    Returns list of dicts with: uid, name, license, author, face_count, vertex_count.
    """
    params = f"?type=models&q={urllib.request.quote(query)}&downloadable=true&count={max_results}&sort_by={sort_by}"
    if license_filter:
        params += f"&license={license_filter}"

    data = _api_get(f"/search{params}", token)

    query_words = query.lower().split()
    results = []
    for item in data.get("results", [])[:max_results]:
        name = item.get("name", "").lower()
        tags = " ".join(t.get("name", "") if isinstance(t, dict) else str(t)
                        for t in item.get("tags", [])).lower()
        searchable = name + " " + tags
        if not all(re.search(r'\b' + re.escape(w) + r'\b', searchable) for w in query_words):
            continue
        results.append({
            "uid": item["uid"],
            "name": item.get("name", ""),
            "license": item.get("license", {}).get("label", "Unknown"),
            "author": item.get("user", {}).get("displayName", "Unknown"),
            "face_count": item.get("faceCount", 0),
            "vertex_count": item.get("vertexCount", 0),
            "likes": item.get("likeCount", 0),
        })
    return results


def get_download_url(uid: str, token: str, fmt: str = "glb") -> str | None:
    """Get a temporary signed download URL for a model. Requires auth token.

    Returns the direct download URL or None.
    """
    try:
        data = _api_get(f"/models/{uid}/download", token)
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise RuntimeError("Sketchfab API token is invalid or missing. Set it in addon preferences.") from e
        raise

    entry = data.get(fmt) or data.get("glb") or data.get("gltf")
    if entry and "url" in entry:
        return entry["url"]
    return None


def _download_file(url: str, dest_dir: str, filename: str | None = None) -> str:
    if filename is None:
        filename = url.split("/")[-1].split("?")[0]
        if not filename:
            filename = "model.glb"
    filepath = os.path.join(dest_dir, filename)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=120) as resp:
        with open(filepath, "wb") as f:
            f.write(resp.read())
    return filepath


def _find_existing_in_scene(uid: str) -> bpy.types.Object | None:
    for obj in bpy.data.objects:
        if obj.type == "EMPTY" and uid in obj.name:
            if obj.children:
                return obj
    return None


def _duplicate_from_scene(existing_empty: bpy.types.Object) -> str:
    new_empty = existing_empty.copy()
    bpy.context.collection.objects.link(new_empty)
    for child in existing_empty.children:
        new_child = child.copy()
        if child.data:
            new_child.data = child.data.copy()
        bpy.context.collection.objects.link(new_child)
        new_child.parent = new_empty
    return new_empty.name


def download_and_import(uid: str, token: str, name: str = "", target_height: float = 0.0) -> tuple[bool, str | None, str]:
    """Download a model from Sketchfab and import it into the current scene.

    - If already in scene, duplicates it.
    - If cached on disk, imports from cache.
    - Otherwise downloads to persistent cache, then imports.
    - If target_height > 0, scales the model so its bounding box height matches.

    Args:
        uid: Sketchfab model UID.
        token: Sketchfab API token (required for download).
        name: Display name for the empty parent. Defaults to uid.
        target_height: Desired real-world height in meters. 0 = no scaling.

    Returns (success, empty_name, message).
    """
    display_name = name or uid
    existing_objects = set(bpy.data.objects.keys())

    # 1. Check if already in scene
    existing = _find_existing_in_scene(uid)
    if existing:
        new_name = _duplicate_from_scene(existing)
        if target_height > 0:
            _scale_to_height(new_name, target_height)
        return True, new_name, f"Duplicated '{display_name}' from scene (parent: {new_name})"

    # 2. Check local cache
    if _is_cached(uid):
        filepath = _get_cached_main_file(uid)
        if filepath:
            try:
                imported = _import_glb(filepath, existing_objects)
                if imported:
                    empty_name = _parent_under_empty(display_name, uid, imported, existing_objects)
                    if target_height > 0:
                        _scale_to_height(empty_name, target_height)
                    return True, empty_name, f"Imported '{display_name}' from cache ({len(imported)} objects)"
            except Exception:
                pass

    # 3. Download
    if not token:
        return False, None, "Sketchfab API token not set. Add it in addon preferences (Settings)."

    try:
        url = get_download_url(uid, token, fmt="glb")
        if url is None:
            return False, None, f"No downloadable file found for '{display_name}'"

        cache_dir = _get_model_cache_path(uid)
        if os.path.exists(cache_dir):
            shutil.rmtree(cache_dir, ignore_errors=True)
        os.makedirs(cache_dir, exist_ok=True)

        filepath = _download_file(url, cache_dir, filename=f"{uid}.glb")

        imported = _import_glb(filepath, existing_objects)
        if not imported:
            return False, None, "Import completed but no new objects found"

        empty_name = _parent_under_empty(display_name, uid, imported, existing_objects)
        if target_height > 0:
            _scale_to_height(empty_name, target_height)
        return True, empty_name, f"Imported '{display_name}' from Sketchfab ({len(imported)} objects, parent: {empty_name})"

    except Exception as e:
        return False, None, f"Download/import failed: {e}"


def _import_glb(filepath: str, existing_objects: set[str]) -> list[bpy.types.Object]:
    bpy.ops.import_scene.gltf(filepath=filepath)
    return [o for o in bpy.data.objects if o.name not in existing_objects]


def _parent_under_empty(name: str, uid: str, imported: list[bpy.types.Object], existing_objects: set[str]) -> str:
    empty = bpy.data.objects.new(f"{name} [{uid[:8]}]", None)
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

    # Force dependency graph update so bounding boxes are correct
    bpy.context.view_layer.update()

    # Calculate combined bounding box of all children
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


def clear_cache() -> tuple[int, float]:
    """Delete all cached Sketchfab downloads. Returns (count, size_mb)."""
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
