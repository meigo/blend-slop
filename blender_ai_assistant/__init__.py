from . import properties
from . import preferences
from . import operators
from . import panels


def register():
    properties.register()
    preferences.register()
    operators.register()
    panels.register()


def unregister():
    panels.unregister()
    operators.unregister()
    preferences.unregister()
    properties.unregister()
