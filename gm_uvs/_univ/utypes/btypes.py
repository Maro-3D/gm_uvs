# SPDX-FileCopyrightText: 2026 Oxicid
# SPDX-License-Identifier: GPL-3.0-or-later

# Everything that happens below is thanks to the K-410
# The code was taken and modified from the 'btypes' module: https://github.com/K-410/btypes/tree/fafc510bd9de3aa3201edf5ad9bced26a5298bc0

import bpy
import typing
from ctypes import POINTER, Union, Structure, c_float, c_short, c_int, c_long, c_char, c_void_p, c_bool

from . import bbox

version = bpy.app.version
bpy_struct_subclass = typing.TypeVar('bpy_struct_subclass', bound=bpy.types.bpy_struct)


class PyObject_HEAD(Structure):
    _fields_ = (("ob_refcnt", c_long),
                ("ob_type", c_void_p)
                )

class PyObject_VAR_HEAD(Structure):
    _fields_ = (("ob_refcnt", c_long),
                ("ob_type", c_void_p),
                ("ob_size", c_long)
                )


class StructBase(Structure):
    _subclasses = []
    __annotations__ = {}

    def __init_subclass__(cls):
        cls._subclasses.append(cls)

    def __new__(cls, srna: bpy_struct_subclass | None =None):
        if srna is None:
            return super().__new__(cls)
        try:
            return cls.from_address(srna.as_pointer())
        except AttributeError:
            raise Exception("Not a StructRNA instance")

    # Required
    def __init__(self, *_):  # noqa
        pass

    @staticmethod
    def _init_structs():
        """ Initialize subclasses, converting annotations to fields. """
        functype = type(lambda: None)

        for cls in StructBase._subclasses:
            fields = []
            anons = []
            for key, value in cls.__annotations__.items():
                if isinstance(value, functype):
                    value = value()
                elif isinstance(value, Union):
                    anons.append(key)
                fields.append((key, value))

            if anons:
                cls._anonynous_ = anons

            if fields:  # Base classes might not have _fields_. Don't set anything.
                cls._fields_ = fields
            cls.__annotations__.clear()

        StructBase._subclasses.clear()


class rctf(StructBase, bbox.BBox):
    xmin: c_float
    xmax: c_float
    ymin: c_float
    ymax: c_float


class rcti(StructBase, bbox.BBox):
    xmin: c_int
    xmax: c_int
    ymin: c_int
    ymax: c_int

    def __str__(self):
        return f"xmin={self.xmin}, xmax={self.xmax}, ymin={self.ymin}, ymax={self.ymax}, width={self.width}, height={self.height}"


class View2D(StructBase):
    tot: rctf
    cur: rctf
    vert: rcti
    hor: rcti
    mask: rcti

    min: c_float * 2  # noqa
    max: c_float * 2  # noqa

    minzoom: c_float
    maxzoom: c_float

    scroll: c_short
    scroll_ui: c_short

    keeptot: c_short
    keepzoom: c_short
    keepofs: c_short

    flag: c_short
    align: c_short

    winx: c_short
    winy: c_short
    oldwinx: c_short
    oldwiny: c_short

    around: c_short

    alpha_vert: c_char
    alpha_hor: c_char

    _pad6: c_char * 6  # noqa

    sms: c_void_p  # SmoothView2DStore
    smooth_timer: c_void_p  # wmTimer


    @classmethod
    def get_zoom(cls, view):
        v2d = cls.from_address(view.as_pointer())
        return (v2d.mask.xmax - v2d.mask.xmin) / (v2d.cur.xmax - v2d.cur.xmin)  # noqa
class CustomDataLayer(StructBase):
    type: c_int
    offset: c_int
    flag: c_int
    active: c_int
    active_rnd: c_int

    if version < (5, 1, 0):
        active_clone: c_int
        active_mask: c_int

    uid: c_int
    if version >= (3, 5, 0):
        name: c_char * 68
        _pad1: c_char * 4
    else:
        name: c_char * 64
    data: c_void_p

    sharing_info: c_void_p
class CustomData(StructBase):
    layers: lambda: POINTER(CustomDataLayer)

    if version >= (3, 4, 0):
        typemap: c_int * 53
    else:
        if version >= (3, 2, 0):
            typemap: c_int * 52
        else:
            typemap: c_int * 50
        _pad1: c_char * 4

    totlayer: c_int
    maxlayer: c_int

    totsize: c_int

    pool: c_void_p
    external: c_void_p


class CBMesh(StructBase):
    totvert: c_int
    totedge: c_int
    totloop: c_int
    totface: c_int
    totvertsel: c_int
    totedgesel: c_int
    totfacesel: c_int

    elem_index_dirty: c_char

    vpool: c_void_p
    epool: c_void_p
    lpool: c_void_p
    fpool: c_void_p

    vtable: c_void_p
    etable: c_void_p
    ftable: c_void_p

    vtable_tot: c_int
    etable_tot: c_int
    ftable_tot: c_int

    vtoolflagpool: c_void_p
    etoolflagpool: c_void_p
    ftoolflagpool: c_void_p

    use_toolflags: c_bool

    if version >= (5, 0, 0):
        uv_select_sync_valid: c_bool

    toolflag_index: c_int

    vdata: CustomData
    edata: CustomData
    ldata: CustomData
    pdata: CustomData


class PyBMesh(StructBase):
    # Cleanup: use PyObject_HEAD for fixed-size types: https://projects.blender.org/blender/blender/pulls/155741
    if version >= (5, 2, 0):
        pyhead: PyObject_HEAD
    else:
        pyhead: PyObject_VAR_HEAD
    bm: POINTER(CBMesh)


    @classmethod
    def fields(cls, bm):
        c_bm = cls.from_address(id(bm))
        # print(ctypes.c_void_p.from_address(c_bm.bm.contents))  # get address by int
        # ctypes.addressof(c_bm.bm.contents)
        return c_bm.bm.contents

    @classmethod
    def is_full_face_selected(cls, bm):
        bm = cls.fields(bm)
        if bm.totfacesel:
            return bm.totfacesel == bm.totface
        return False

    @classmethod
    def is_full_face_deselected(cls, bm):
        return cls.fields(bm).totfacesel == 0


    @classmethod
    def is_full_edge_deselected(cls, bm):
        return cls.fields(bm).totedgesel == 0


    @classmethod
    def is_full_vert_deselected(cls, bm):
        return cls.fields(bm).totvertsel == 0

    @classmethod
    def total_face_sel(cls, bm):
        return cls.fields(bm).totfacesel

    @classmethod
    def total_edge_sel(cls, bm):
        return cls.fields(bm).totedgesel

    @classmethod
    def total_vert_sel(cls, bm):
        return cls.fields(bm).totvertsel


StructBase._init_structs()  # noqa
