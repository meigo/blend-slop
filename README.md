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
- **Sketchfab integration** -- search and download from 1M+ free CC-licensed 3D models (characters, vehicles, animals, props)
- **Polyhaven integration** -- download CC0 3D models (furniture, plants, rocks, nature), PBR textures (wood, brick, stone, metal, fabric, etc.), and HDRIs (environment lighting) with no auth needed
- **Auto-scaling** -- downloaded models are scaled to real-world size based on LLM's height estimate
- **Dimensions database** -- 300+ real-world object heights for correctly scaled primitive creation
- **PBR material creation** -- automatically builds full Principled BSDF node trees from downloaded texture maps (diffuse, normal, roughness, displacement, AO)
- Local caching and scene deduplication for downloaded models and textures
- Smart search result filtering -- validates Sketchfab results by name relevance before importing
- Full conversation log and structured error collection in Blender Text blocks

**Requirements:**
- Blender 5.0+
- API key for Claude or OpenAI (or a running Ollama instance for local models)
- Optional: Sketchfab API token for model downloads (get from [sketchfab.com/settings/password](https://sketchfab.com/settings/password))

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
"Add a brick texture to the wall"
"Apply a wood material to the table"
"Add an armchair near the table"
"Find a dragon model on Sketchfab and add it to the scene"
"Animate the camera orbiting around the origin over 120 frames"
"Render at 1080p with transparent background"
"Make the cube spin continuously on the Z axis"
"At frame 50, lift the plant 2 units, hold it there for 25 frames with a violent shake, then drop it back down with a bounce"
"Set up a sunset HDRI for the scene"
"Add rigid body physics to all the objects so they fall and collide"
"Scatter rocks across the terrain using geometry nodes"
"Create a cloth simulation on the tablecloth"
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
