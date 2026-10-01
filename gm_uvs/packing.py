"""Persistent island groups and bounded, deterministic single-tile packing."""
import uuid
import colorsys
from time import perf_counter
from bpy.app.handlers import persistent

import bpy
import bmesh
from bpy.props import CollectionProperty, FloatProperty, FloatVectorProperty, IntProperty, StringProperty, BoolProperty
from .transform import is_uv_edit_mode, selected_uvs, _uv_island_faces
from .stacking import align_polygons


def redraw_uvs(self=None, context=None):
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'IMAGE_EDITOR':
                area.tag_redraw()


def layer_visibility(self, context):
    """Hide/reveal only faces owned by this layer's eye toggle."""
    if context is None or context.mode != 'EDIT_MESH' or not self.uid:
        redraw_uvs()
        return
    _overlay_sources.clear()
    sync = context.scene.tool_settings.use_uv_select_sync
    for obj in context.objects_in_mode_unique_data:
        if obj.type != 'MESH':
            continue
        bm = bmesh.from_edit_mesh(obj.data)
        sync_valid = bm.uv_select_sync_valid
        uv = bm.loops.layers.uv.active
        if uv is None:
            continue
        assignment_name, hidden_name = 'gm_pack_' + uv.name, 'gm_hidden_' + uv.name
        if bm.faces.layers.int.get(assignment_name) is None:
            continue
        if bm.faces.layers.int.get(hidden_name) is None:
            bm.faces.layers.int.new(hidden_name)
        assignment = bm.faces.layers.int.get(assignment_name)
        hidden = bm.faces.layers.int.get(hidden_name)
        for face in bm.faces:
            if not self.visible and face[assignment] == self.uid and not face.hide:
                face[hidden] = self.uid
                face.uv_select = False
                for loop in face.loops:
                    loop.uv_select_vert = False
                    loop.uv_select_edge = False
                face.hide_set(True)
            elif self.visible and face[hidden] == self.uid:
                face.hide_set(False)
                face[hidden] = 0
                if not sync:
                    face.select_set(True)
        bm.select_flush_mode()
        # Preserve the pre-existing cache state instead of declaring stale
        # selections valid when visibility was changed after native mesh edits.
        if sync:
            bm.uv_select_sync_valid = sync_valid
        bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
    redraw_uvs()


def _perimeter(face, uv):
    return sum((loop[uv].uv - loop.link_loop_next[uv].uv).length for loop in face.loops)


def _ensure_original_sizes(context):
    # Allocate custom data before gathering any face/loop references.
    _overlay_sources.clear()
    for obj in context.objects_in_mode_unique_data:
        if obj.type != 'MESH':
            continue
        bm = bmesh.from_edit_mesh(obj.data)
        uv = bm.loops.layers.uv.active
        if uv and bm.faces.layers.float.get('gm_size_' + uv.name) is None:
            bm.faces.layers.float.new('gm_size_' + uv.name)


def _original_factor(bm, uv, faces):
    attr = bm.faces.layers.float.get('gm_size_' + uv.name)
    if attr is None:
        return 1.0
    original = sum(face[attr] for face in faces)
    current = sum(_perimeter(face, uv) for face in faces)
    return current / original if original > 1e-10 and current > 1e-10 else 1.0


def _preview_island(bm, uv, faces, loops, target):
    attr = bm.faces.layers.float.get('gm_size_' + uv.name)
    for face in faces:
        if face[attr] <= 0:
            face[attr] = _perimeter(face, uv)
    factor = target / _original_factor(bm, uv, faces)
    coords = [loop[uv].uv.copy() for loop in loops]
    from mathutils import Vector
    center = Vector(((min(p.x for p in coords)+max(p.x for p in coords))/2,
                     (min(p.y for p in coords)+max(p.y for p in coords))/2))
    for loop, p in zip(loops, coords):
        loop[uv].uv = center + (p-center)*factor


