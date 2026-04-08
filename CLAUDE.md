# blend-slop

Monorepo for Blender addons. Each subfolder is a self-contained Blender extension.

## Before committing
- Update README.md if features changed (new integrations, new settings, new usage examples)
- Lint check: no unused imports, no f-strings without placeholders, no multi-statement lines

## Build & release
Do NOT zip after every code change. Only build the zip when creating a release:
```
python -c "import shutil; shutil.make_archive('blender_ai_assistant', 'zip', '.', 'blender_ai_assistant')"
gh release create v0.x.0 blender_ai_assistant.zip --title "AI Assistant v0.x.0" --notes "changelog here"
```
The zip is gitignored. For development, install the addon by symlinking the source folder
into Blender's extensions directory.

## Target
- Blender 5.0+ (new extension format with `blender_manifest.toml`, `layout.panel()`, etc.)
- No backwards compatibility with Blender 4.x needed

## Repo structure
```
blend-slop/
  blender_ai_assistant/     # AI chat assistant addon
  pyrightconfig.json          # Shared dev config (IDE type checking)
  .gitignore                  # Excludes *.zip, __pycache__, temp/
```

## Addons

### blender_ai_assistant
AI chat panel in Blender's 3D viewport sidebar.
- LLM providers: Claude, OpenAI, Ollama (local)
- Rich system prompt with Blender 5.x API reference + workflow knowledge
- Scene context injection (objects, materials, modifiers, nodes, addons)
- Auto-executes generated code with error retry loop
- Polyhaven integration (CC0 3D models, local caching, scene deduplication)
- Conversation log + structured error collection in Blender Text blocks

### Code style
- Type annotations on all functions
- Lint-clean (no unused imports, no f-strings without placeholders, no multi-statement lines)
- `fake-bpy-module-latest` installed for IDE type checking
