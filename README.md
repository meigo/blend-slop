# blend-slop

Blender addons for AI-assisted 3D workflows.

## Addons

### AI Assistant (`blender_ai_assistant/`)

A chat panel inside Blender's 3D viewport that lets you control Blender through natural language. Ask it to create objects, set up materials, configure lighting, animate, render -- it generates and executes Python code automatically.

**Features:**
- Chat interface in the 3D viewport sidebar (N panel > AI Assistant tab)
- Supports **Claude**, **OpenAI**, and **Ollama** (local models) as LLM providers
- Deep Blender 5.x API knowledge in the system prompt -- knows about renamed nodes, removed APIs, and common pitfalls
- Understands natural language ("make it glossy", "add thickness", "three-point lighting") and maps to correct Blender operations
- Sends current scene state to the LLM (objects, materials, modifiers, node trees, lights, cameras, enabled addons)
- Auto-executes generated code with automatic error retry (sends traceback back to LLM for correction)
- **Polyhaven integration** -- downloads CC0 3D models (furniture, plants, rocks, props) directly into the scene with local caching
- Full conversation log and structured error collection in Blender Text blocks

**Requirements:**
- Blender 5.0+
- API key for Claude or OpenAI (or a running Ollama instance for local models)

### Installation

1. Download `blender_ai_assistant.zip` from [Releases](https://github.com/meigo/blend-slop/releases)
2. In Blender: Edit > Preferences > Add-ons > Install from Disk > select the zip
3. Enable the addon
4. Open the sidebar (N key) in the 3D viewport > **AI Assistant** tab
5. Expand Settings, select your provider, and enter your API key
6. Start chatting

### Usage examples

```
"Add a red metallic sphere next to the cube"
"Set up three-point lighting for the scene"
"Make the floor material look like polished concrete"
"Add an armchair from Polyhaven near the table"
"Animate the camera orbiting around the origin over 120 frames"
"Render at 1080p with transparent background"
```

## Development

```bash
# Install type stubs for IDE support
pip install fake-bpy-module-latest

# Build installable zip
python -c "import shutil; shutil.make_archive('blender_ai_assistant', 'zip', '.', 'blender_ai_assistant')"
```

## License

MIT
