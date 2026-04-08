import bpy
import threading
import queue
from datetime import datetime
from bpy.types import Operator

from . import llm_client
from . import code_execution
from . import scene_context
from . import polyhaven
from .preferences import get_addon_preferences


LOG_TEXT_NAME = "AI Assistant Log"
ERROR_LOG_NAME = "AI Assistant Errors"

# Global queue for thread-safe communication between HTTP thread and main thread
_result_queue = queue.Queue()


def _get_log_text() -> bpy.types.Text:
    """Get or create the Text block used for full conversation log."""
    if LOG_TEXT_NAME not in bpy.data.texts:
        bpy.data.texts.new(LOG_TEXT_NAME)
    return bpy.data.texts[LOG_TEXT_NAME]


def _log_write(role: str, content: str) -> None:
    """Append a message to the log Text block."""
    log = _get_log_text()
    prefix = {"user": "USER", "assistant": "AI", "system": "SYSTEM"}.get(role, role.upper())
    separator = "=" * 60
    log.write(f"\n{separator}\n[{prefix}]\n{separator}\n{content}\n")


def _get_error_log() -> bpy.types.Text:
    """Get or create the Text block for structured error collection."""
    if ERROR_LOG_NAME not in bpy.data.texts:
        bpy.data.texts.new(ERROR_LOG_NAME)
    return bpy.data.texts[ERROR_LOG_NAME]


def _log_error(prompt: str, code: str, error: str) -> None:
    """Log a structured error entry for later analysis."""
    log = _get_error_log()
    prefs = get_addon_preferences()
    blender_ver = ".".join(str(v) for v in bpy.app.version)
    provider = prefs.provider
    if provider == "CLAUDE":
        model = prefs.claude_model
    elif provider == "OPENAI":
        model = prefs.openai_model
    else:
        model = prefs.ollama_model

    entry = (
        f"\n{'#' * 60}\n"
        f"## Error @ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"Blender: {blender_ver}\n"
        f"Provider: {provider} / {model}\n"
        f"\n### Prompt\n{prompt}\n"
        f"\n### Generated Code\n```python\n{code}\n```\n"
        f"\n### Traceback\n```\n{error}\n```\n"
    )
    log.write(entry)


def _redraw_views() -> None:
    """Force redraw of 3D viewports."""
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()


class AIASSIST_OT_send_message(Operator):
    bl_idname = "ai_assistant.send_message"
    bl_label = "Send Message"
    bl_description = "Send message to the AI assistant"

    def execute(self, context: bpy.types.Context) -> set[str]:
        state = context.scene.ai_assistant
        prompt_text = state.prompt.strip()

        if not prompt_text:
            self.report({"WARNING"}, "Please type a message first")
            return {"CANCELLED"}

        if state.is_busy:
            self.report({"WARNING"}, "AI assistant is already processing")
            return {"CANCELLED"}

        prefs = get_addon_preferences(context)

        # Validate API key
        if prefs.provider == "CLAUDE" and not prefs.claude_api_key:
            self.report({"ERROR"}, "Claude API key not set. Check addon preferences.")
            return {"CANCELLED"}
        elif prefs.provider == "OPENAI" and not prefs.openai_api_key:
            self.report({"ERROR"}, "OpenAI API key not set. Check addon preferences.")
            return {"CANCELLED"}

        # Clear UI messages from previous exchange, keep full history in log
        state.messages.clear()

        # Add user message to UI
        msg = state.messages.add()
        msg.role = "user"
        msg.content = prompt_text

        # Log it
        _log_write("user", prompt_text)

        # Clear input
        state.prompt = ""
        state.is_busy = True

        # Build conversation history from the full log text block
        history = _build_history_from_log()

        # Always include scene context
        scene_ctx = scene_context.get_scene_summary()

        blender_version = ".".join(str(v) for v in bpy.app.version)
        system_prompt = llm_client.build_system_prompt(blender_version, scene_ctx, rich=state.rich_prompt)
        _, messages = llm_client.build_messages(system_prompt, history)

        # Gather provider settings
        provider = prefs.provider
        if provider == "CLAUDE":
            api_key = prefs.claude_api_key
            model = prefs.claude_model
        elif provider == "OPENAI":
            api_key = prefs.openai_api_key
            model = prefs.openai_model
        else:
            api_key = None
            model = prefs.ollama_model

        ollama_url = prefs.ollama_url

        # Spawn background thread for HTTP call
        thread = threading.Thread(
            target=_background_llm_call,
            args=(provider, api_key, model, ollama_url, system_prompt, messages),
            daemon=True,
        )
        thread.start()

        # Register timer to poll for results on main thread
        bpy.app.timers.register(_check_result_queue, first_interval=0.1)

        _redraw_views()
        return {"FINISHED"}


class AIASSIST_OT_clear_chat(Operator):
    bl_idname = "ai_assistant.clear_chat"
    bl_label = "Clear Chat"
    bl_description = "Clear chat display (log is preserved in Text Editor)"

    def execute(self, context: bpy.types.Context) -> set[str]:
        state = context.scene.ai_assistant
        state.messages.clear()
        state.active_message_index = 0
        state.is_busy = False
        return {"FINISHED"}


