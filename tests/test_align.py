"""Run in Blender: --background --python-exit-code 1 --python tests/test_align.py."""
import sys
from pathlib import Path
import bpy
import bmesh

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gm_uvs
from gm_uvs import transform as selection

gm_uvs.register()
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
bpy.ops.mesh.primitive_cube_add()
obj = bpy.context.object
bpy.ops.object.mode_set(mode="EDIT")
area = bpy.context.screen.areas[0]
area.type = "IMAGE_EDITOR"
area.ui_type = "UV"
window = next(r for r in area.regions if r.type == "WINDOW")
ui = next(r for r in area.regions if r.type == "UI")
bm = bmesh.from_edit_mesh(obj.data)
layer = bm.loops.layers.uv.active
loops = [loop for face in bm.faces for loop in face.loops]
for loop in loops:
    uv = loop[layer].uv.copy()
    loop[layer].uv = (0.2 + uv.x * 0.5, 0.2 + uv.y * 0.5)
initial = [tuple(loop[layer].uv) for loop in loops]
mins = [min(uv[axis] for uv in initial) for axis in (0, 1)]
maxs = [max(uv[axis] for uv in initial) for axis in (0, 1)]
assert mins[0] > 0 and maxs[0] < 1, "Cube UVs must be centered horizontally"
cases = {
    "TOP_LEFT": ("MIN", "MAX"), "TOP": (None, "MAX"),
    "TOP_RIGHT": ("MAX", "MAX"), "LEFT": ("MIN", None),
    "CENTER_V": (None, "CENTER"), "CENTER": ("CENTER", "CENTER"),
    "CENTER_U": ("CENTER", None), "RIGHT": ("MAX", None),
    "BOTTOM_LEFT": ("MIN", "MIN"), "BOTTOM": (None, "MIN"),
    "BOTTOM_RIGHT": ("MAX", "MIN"),
}
checks = 0
for sync in (False, True):
    bpy.context.scene.tool_settings.use_uv_select_sync = sync
    for direction, modes in cases.items():
        for loop, uv in zip(loops, initial):
            loop[layer].uv = uv
        bmesh.update_edit_mesh(obj.data)
        with bpy.context.temp_override(area=area, region=window):
            bpy.ops.uv.select_all(action="SELECT")
        with bpy.context.temp_override(area=area, region=ui):
            assert bpy.ops.uv.gm_uvs_align(direction=direction) == {"FINISHED"}
        offsets = []
        for axis, mode in enumerate(modes):
            if mode == "MIN":
                offsets.append(-mins[axis])
            elif mode == "MAX":
                offsets.append(1 - maxs[axis])
            elif mode == "CENTER":
                offsets.append(0.5 - (mins[axis] + maxs[axis]) / 2)
            else:
                offsets.append(0)
        for loop, uv in zip(loops, initial):
            expected = (uv[0] + offsets[0], uv[1] + offsets[1])
            assert all(abs(a - b) < 1e-6 for a, b in zip(loop[layer].uv, expected)), (
                sync, direction, tuple(loop[layer].uv), expected)
        checks += 1

# A partial selection moves; unselected UVs retain their coordinates.
bpy.context.scene.tool_settings.use_uv_select_sync = False
for loop, uv in zip(loops, initial):
    loop[layer].uv = uv
    loop.uv_select_vert = False
loops[0].uv_select_vert = True
bmesh.update_edit_mesh(obj.data)
with bpy.context.temp_override(area=area, region=ui):
    assert bpy.ops.uv.gm_uvs_align(direction="BOTTOM_LEFT") == {"FINISHED"}
assert all(abs(value) < 1e-6 for value in loops[0][layer].uv)
for loop, uv in zip(loops[1:], initial[1:]):
    assert all(abs(a - b) < 1e-6 for a, b in zip(loop[layer].uv, uv))
checks += 1

# Sync mode must follow mesh selection even if UV corner flags are stale.
bpy.context.scene.tool_settings.use_uv_select_sync = True
bpy.context.scene.tool_settings.mesh_select_mode = (False, False, True)
for loop, uv in zip(loops, initial):
    loop[layer].uv = uv
    loop.uv_select_vert = False
for face in bm.faces:
    face.select_set(True)
bm.uv_select_sync_valid = True
bmesh.update_edit_mesh(obj.data)
with bpy.context.temp_override(area=area, region=ui):
    assert bpy.ops.uv.gm_uvs_align(direction="BOTTOM_LEFT") == {"FINISHED"}
assert all(abs(a - b) < 1e-6 for loop, uv in zip(loops, initial)
           for a, b in zip(loop[layer].uv, (uv[0] - mins[0], uv[1] - mins[1])))
checks += 1

# In face mode, selecting one face moves its full UV island.
bpy.context.scene.tool_settings.use_uv_select_sync = True
bpy.context.scene.tool_settings.mesh_select_mode = (False, False, True)
for loop, uv in zip(loops, initial):
    loop[layer].uv = uv
for face in bm.faces:
    face.select_set(False)
island = max(selection._uv_island_faces(bm, layer), key=len)
assert len(island) > 1
island[0].select_set(True)
selected_group = selection.selected_uvs(bpy.context)
assert len(selected_group) == 1
selected_loops = set(selected_group[0][3])
assert len(selected_loops) == sum(len(face.loops) for face in island)
bmesh.update_edit_mesh(obj.data)
with bpy.context.temp_override(area=area, region=ui):
    assert bpy.ops.uv.gm_uvs_align(direction="BOTTOM_LEFT") == {"FINISHED"}
island_min = (
    min(loop[layer].uv.x for loop in selected_loops),
    min(loop[layer].uv.y for loop in selected_loops),
)
assert all(abs(value) < 1e-6 for value in island_min)
assert any(loop[layer].uv.length > 0.1 for loop in selected_loops)
for loop, uv in zip(loops, initial):
    if loop not in selected_loops:
        assert all(abs(a - b) < 1e-6 for a, b in zip(loop[layer].uv, uv))
checks += 1

# The operator must survive collection between selection gathering and UV access.
import gc
original_selected_uvs = selection.selected_uvs

def selected_uvs_with_collection(context):
    groups = original_selected_uvs(context)
    gc.collect()
    return groups

selection.selected_uvs = selected_uvs_with_collection
for loop, uv in zip(loops, initial):
    loop[layer].uv = uv
for face in bm.faces:
    face.select_set(True)
bmesh.update_edit_mesh(obj.data)
with bpy.context.temp_override(area=area, region=ui):
    assert bpy.ops.uv.gm_uvs_align(direction="BOTTOM_LEFT") == {"FINISHED"}
assert min(loop[layer].uv.x for loop in loops) < 1e-6
selection.selected_uvs = original_selected_uvs
checks += 1

gm_uvs.unregister()
print(f"PASS: {checks} UV layout movement checks on Blender {bpy.app.version_string}")

