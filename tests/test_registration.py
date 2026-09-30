"""Exercise enable/disable cycles in Blender, including extension-style imports."""
import importlib
import sys
import types
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gm_uvs


def check_lifecycle(addon):
    from_module = addon
    properties = ("gm_uvs_univ_settings",) + tuple(
        name for name, _label in from_module.QUADRIFY_SETTINGS
    )
    for _ in range(3):
        addon.register()
        assert all(cls.is_registered for cls in from_module.CLASSES)
        assert all(hasattr(bpy.types.Scene, name) for name in properties)
        assert all(getattr(bpy.context.scene, name)
                   for name, _label in from_module.QUADRIFY_SETTINGS)
        assert not bpy.app.timers.is_registered(from_module._init_shaders)
        addon.unregister()
        assert not any(cls.is_registered for cls in from_module.CLASSES)
        assert not any(hasattr(bpy.types.Scene, name) for name in properties)


check_lifecycle(gm_uvs)

# Blender extensions use a dotted package name; no imports may assume gm_uvs
# is a top-level module. Use a separate namespace without installing anything.
namespace = types.ModuleType("gm_uvs_test_extensions")
namespace.__path__ = [str(Path(__file__).resolve().parents[1])]
sys.modules[namespace.__name__] = namespace
extension = importlib.import_module(f"{namespace.__name__}.gm_uvs")
check_lifecycle(extension)
print("PASS: repeated registration and extension namespace imports")
