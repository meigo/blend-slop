import bpy
from bpy.props import (
    StringProperty,
    CollectionProperty,
    IntProperty,
    BoolProperty,
)
from bpy.types import PropertyGroup


class AIMessageItem(PropertyGroup):
    role: StringProperty(name="Role", default="user")  # "user", "assistant", "system", "code"
    content: StringProperty(name="Content", default="")
    code: StringProperty(name="Code", default="")
    is_error: BoolProperty(name="Is Error", default=False)


class AIAssistantState(PropertyGroup):
    messages: CollectionProperty(type=AIMessageItem)
    active_message_index: IntProperty(name="Active Message", default=0)
    prompt: StringProperty(
        name="Prompt",
        default="",
        description="Type your message to the AI assistant",
    )
    is_busy: BoolProperty(name="Is Busy", default=False)
    rich_prompt: BoolProperty(
        name="Rich Prompt",
        default=True,
        description="Full API reference in system prompt (more accurate, ~2.5K extra tokens). Disable for cheaper/faster calls",
    )


classes = (
    AIMessageItem,
    AIAssistantState,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.ai_assistant = bpy.props.PointerProperty(type=AIAssistantState)


def unregister():
    del bpy.types.Scene.ai_assistant
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