def preview_layer_scale(self, context):
    if context is None or context.mode != 'EDIT_MESH' or not self.uid:
        return
    _ensure_original_sizes(context)
    changed = set()
    for mesh, bm, uv, faces, loops, uid in records(context):
        if uid == self.uid:
            _preview_island(bm, uv, faces, loops, self.max_scale)
            changed.add(mesh)
    for mesh in changed:
        bmesh.update_edit_mesh(mesh, loop_triangles=False, destructive=False)
    if changed:
        context.scene.gm_uvs_pack_result = ''
        if self.stack_matching:
            _stack_layer(self, context)
    redraw_uvs()


def _polygons(record):
    _, _, uv, faces, _, _ = record
    return [[complex(*loop[uv].uv) for loop in face.loops] for face in faces]


def stack_groups(islands, enabled):
    """Groups contain (island index, coordinates aligned to the leader)."""
    groups = []
    # Smallest original island leads, so stacking never exceeds a member's cap.
    def original_size(i):
        _, bm, uv, faces, _, _ = islands[i]
        return sum(_perimeter(f, uv) for f in faces)/_original_factor(bm, uv, faces)
    for i in sorted(range(len(islands)), key=original_size):
        uid = islands[i][5]
        source = _polygons(islands[i])
        for group in groups:
            leader = group[0][0]
            if uid not in enabled or islands[leader][5] != uid:
                continue
            aligned = align_polygons(source, _polygons(islands[leader]))
            if aligned is not None:
                group.append((i, aligned))
                break
        else:
            groups.append([(i, [p for poly in source for p in poly])])
    return groups


def _stack_layer(self, context):
    if context is None or context.mode != 'EDIT_MESH' or not self.stack_matching:
        redraw_uvs()
        return
    _ensure_original_sizes(context)
    islands = records(context)
    for _, bm, uv, faces, _, uid in islands:
        if uid == self.uid:
            attr = bm.faces.layers.float.get('gm_size_' + uv.name)
            for face in faces:
                if face[attr] <= 0:
                    face[attr] = _perimeter(face, uv)
    changed = set()
    for group in stack_groups(islands, {self.uid}):
        for i, coordinates in group[1:]:
            mesh, _, uv, _, loops, _ = islands[i]
            for loop, p in zip(loops, coordinates):
                loop[uv].uv = (p.real, p.imag)
            changed.add(mesh)
    for mesh in changed:
        bmesh.update_edit_mesh(mesh, loop_triangles=False, destructive=False)
    context.scene.gm_uvs_pack_result = ''
    _overlay_sources.clear()
    redraw_uvs()


class GMUVS_PG_pack_layer(bpy.types.PropertyGroup):
    name: StringProperty(name="Name", default="Layer")
    uid: IntProperty()
    visible: BoolProperty(name='Layer Visibility', description='Show/hide assigned faces in Edit Mode and exclude hidden islands from packing', default=True, update=layer_visibility)
    color: FloatVectorProperty(name='Layer Color', subtype='COLOR', size=3,
                              min=0, max=1, default=(0.2, 0.65, 1.0), update=redraw_uvs)
    max_scale: FloatProperty(name="Scale Limit", description="Preview and maximum packed scale relative to the original island size; 1 restores original size", default=1.0, min=0.001, max=1000, update=preview_layer_scale)
    stack_matching: BoolProperty(name='Stack Matching Islands', description='Overlay matching UV polygon layouts in this layer, allowing rotation and uniform scaling; keep stacks together when packing', default=False, update=_stack_layer)


def records(context):
    result = []
    for obj in context.objects_in_mode_unique_data:
        if obj.type != 'MESH':
            continue
        bm = bmesh.from_edit_mesh(obj.data)
        uv = bm.loops.layers.uv.active
        if uv is None:
            continue
        # Each UV map has independent face assignments, retained in the blend file.
        key = 'gm_pack_' + uv.name
        layer = bm.faces.layers.int.get(key)
        for faces in _uv_island_faces(bm, uv):
            loops = [loop for face in faces for loop in face.loops]
            ids = {face[layer] for face in faces} if layer else {0}
            result.append((obj.data, bm, uv, faces, loops, ids.pop() if len(ids) == 1 else 0))
    return result


