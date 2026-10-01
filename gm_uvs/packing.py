"""Persistent island groups and bounded, deterministic single-tile packing."""
import uuid
import colorsys

import bpy
import bmesh
from bpy.props import CollectionProperty, FloatProperty, FloatVectorProperty, IntProperty, StringProperty, BoolProperty
from .transform import is_uv_edit_mode, selected_uvs, _uv_island_faces


def redraw_uvs(self=None, context=None):
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'IMAGE_EDITOR':
                area.tag_redraw()


class GMUVS_PG_pack_layer(bpy.types.PropertyGroup):
    name: StringProperty(name="Name", default="Layer")
    uid: IntProperty()
    color: FloatVectorProperty(name='Layer Color', subtype='COLOR', size=3,
                              min=0, max=1, default=(0.2, 0.65, 1.0), update=redraw_uvs)
    max_scale: FloatProperty(name="Scale Limit", description="Maximum linear scale relative to UVs before this pack (1 = no enlargement)", default=1.0, min=0.001, max=1000)


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
        uid = layers[index].uid
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
                count += 1
            bmesh.update_edit_mesh(mesh, loop_triangles=False, destructive=False)
        if self.action == 'REMOVE':
            layers.remove(index)
            scene.gm_uvs_pack_layer_index = max(0, min(index, len(layers)-1))
        else:
            self.report({'INFO'}, f'{count} islands updated')
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
        islands = records(context)
        if not islands:
            self.report({'WARNING'}, 'No visible UV islands')
            return {'CANCELLED'}
        caps = {item.uid: item.max_scale for item in scene.gm_uvs_pack_layers}
        bounds, sizes = [], []
        for _, _, uv, _, loops, uid in islands:
            coords = [loop[uv].uv.copy() for loop in loops]
            x, y = min(p.x for p in coords), min(p.y for p in coords)
            w, h = max(p.x for p in coords)-x, max(p.y for p in coords)-y
            bounds.append((x, y, h, coords))
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
        for i, (mesh, bm, uv, faces, loops, _) in enumerate(islands):
            x, y, turn, scale = best[i]
            ox, oy, height, coords = bounds[i]
            for loop, p in zip(loops, coords):
                u, v = p.x-ox, p.y-oy
                if turn:
                    u, v = height-v, u
                loop[uv].uv = (x+u*scale, y+v*scale)
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
        layout.prop(item, 'name', text='', emboss=False, icon='GROUP')
        layout.prop(item, 'color', text='')
        op = layout.operator('uv.gm_uvs_pack_layer', text='', icon='RESTRICT_SELECT_OFF')
        op.action = 'SELECT'
        op.layer_uid = item.uid


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


def _overlay_modal_is_safe(operator):
    name = operator.bl_idname
    return (name.startswith('VIEW2D_OT_')
            or name in {'IMAGE_OT_view_pan', 'IMAGE_OT_view_zoom',
                        'TRANSFORM_OT_translate', 'TRANSFORM_OT_resize',
                        'TRANSFORM_OT_rotate', 'TRANSFORM_OT_shear'})


def overlay_geometry(context):
    """Draw live UV references without acquiring edit BMeshes during transforms."""
    from mathutils import Vector
    from mathutils.geometry import tessellate_polygon
    colors = {item.uid: tuple(item.color) for item in context.scene.gm_uvs_pack_layers}
    geometry = {}
    view = context.region.view2d
    window = context.window
    area = getattr(context, 'area', None)
    key = (window.as_pointer() if window else 0,
           area.as_pointer() if area else 0)
    modal = tuple(window.modal_operators) if window else ()
    if modal:
        # Navigation changes only the view; UV transforms change coordinates.
        # Both can reuse existing references without acquiring an edit BMesh.
        if not all(_overlay_modal_is_safe(op) for op in modal):
            return []
        source = _overlay_sources.get(key, ())
    else:
        source = []
        for mesh, bm, uv, faces, _, uid in records(context):
            if uid not in colors:
                continue
            for face in faces:
                if not context.scene.tool_settings.use_uv_select_sync and not face.select:
                    continue
                # Keep the BMesh alive and retain wrapped coordinates, not copies.
                coordinates = [loop[uv].uv for loop in face.loops]
                indices = tessellate_polygon([[Vector((*p, 0)) for p in coordinates]])
                source.append((bm, face, uid, coordinates, indices))
        _overlay_sources[key] = source
    for bm, face, uid, coordinates, indices in source:
        if uid not in colors or not bm.is_valid or not face.is_valid:
            continue
        lines, triangles = geometry.setdefault(uid, ([], []))
        try:
            uv_points = [Vector((*p, 0)) for p in coordinates]
            points = [Vector(view.view_to_region(*p.xy, clip=False)) for p in uv_points]
            for a, b in zip(points, points[1:]+points[:1]):
                lines.extend((a.xy, b.xy))
            triangles.extend(points[i] for tri in indices for i in tri)
        except ReferenceError:
            _overlay_sources.pop(key, None)
            return []
    return [(colors[uid], lines, triangles) for uid, (lines, triangles) in geometry.items()]


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
    blend = gpu.state.blend_get()
    try:
        gpu.state.blend_set('ALPHA')
        for color, lines, triangles in geometry:
            shader.bind()
            if triangles:
                shader.uniform_float('color', (*color, .16))
                batch_for_shader(shader, 'TRIS', {'pos': triangles}).draw(shader)
            if lines:
                shader.uniform_float('color', (*color, .85))
                batch_for_shader(shader, 'LINES', {'pos': lines}).draw(shader)
    finally:
        gpu.state.blend_set(blend)


def register_overlay():
    global _overlay_handler
    if not bpy.app.background and _overlay_handler is None:
        _overlay_handler = bpy.types.SpaceImageEditor.draw_handler_add(
            draw_layer_colors, (), 'WINDOW', 'POST_PIXEL')


def unregister_overlay():
    global _overlay_handler, _overlay_shader
    if _overlay_handler is not None:
        bpy.types.SpaceImageEditor.draw_handler_remove(_overlay_handler, 'WINDOW')
        _overlay_handler = None
    _overlay_shader = None
    _overlay_sources.clear()
    redraw_uvs()
