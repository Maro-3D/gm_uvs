"""Selection modes, multi-object editing, distance welding, and UV picking.

Run in Blender with --background --factory-startup --python-exit-code 1.
Optional arguments after --: --addon-root PATH --snapshot PATH. These allow
the same cases to be compared against a saved pre-refactor add-on.
"""
import argparse
import json
import math
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bmesh
import bpy
from mathutils import Vector

parser = argparse.ArgumentParser()
parser.add_argument("--addon-root", type=Path, default=Path(__file__).resolve().parents[1])
parser.add_argument("--snapshot", type=Path)
options = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
sys.path.insert(0, str(options.addon_root))
import gm_uvs
from gm_uvs._univ import utils

gm_uvs.register()
area = bpy.context.screen.areas[0]
area.type = "IMAGE_EDITOR"
area.ui_type = "UV"
region = next(region for region in area.regions if region.type == "WINDOW")


def make_meshes(tool, selection, count=2):
    if bpy.context.object and bpy.context.object.mode == "EDIT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    objects = []
    for index in range(count):
        mesh = bpy.data.meshes.new("WorkflowMesh")
        mesh.from_pydata(
            [(0, 0, 0), (1, 0, 0), (2, 0, 0),
             (0, 1, 0), (1, 1, 0), (2, 1, 0)],
            [], [(0, 1, 4, 3), (1, 2, 5, 4)],
        )
        mesh.uv_layers.new()
        obj = bpy.data.objects.new(f"Workflow{index}", mesh)
        bpy.context.collection.objects.link(obj)
        obj.select_set(True)
        objects.append(obj)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.object.mode_set(mode="EDIT")
    tools = bpy.context.scene.tool_settings
    for index, obj in enumerate(objects):
        bm = bmesh.from_edit_mesh(obj.data)
        bm.faces.ensure_lookup_table()
        uv = bm.loops.layers.uv.active
        for face in bm.faces:
            face.select_set(not tools.use_uv_select_sync)
        for face in bm.faces:
            selected = selection == "ALL" or selection == "PARTIAL" and face is bm.faces[0]
            if tools.use_uv_select_sync and selected:
                face.select_set(True)
            face.uv_select = selected
            for loop in face.loops:
                x, y = loop.vert.co.xy
                shift = 0.0
                if "weld" in tool and face is bm.faces[1]:
                    shift = 0.0002 if "distance" in tool else 0.25
                loop[uv].uv = (0.1 + 0.2 * x + 0.025 * y + index + shift,
                               0.2 + 0.2 * y + 0.015 * x)
                loop.uv_select_vert = selected
                loop.uv_select_edge = selected
        bm.uv_select_sync_valid = True
        bmesh.update_edit_mesh(obj.data)
    return objects


def capture(objects):
    result = []
    for obj in objects:
        bm = bmesh.from_edit_mesh(obj.data)
        uv = bm.loops.layers.uv.active
        coords = [tuple(loop[uv].uv) for face in bm.faces for loop in face.loops]
        assert all(math.isfinite(value) for point in coords for value in point)
        result.append({
            "uv": coords,
            "seams": [edge.seam for edge in bm.edges],
            "uv_selected": [loop.uv_select_vert for face in bm.faces for loop in face.loops],
        })
    return result


snapshots = {}
for sync in (False, True):
    modes = ("VERT", "EDGE", "FACE") if sync else ("VERTEX", "EDGE", "FACE")
    for mode in modes:
        for selection in ("ALL", "PARTIAL"):
            for tool in ("quadrify", "weld", "distance_all", "distance_islands"):
                tools = bpy.context.scene.tool_settings
                tools.use_uv_select_sync = sync
                if sync:
                    tools.mesh_select_mode = tuple(mode == item for item in ("VERT", "EDGE", "FACE"))
                else:
                    tools.uv_select_mode = mode
                objects = make_meshes(tool if tool != "distance_all" and tool != "distance_islands" else "weld_distance", selection)
                with bpy.context.temp_override(area=area, region=region):
                    if tool == "quadrify":
                        status = bpy.ops.uv.gm_uvs_quadrify()
                    else:
                        status = bpy.ops.uv.gm_uvs_weld(
                            use_by_distance=tool.startswith("distance"), distance=0.001,
                            weld_by_distance_type="ALL" if tool == "distance_all" else "BY_ISLANDS",
                        )
                assert status == {"FINISHED"}, (sync, mode, selection, tool, status)
                snapshots[f"{sync}/{mode}/{selection}/{tool}"] = capture(objects)


# Use a predictable event to exercise the same invoke/picking path as a mouse
# click. Blender still constructs and registers the operators normally.
class GMUVS_TEST_OT_quadrify_pick(bpy.types.Operator.bl_rna_get_subclass_py("UV_OT_gm_uvs_quadrify")):
    bl_idname = "uv.gm_uvs_test_quadrify_pick"

    def execute(self, context):
        if getattr(self, "_picking", False):
            return super().execute(context)
        self._picking = True
        x, y = context.region.view2d.view_to_region(0.22, 0.32, clip=False)
        return super().invoke(context, SimpleNamespace(
            value="PRESS", mouse_region_x=x, mouse_region_y=y))


class GMUVS_TEST_OT_weld_pick(bpy.types.Operator.bl_rna_get_subclass_py("UV_OT_gm_uvs_weld")):
    bl_idname = "uv.gm_uvs_test_weld_pick"

    def execute(self, context):
        if getattr(self, "_picking", False):
            self.mouse_position = Vector((0.31, 0.31))
            return super().execute(context)
        self._picking = True
        x, y = context.region.view2d.view_to_region(0.31, 0.31, clip=False)
        return super().invoke(context, SimpleNamespace(
            value="PRESS", alt=False, mouse_region_x=x, mouse_region_y=y))


for cls in (GMUVS_TEST_OT_quadrify_pick, GMUVS_TEST_OT_weld_pick):
    bpy.utils.register_class(cls)
for tool in ("quadrify", "weld"):
    tools = bpy.context.scene.tool_settings
    tools.use_uv_select_sync = False
    tools.uv_select_mode = "EDGE"
    objects = make_meshes(tool, "NONE", count=1)
    before = capture(objects)
    # Background Blender has no initialized viewport transform. Stub only the
    # pixel-to-UV conversion, keeping the operators' actual picking logic.
    point = (0.22, 0.32) if tool == "quadrify" else (0.31, 0.31)
    with bpy.context.temp_override(area=area, region=region), \
            patch.object(utils, "get_mouse_pos", return_value=Vector(point)), \
            patch.object(utils, "get_max_distance_from_px", return_value=1.0):
        if tool == "quadrify":
            status = bpy.ops.uv.gm_uvs_test_quadrify_pick()
        else:
            status = bpy.ops.uv.gm_uvs_test_weld_pick()
    assert status == {"FINISHED"}, (tool, status)
    after = capture(objects)
    assert before != after, f"{tool} must pick and modify an island with no UV selection"
    snapshots[f"pick/{tool}"] = after
for cls in (GMUVS_TEST_OT_weld_pick, GMUVS_TEST_OT_quadrify_pick):
    bpy.utils.unregister_class(cls)

gm_uvs.unregister()
if options.snapshot:
    options.snapshot.write_text(json.dumps(snapshots, indent=2), encoding="utf-8")
print(f"PASS: {len(snapshots)} selection-mode, multi-object, distance, and picking workflows")