def arrange(sizes, factor, margin, rotate):
    """MaxRects placement. Return placements only when every box fits."""
    free = [(margin, margin, 1 - 2 * margin, 1 - 2 * margin)]
    placed = {}
    scaled = [(i, w * min(factor, cap), h * min(factor, cap)) for i, (w, h, cap) in enumerate(sizes)]
    for i, w, h in sorted(scaled, key=lambda item: max(item[1:]), reverse=True):
        candidates = []
        for x, y, fw, fh in free:
            for turn in range(2 if rotate else 1):
                a, b = (h, w) if turn else (w, h)
                a += margin
                b += margin
                if a <= fw + 1e-12 and b <= fh + 1e-12:
                    candidates.append((min(fw-a, fh-b), max(fw-a, fh-b), x, y, a, b, turn))
        if not candidates:
            return None
        _, _, x, y, a, b, turn = min(candidates)
        placed[i] = (x, y, bool(turn), min(factor, sizes[i][2]))
        remaining = []
        for fx, fy, fw, fh in free:
            if x >= fx+fw or x+a <= fx or y >= fy+fh or y+b <= fy:
                remaining.append((fx, fy, fw, fh))
                continue
            if x > fx:
                remaining.append((fx, fy, x-fx, fh))
            if x+a < fx+fw:
                remaining.append((x+a, fy, fx+fw-x-a, fh))
            if y > fy:
                remaining.append((fx, fy, fw, y-fy))
            if y+b < fy+fh:
                remaining.append((fx, y+b, fw, fy+fh-y-b))
        free = [r for j, r in enumerate(remaining) if not any(
            k != j and s[0] <= r[0] and s[1] <= r[1]
            and s[0]+s[2] >= r[0]+r[2] and s[1]+s[3] >= r[1]+r[3]
            and (s != r or k < j) for k, s in enumerate(remaining))]
    return placed


