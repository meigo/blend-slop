import bpy
from bpy.props import StringProperty, EnumProperty, IntProperty
from bpy.types import AddonPreferences


def get_addon_preferences(context: bpy.types.Context | None = None) -> "AIAssistantPreferences":
    if context is None:
        context = bpy.context
    return context.preferences.addons[__package__].preferences


class AIAssistantPreferences(AddonPreferences):
    bl_idname = __package__

    provider: EnumProperty(
        name="Provider",
        items=[
            ("CLAUDE", "Claude (Anthropic)", "Use Anthropic Claude API"),
            ("OPENAI", "OpenAI", "Use OpenAI API (GPT-4o, etc.)"),
            ("OLLAMA", "Ollama (Local)", "Use local Ollama instance"),
        ],
        default="CLAUDE",
        description="LLM provider to use",
    )

    claude_api_key: StringProperty(
        name="Claude API Key",
        subtype="PASSWORD",
        description="Anthropic API key (starts with sk-ant-)",
    )

    claude_model: EnumProperty(
        name="Claude Model",
        items=[
            ("claude-sonnet-4-20250514", "Claude Sonnet 4", "Fast and capable"),
            ("claude-opus-4-20250514", "Claude Opus 4", "Most capable"),
            ("claude-haiku-4-20250414", "Claude Haiku 4", "Fastest and cheapest"),
        ],
        default="claude-sonnet-4-20250514",
    )

    openai_api_key: StringProperty(
        name="OpenAI API Key",
        subtype="PASSWORD",
        description="OpenAI API key (starts with sk-)",
    )

    openai_model: EnumProperty(
        name="OpenAI Model",
        items=[
            ("gpt-4o", "GPT-4o", "Most capable"),
            ("gpt-4o-mini", "GPT-4o Mini", "Fast and cheap"),
            ("gpt-4.1", "GPT-4.1", "Latest GPT-4 variant"),
        ],
        default="gpt-4o",
    )

    ollama_url: StringProperty(
        name="Ollama URL",
        default="http://localhost:11434",
        description="Ollama server URL",
    )

    ollama_model: StringProperty(
        name="Ollama Model",
        default="qwen2.5-coder:7b",
        description="Model name (e.g. qwen2.5-coder:7b, llama3.2, deepseek-coder-v2)",
    )

    max_retries: IntProperty(
        name="Max Retries",
        default=3,
        min=0,
        max=10,
        description="Number of automatic retries on code execution error",
    )

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout

        layout.prop(self, "provider")
        layout.separator()

        if self.provider == "CLAUDE":
            layout.prop(self, "claude_api_key")
            layout.prop(self, "claude_model")
        elif self.provider == "OPENAI":
            layout.prop(self, "openai_api_key")
            layout.prop(self, "openai_model")
        elif self.provider == "OLLAMA":
            layout.prop(self, "ollama_url")
            layout.prop(self, "ollama_model")

        layout.separator()
        layout.prop(self, "max_retries")


classes = (AIAssistantPreferences,)


def register() -> None:
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister() -> None:
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