class AIASSIST_OT_clear_log(Operator):
    bl_idname = "ai_assistant.clear_log"
    bl_label = "Clear Log"
    bl_description = "Clear the full conversation log"

    def execute(self, context: bpy.types.Context) -> set[str]:
        if LOG_TEXT_NAME in bpy.data.texts:
            bpy.data.texts.remove(bpy.data.texts[LOG_TEXT_NAME])
        _get_log_text()  # Recreate empty
        # Clear panel UI too
        state = context.scene.ai_assistant
        state.messages.clear()
        state.is_busy = False
        self.report({"INFO"}, "Log cleared")
        return {"FINISHED"}


class AIASSIST_OT_open_log(Operator):
    bl_idname = "ai_assistant.open_log"
    bl_label = "Open Log"
    bl_description = "Open the conversation log in Blender's Text Editor"

    def execute(self, context: bpy.types.Context) -> set[str]:
        log = _get_log_text()

        # If there's already a text editor open, just point it at the log
        for area in context.screen.areas:
            if area.type == "TEXT_EDITOR":
                area.spaces.active.text = log
                self.report({"INFO"}, "Log opened in Text Editor")
                return {"FINISHED"}

        # No text editor visible -- show a popup with instructions
        def draw_popup(self_popup: object, context: bpy.types.Context) -> None:
            self_popup.layout.label(text=f"Select '{LOG_TEXT_NAME}' in the text dropdown.")

        context.window_manager.popup_menu(draw_popup, title="Open Scripting workspace", icon="TEXT")
        return {"FINISHED"}


class AIASSIST_OT_copy_errors(Operator):
    bl_idname = "ai_assistant.copy_errors"
    bl_label = "Copy Errors"
    bl_description = "Copy collected errors to clipboard (formatted for GitHub issue)"

    def execute(self, context: bpy.types.Context) -> set[str]:
        if ERROR_LOG_NAME not in bpy.data.texts:
            self.report({"INFO"}, "No errors collected")
            return {"CANCELLED"}

        log = bpy.data.texts[ERROR_LOG_NAME]
        text = log.as_string().strip()
        if not text:
            self.report({"INFO"}, "No errors collected")
            return {"CANCELLED"}

        context.window_manager.clipboard = text
        # Count errors
        count = text.count("## Error @")
        self.report({"INFO"}, f"{count} error(s) copied to clipboard")
        return {"FINISHED"}


class AIASSIST_OT_clear_errors(Operator):
    bl_idname = "ai_assistant.clear_errors"
    bl_label = "Clear Errors"
    bl_description = "Clear collected errors"

    def execute(self, context: bpy.types.Context) -> set[str]:
        if ERROR_LOG_NAME in bpy.data.texts:
            bpy.data.texts.remove(bpy.data.texts[ERROR_LOG_NAME])
        self.report({"INFO"}, "Errors cleared")
        return {"FINISHED"}


def _build_history_from_log() -> list[dict[str, str]]:
    """Parse the log Text block back into a conversation history list."""
    if LOG_TEXT_NAME not in bpy.data.texts:
        return []

    log = bpy.data.texts[LOG_TEXT_NAME]
    text = log.as_string()
    if not text.strip():
        return []

    history = []
    separator = "=" * 60
    sections = text.split(separator)

    current_role = None
    for section in sections:
        section = section.strip()
        if not section:
            continue
        if section == "[USER]":
            current_role = "user"
        elif section == "[AI]":
            current_role = "assistant"
        elif section == "[SYSTEM]":
            current_role = None  # Skip system messages in history sent to LLM
        elif current_role in ("user", "assistant"):
            history.append({"role": current_role, "content": section})
            current_role = None

    # Keep last 20 exchanges to avoid huge context
    if len(history) > 40:
        history = history[-40:]

    return history


def _background_llm_call(provider: str, api_key: str | None, model: str, ollama_url: str, system_prompt: str, messages: list[dict[str, str]]) -> None:
    """Run LLM API call in a background thread. Puts result in the global queue."""
    try:
        if provider == "CLAUDE":
            response = llm_client.call_claude(api_key, model, system_prompt, messages)
        elif provider == "OPENAI":
            response = llm_client.call_openai(api_key, model, system_prompt, messages)
        else:
            response = llm_client.call_ollama(ollama_url, model, system_prompt, messages)
        _result_queue.put(("success", response))
    except Exception as e:
        _result_queue.put(("error", str(e)))


