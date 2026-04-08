import bpy
import bmesh
import mathutils
import math
import io
import traceback
from contextlib import redirect_stdout, redirect_stderr

from . import polyhaven
from . import sketchfab
from . import dimensions


SAFE_NAMESPACE = {
    "bpy": bpy,
    "bmesh": bmesh,
    "mathutils": mathutils,
    "math": math,
    "Vector": mathutils.Vector,
    "Matrix": mathutils.Matrix,
    "Euler": mathutils.Euler,
    "Quaternion": mathutils.Quaternion,
    "Color": mathutils.Color,
    "polyhaven": polyhaven,
    "sketchfab": sketchfab,
    "dimensions": dimensions,
}


def execute_code(code: str) -> tuple[bool, str, str]:
    """Execute generated Python code in Blender context.

    Returns (success: bool, output: str, error: str).
    """
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()

    namespace = dict(SAFE_NAMESPACE)
    namespace["__builtins__"] = __builtins__

    # Inject Sketchfab token so generated code doesn't need to import preferences
    from .preferences import get_addon_preferences
    try:
        namespace["SKETCHFAB_TOKEN"] = get_addon_preferences().sketchfab_api_key
    except Exception:
        namespace["SKETCHFAB_TOKEN"] = ""

    try:
        with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
            exec(code, namespace)
        stdout = stdout_buf.getvalue()
        stderr = stderr_buf.getvalue()
        return True, stdout, stderr
    except Exception:
        tb = traceback.format_exc()
        return False, stdout_buf.getvalue(), tb


def extract_code_blocks(text: str) -> list[str]:
    """Extract Python code blocks from markdown-formatted LLM response."""
    blocks = []
    lines = text.split("\n")
    in_block = False
    current_block = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            if in_block:
                blocks.append("\n".join(current_block))
                current_block = []
                in_block = False
            else:
                in_block = True
                # Skip language identifier like ```python
            continue
        if in_block:
            current_block.append(line)

    if current_block:
        blocks.append("\n".join(current_block))

    # If no code blocks found, check if the entire response looks like code
    if not blocks and _looks_like_code(text):
        blocks.append(text)

    return blocks


def _looks_like_code(text: str) -> bool:
    code_indicators = ["import ", "bpy.", "def ", "for ", "if ", "=", "()", "bmesh."]
    lines = text.strip().split("\n")
    code_lines = sum(1 for line in lines if any(ind in line for ind in code_indicators))
    return code_lines > len(lines) * 0.3


def format_error_for_retry(code: str, error: str) -> str:
    """Format the error context to send back to the LLM for a retry."""
    return (
        f"The following Blender Python code produced an error:\n\n"
        f"```python\n{code}\n```\n\n"
        f"Error:\n```\n{error}\n```\n\n"
        f"Please fix the code. Respond only with the corrected Python code."
    )