class GMUVS_OT_pack_layer(bpy.types.Operator):
    bl_idname = 'uv.gm_uvs_pack_layer'
    bl_label = 'UV Packing Layer'
    bl_options = {'REGISTER', 'UNDO'}
    action: StringProperty()
    layer_uid: IntProperty(default=0, options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return is_uv_edit_mode(context)

    def execute(self, context):
        scene = context.scene
        layers = scene.gm_uvs_pack_layers
        index = scene.gm_uvs_pack_layer_index
        if self.layer_uid:
            index = next((i for i, item in enumerate(layers) if item.uid == self.layer_uid), -1)
        if self.action == 'ADD':
            item = layers.add()
            item.name = f'Layer {len(layers)}'
            item.uid = uuid.uuid4().int % 2147483646 + 1
            item.color = colorsys.hsv_to_rgb(((len(layers)-1) * 0.618034 + .55) % 1, .7, 1)
            scene.gm_uvs_pack_layer_index = len(layers)-1
            return {'FINISHED'}
        if not layers or not 0 <= index < len(layers):
            return {'CANCELLED'}
        scene.gm_uvs_pack_layer_index = index
        if self.action in {'UP', 'DOWN'}:
            target = index + (-1 if self.action == 'UP' else 1)
            if not 0 <= target < len(layers):
                return {'CANCELLED'}
            layers.move(index, target)
            scene.gm_uvs_pack_layer_index = target
            redraw_uvs()
            return {'FINISHED'}
        uid = layers[index].uid
        if self.action in {'SELECT', 'REMOVE'} and not layers[index].visible:
            layers[index].visible = True
        if self.action == 'SELECT':
            islands = records(context)
            sync = scene.tool_settings.use_uv_select_sync
            meshes = {mesh: bm for mesh, bm, *_ in islands}
            if sync:
                for bm in meshes.values():
                    for face in bm.faces:
                        face.select_set(False)
                    for edge in bm.edges:
                        edge.select_set(False)
                    for vert in bm.verts:
                        vert.select_set(False)
            count = 0
            for mesh, bm, uv, faces, loops, assigned in islands:
                selected = assigned == uid
                count += int(selected)
                for face in faces:
                    if sync:
                        face.select_set(selected)
                    elif selected:
                        # UVs on unselected mesh faces are otherwise invisible.
                        face.select_set(True)
                    face.uv_select = selected
                for loop in loops:
                    loop.uv_select_vert = selected
                    loop.uv_select_edge = selected
            for mesh, bm in meshes.items():
                if sync:
                    bm.select_flush_mode()
                    # Blender 5 transforms must use the explicit UV selection.
                    # Rebuilding it from shared mesh vertices loses seam corners.
                    bm.uv_select_sync_valid = True
                bmesh.update_edit_mesh(mesh, loop_triangles=False, destructive=False)
            redraw_uvs()
            self.report({'INFO'}, f'{count} layer islands selected')
            return {'FINISHED'}
        # Adding custom data invalidates existing BMFace/BMLoop wrappers.
        # Create all attributes before collecting selection or island references.
        if self.action in {'ASSIGN', 'UNASSIGN'}:
            _ensure_original_sizes(context)
            for obj in context.objects_in_mode_unique_data:
                if obj.type != 'MESH':
                    continue
                bm = bmesh.from_edit_mesh(obj.data)
                uv = bm.loops.layers.uv.active
                if uv and bm.faces.layers.int.get('gm_pack_' + uv.name) is None:
                    bm.faces.layers.int.new('gm_pack_' + uv.name)
        selected = {loop for _, _, _, loops in selected_uvs(context) for loop in loops}
        count = 0
        for mesh, bm, uv, faces, loops, _ in records(context):
            attr = bm.faces.layers.int.get('gm_pack_' + uv.name)
            if self.action == 'REMOVE':
                if attr:
                    for face in faces:
                        if face[attr] == uid:
                            face[attr] = 0
            elif any(loop in selected for loop in loops):
                for face in faces:
                    face[attr] = uid if self.action == 'ASSIGN' else 0
                if self.action == 'ASSIGN':
                    _preview_island(bm, uv, faces, loops, layers[index].max_scale)
                count += 1
            bmesh.update_edit_mesh(mesh, loop_triangles=False, destructive=False)
        if self.action == 'REMOVE':
            layers.remove(index)
            scene.gm_uvs_pack_layer_index = max(0, min(index, len(layers)-1))
        else:
            self.report({'INFO'}, f'{count} islands updated')
            if self.action == 'ASSIGN' and layers[index].stack_matching:
                _stack_layer(layers[index], context)
            if self.action == 'ASSIGN' and not layers[index].visible:
                layer_visibility(layers[index], context)
        redraw_uvs()
        return {'FINISHED'}


class GMUVS_OT_pack(bpy.types.Operator):
    bl_idname = 'uv.gm_uvs_pack'
    bl_label = 'Pack UVs & Measure Coverage'
    bl_description = 'Pack all visible UV islands of edited meshes into the 0-1 tile with layer scale limits'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return is_uv_edit_mode(context)

    def execute(self, context):
        scene = context.scene
        _ensure_original_sizes(context)
        islands = records(context)
        if not islands:
            self.report({'WARNING'}, 'No visible UV islands')
            return {'CANCELLED'}
        caps = {item.uid: item.max_scale for item in scene.gm_uvs_pack_layers}
        for _, bm, uv, faces, _, uid in islands:
            if uid in caps:
                attr = bm.faces.layers.float.get('gm_size_' + uv.name)
                for face in faces:
                    if face[attr] <= 0:
                        face[attr] = _perimeter(face, uv)
        groups = stack_groups(islands, {item.uid for item in scene.gm_uvs_pack_layers if item.stack_matching})
        bounds, sizes = [], []
        for group in groups:
            _, bm, uv, faces, loops, uid = islands[group[0][0]]
            coords = [loop[uv].uv.copy() for loop in loops]
            x, y = min(p.x for p in coords), min(p.y for p in coords)
            w, h = max(p.x for p in coords)-x, max(p.y for p in coords)-y
            # Preview has already applied the limit. Pack from original size so
            # the limit is absolute and repeated packing cannot compound it.
            factor = _original_factor(bm, uv, faces) if uid in caps else 1.0
            if uid in caps:
                coords = [coords[0] + (p-coords[0])/factor for p in coords]
                x, y = min(p.x for p in coords), min(p.y for p in coords)
                w, h = max(p.x for p in coords)-x, max(p.y for p in coords)-y
            bounds.append((x, y, h, coords, factor, coords[0].copy()))
            sizes.append((max(w, 1e-9), max(h, 1e-9), caps.get(uid, 1.0)))
        low, high = 0.0, max(size[2] for size in sizes)
        best = arrange(sizes, high, scene.gm_uvs_pack_margin, scene.gm_uvs_pack_rotate)
        if best is None:
            for _ in range(40):
                mid = (low+high)/2
                attempt = arrange(sizes, mid, scene.gm_uvs_pack_margin, scene.gm_uvs_pack_rotate)
                if attempt is None:
                    high = mid
                else:
                    low, best = mid, attempt
        if best is None or max(p[3] for p in best.values()) < 1e-8:
            self.report({'WARNING'}, 'Margin too large for this many islands; reduce it')
            return {'CANCELLED'}
        area = 0.0
        for i, group in enumerate(groups):
            mesh, bm, uv, faces, loops, uid = islands[group[0][0]]
            x, y, turn, scale = best[i]
            ox, oy, height, coords, original_factor, anchor = bounds[i]
            for loop, p in zip(loops, coords):
                u, v = p.x-ox, p.y-oy
                if turn:
                    u, v = height-v, u
                loop[uv].uv = (x+u*scale, y+v*scale)
            # Apply the same packed transform to every aligned member.
            for member, aligned in group[1:]:
                other_mesh, _, other_uv, _, other_loops, _ = islands[member]
                for loop, p in zip(other_loops, aligned):
                    u = anchor.x+(p.real-anchor.x)/original_factor-ox
                    v = anchor.y+(p.imag-anchor.y)/original_factor-oy
                    if turn:
                        u, v = height-v, u
                    loop[other_uv].uv = (x+u*scale, y+v*scale)
                bmesh.update_edit_mesh(other_mesh, loop_triangles=False, destructive=False)
            for face in faces:
                points = [loop[uv].uv for loop in face.loops]
                area += abs(sum(a.x*b.y-b.x*a.y for a, b in zip(points, points[1:]+points[:1]))) / 2
            bmesh.update_edit_mesh(mesh, loop_triangles=False, destructive=False)
        scene.gm_uvs_pack_coverage = area * 100
        scene.gm_uvs_pack_result = f'{len(islands)} islands | UV coverage: {area*100:.2f}%'
        self.report({'INFO'}, scene.gm_uvs_pack_result)
        return {'FINISHED'}


class GMUVS_UL_pack_layers(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        op = row.operator('uv.gm_uvs_pack_layer', text='', icon='RESTRICT_SELECT_OFF', emboss=False)
        op.action = 'SELECT'
        op.layer_uid = item.uid
        # Standard UIList name property supports native double-click renaming.
        row.prop(item, 'name', text='', emboss=False)
        row.prop(item, 'color', text='')
        row.prop(item, 'visible', text='', emboss=False,
                 icon='HIDE_OFF' if item.visible else 'HIDE_ON')


CLASSES = (GMUVS_PG_pack_layer, GMUVS_OT_pack_layer, GMUVS_OT_pack, GMUVS_UL_pack_layers)


def register_properties():
    bpy.types.Scene.gm_uvs_pack_layers = CollectionProperty(type=GMUVS_PG_pack_layer)
    bpy.types.Scene.gm_uvs_pack_layer_index = IntProperty(default=0, min=0)
    bpy.types.Scene.gm_uvs_pack_margin = FloatProperty(name='Margin', default=0.005, min=0, max=0.1, precision=4)
    bpy.types.Scene.gm_uvs_pack_rotate = BoolProperty(name='Allow 90° Rotation', default=True)
    bpy.types.Scene.gm_uvs_pack_coverage = FloatProperty(default=0)
    bpy.types.Scene.gm_uvs_pack_result = StringProperty(default='')
    bpy.types.Scene.gm_uvs_pack_show_colors = BoolProperty(name='Show Layer Colors', default=True, update=redraw_uvs)
    register_overlay()


def unregister_properties():
    unregister_overlay()
    for name in ('layers', 'layer_index', 'margin', 'rotate', 'coverage', 'result', 'show_colors'):
        delattr(bpy.types.Scene, 'gm_uvs_pack_' + name)


_overlay_handler = None
_overlay_shader = None
_overlay_sources = {}
_overlay_cache = {}
_overlay_batches = {}
_overlay_revision = 0


@persistent
def _overlay_history_changed(*args):
    _overlay_sources.clear()
    _overlay_cache.clear()
    _overlay_batches.clear()


@persistent
def _overlay_mesh_updated(scene, depsgraph):
    global _overlay_revision
    if any(update.is_updated_geometry and isinstance(update.id, (bpy.types.Mesh, bpy.types.Object))
           for update in depsgraph.updates):
        _overlay_revision += 1


def _overlay_key(context):
    window = context.window
    area = getattr(context, 'area', None)
    return (window.as_pointer() if window else 0, area.as_pointer() if area else 0)


def _overlay_visibility(source, sync):
    # Native mesh selection changes do not always send geometry updates. Read
    # only inexpensive face flags here; never scan adjacency or UV coordinates.
    return bytes(bm.is_valid and face.is_valid and not face.hide and (sync or face.select)
                 for bm, face, *_ in source)


def _overlay_modal_is_safe(operator):
    name = operator.bl_idname
    return (name.startswith('VIEW2D_OT_')
            or name in {'IMAGE_OT_view_pan', 'IMAGE_OT_view_zoom',
                        'TRANSFORM_OT_translate', 'TRANSFORM_OT_resize',
                        'TRANSFORM_OT_rotate', 'TRANSFORM_OT_shear'})


def overlay_geometry(context):
    """Cached UV-space geometry; navigation is handled by the GPU projection."""
    from mathutils import Vector
    from mathutils.geometry import tessellate_polygon
    colors = {item.uid: tuple(item.color) for item in context.scene.gm_uvs_pack_layers if item.visible}
    window = context.window
    key = _overlay_key(context)
    modal = tuple(window.modal_operators) if window else ()
    transforming = any(op.bl_idname.startswith('TRANSFORM_OT_') for op in modal)
    cached = _overlay_cache.get(key)
    if modal:
        # Navigation changes only the view; UV transforms change coordinates.
        # Both can reuse existing references without acquiring an edit BMesh.
        if not all(_overlay_modal_is_safe(op) for op in modal):
            return []
        source = _overlay_sources.get(key, ())
        if not source:
            return []
        # Navigation changes no UV coordinates. Transforms refresh at up to
        # 30 Hz instead of rebuilding large GPU buffers on every mouse event.
        if cached and (not transforming or perf_counter()-cached['time'] < 1/30):
            return [(colors[uid], lines, triangles) for uid, lines, triangles in cached['geometry'] if uid in colors]
    else:
        signature = (context.scene.as_pointer(), tuple((obj.data.as_pointer(), obj.data.uv_layers.active_index)
                           for obj in context.objects_in_mode_unique_data if obj.type == 'MESH'),
                     context.scene.tool_settings.use_uv_select_sync, tuple(colors))
        if (cached and key in _overlay_sources and cached['revision'] == _overlay_revision
                and cached['signature'] == signature
                and cached['visibility'] == _overlay_visibility(_overlay_sources[key], context.scene.tool_settings.use_uv_select_sync)):
            return [(colors[uid], lines, triangles) for uid, lines, triangles in cached['geometry'] if uid in colors]
        source = []
        # Coloring needs face assignments, not a fresh island adjacency search.
        for obj in context.objects_in_mode_unique_data:
            if obj.type != 'MESH':
                continue
            bm = bmesh.from_edit_mesh(obj.data)
            uv = bm.loops.layers.uv.active
            attr = bm.faces.layers.int.get('gm_pack_' + uv.name) if uv else None
            if attr is None:
                continue
            for face in bm.faces:
                uid = face[attr]
                if uid not in colors:
                    continue
                # Keep the BMesh alive and retain wrapped coordinates, not copies.
                coordinates = [loop[uv].uv for loop in face.loops]
                indices = tessellate_polygon([[Vector((*p, 0)) for p in coordinates]])
                source.append((bm, face, uid, coordinates, indices))
        _overlay_sources[key] = source
    geometry = {}
    for bm, face, uid, coordinates, indices in source:
        if uid not in colors or not bm.is_valid or not face.is_valid or face.hide:
            continue
        if not context.scene.tool_settings.use_uv_select_sync and not face.select:
            continue
        lines, triangles = geometry.setdefault(uid, ([], []))
        try:
            points = [tuple(p) for p in coordinates]
            for a, b in zip(points, points[1:]+points[:1]):
                lines.extend((a, b))
            triangles.extend(points[i] for tri in indices for i in tri)
        except ReferenceError:
            _overlay_sources.pop(key, None)
            _overlay_cache.pop(key, None)
            return []
    geometry = [(uid, lines, triangles) for uid, (lines, triangles) in geometry.items()]
    _overlay_cache[key] = dict(geometry=geometry, revision=-1 if modal else _overlay_revision,
                              signature=None if modal else signature, time=perf_counter(),
                              visibility=None if modal else _overlay_visibility(source, context.scene.tool_settings.use_uv_select_sync))
    _overlay_batches.pop(key, None)
    return [(colors[uid], lines, triangles) for uid, lines, triangles in geometry]


def draw_layer_colors():
    global _overlay_shader
    context = bpy.context
    if not is_uv_edit_mode(context) or not context.scene.gm_uvs_pack_show_colors:
        return
    import gpu
    from gpu_extras.batch import batch_for_shader
    geometry = overlay_geometry(context)
    if not geometry:
        return
    if _overlay_shader is None:
        _overlay_shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    shader = _overlay_shader
    key = _overlay_key(context)
    cache = _overlay_cache.get(key)
    prepared = _overlay_batches.get(key)
    if prepared is None or prepared['geometry'] is not cache:
        colors = {item.uid: tuple(item.color) for item in context.scene.gm_uvs_pack_layers if item.visible}
        batches = []
        if cache:
            for uid, lines, triangles in cache['geometry']:
                if uid in colors:
                    batches.append((uid,
                        batch_for_shader(shader, 'LINES', {'pos': lines}) if lines else None,
                        batch_for_shader(shader, 'TRIS', {'pos': triangles}) if triangles else None))
        prepared = _overlay_batches[key] = dict(geometry=cache, batches=batches)
    colors = {item.uid: tuple(item.color) for item in context.scene.gm_uvs_pack_layers if item.visible}
    blend = gpu.state.blend_get()
    try:
        gpu.state.blend_set('ALPHA')
        for uid, lines, triangles in prepared['batches']:
            if uid not in colors:
                continue
            color = colors[uid]
            shader.bind()
            if triangles:
                shader.uniform_float('color', (*color, .16))
                triangles.draw(shader)
            if lines:
                shader.uniform_float('color', (*color, .85))
                lines.draw(shader)
    finally:
        gpu.state.blend_set(blend)


def register_overlay():
    global _overlay_handler
    if _overlay_mesh_updated not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_overlay_mesh_updated)
    for handlers in (bpy.app.handlers.load_post, bpy.app.handlers.undo_post, bpy.app.handlers.redo_post):
        if _overlay_history_changed not in handlers:
            handlers.append(_overlay_history_changed)
    if not bpy.app.background and _overlay_handler is None:
        _overlay_handler = bpy.types.SpaceImageEditor.draw_handler_add(
            draw_layer_colors, (), 'WINDOW', 'POST_VIEW')


def unregister_overlay():
    global _overlay_handler, _overlay_shader
    if _overlay_mesh_updated in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_overlay_mesh_updated)
    for handlers in (bpy.app.handlers.load_post, bpy.app.handlers.undo_post, bpy.app.handlers.redo_post):
        if _overlay_history_changed in handlers:
            handlers.remove(_overlay_history_changed)
    if _overlay_handler is not None:
        bpy.types.SpaceImageEditor.draw_handler_remove(_overlay_handler, 'WINDOW')
        _overlay_handler = None
    _overlay_shader = None
    _overlay_sources.clear()
    _overlay_cache.clear()
    _overlay_batches.clear()
    redraw_uvs()
