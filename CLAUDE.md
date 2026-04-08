# Project: Blender AI Assistant Addon

## Build rule
After every code change, rebuild the installable zip package:
```
powershell -Command "Compress-Archive -Path blender_ai_assistant -DestinationPath blender_ai_assistant.zip -Force"
```
The zip goes in the project root. This is the file the user installs in Blender via Edit > Preferences > Add-ons > Install from Disk.

## Target
- Blender 5.0+ (uses new extension format with `blender_manifest.toml`, `layout.panel()`, etc.)
- No backwards compatibility with Blender 4.x needed

## Structure
- `blender_ai_assistant/` - The addon source
- `blender_ai_assistant.zip` - Installable package (rebuild after every change)