def _check_result_queue() -> float | None:
    """Timer callback: polls the result queue on the main thread."""
    if _result_queue.empty():
        return 0.1  # Check again in 100ms

    status, data = _result_queue.get()

    scene = bpy.context.scene
    if not hasattr(scene, "ai_assistant"):
        return None

    state = scene.ai_assistant

    if status == "success":
        # Add assistant response to UI
        msg = state.messages.add()
        msg.role = "assistant"
        msg.content = data
        _log_write("assistant", data)

        # Extract code blocks
        code_blocks = code_execution.extract_code_blocks(data)
        if code_blocks:
            msg.code = "\n\n".join(code_blocks)

            # Always auto-execute
            success, stdout, error = code_execution.execute_code(msg.code)
            if success:
                content = "Executed successfully." + (f"\nOutput:\n{stdout}" if stdout.strip() else "")
                result_msg = state.messages.add()
                result_msg.role = "system"
                result_msg.content = content
                _log_write("system", content)
                state.is_busy = False
            else:
                content = f"Execution error:\n{error}"
                result_msg = state.messages.add()
                result_msg.role = "system"
                result_msg.content = content
                result_msg.is_error = True
                _log_write("system", content)

                # Collect error for analysis
                user_prompt = ""
                for m in state.messages:
                    if m.role == "user":
                        user_prompt = m.content
                _log_error(user_prompt, msg.code, error)

                # Auto-retry on error
                prefs = get_addon_preferences()
                if prefs.max_retries > 0:
                    _trigger_retry(None, msg.code, error)
                else:
                    state.is_busy = False
        else:
            state.is_busy = False
    else:
        msg = state.messages.add()
        msg.role = "system"
        msg.content = f"API Error: {data}"
        msg.is_error = True
        _log_write("system", f"API Error: {data}")
        state.is_busy = False

    _redraw_views()
    return None  # Unregister timer


_retry_count = 0


def _trigger_retry(context: bpy.types.Context | None, failed_code: str, error: str) -> None:
    """Send the error back to the LLM for automatic correction."""
    global _retry_count
    prefs = get_addon_preferences(context)

    if _retry_count >= prefs.max_retries:
        _retry_count = 0
        state = bpy.context.scene.ai_assistant
        state.is_busy = False

        # Add final failure message
        fail_msg = state.messages.add()
        fail_msg.role = "system"
        fail_msg.content = f"Failed after {prefs.max_retries} retries. Check the log for details."
        fail_msg.is_error = True
        _log_write("system", f"Failed after {prefs.max_retries} retries.")
        return

    _retry_count += 1

    state = bpy.context.scene.ai_assistant
    state.is_busy = True

    retry_prompt = code_execution.format_error_for_retry(failed_code, error)
    _log_write("user", f"[Auto-retry {_retry_count}] {retry_prompt}")

    # Add retry indicator in UI
    retry_ui = state.messages.add()
    retry_ui.role = "system"
    retry_ui.content = f"Retrying... (attempt {_retry_count}/{prefs.max_retries})"

    # Build conversation from log
    history = _build_history_from_log()

    blender_version = ".".join(str(v) for v in bpy.app.version)
    scene_ctx = scene_context.get_scene_summary()
    system_prompt = llm_client.build_system_prompt(blender_version, scene_ctx, rich=state.rich_prompt)
    _, messages = llm_client.build_messages(system_prompt, history)

    provider = prefs.provider
    if provider == "CLAUDE":
        api_key = prefs.claude_api_key
        model = prefs.claude_model
    elif provider == "OPENAI":
        api_key = prefs.openai_api_key
        model = prefs.openai_model
    else:
        api_key = None
        model = prefs.ollama_model

    thread = threading.Thread(
        target=_background_llm_call,
        args=(provider, api_key, model, prefs.ollama_url, system_prompt, messages),
        daemon=True,
    )
    thread.start()
    bpy.app.timers.register(_check_result_queue, first_interval=0.1)


class AIASSIST_OT_clear_polyhaven_cache(Operator):
    bl_idname = "ai_assistant.clear_polyhaven_cache"
    bl_label = "Clear Polyhaven Cache"
    bl_description = "Delete all cached Polyhaven model downloads"

    def execute(self, context: bpy.types.Context) -> set[str]:
        count, size_mb = polyhaven.clear_cache()
        self.report({"INFO"}, f"Cleared {count} cached models ({size_mb:.1f} MB)")
        return {"FINISHED"}


class AIASSIST_OT_clear_sketchfab_cache(Operator):
    bl_idname = "ai_assistant.clear_sketchfab_cache"
    bl_label = "Clear Sketchfab Cache"
    bl_description = "Delete all cached Sketchfab model downloads"

    def execute(self, context: bpy.types.Context) -> set[str]:
        from . import sketchfab
        count, size_mb = sketchfab.clear_cache()
        self.report({"INFO"}, f"Cleared {count} cached models ({size_mb:.1f} MB)")
        return {"FINISHED"}


classes = (
    AIASSIST_OT_send_message,
    AIASSIST_OT_clear_chat,
    AIASSIST_OT_clear_log,
    AIASSIST_OT_open_log,
    AIASSIST_OT_copy_errors,
    AIASSIST_OT_clear_errors,
    AIASSIST_OT_clear_polyhaven_cache,
    AIASSIST_OT_clear_sketchfab_cache,
)


def register() -> None:
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister() -> None:
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
