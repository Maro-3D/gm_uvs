# SPDX-FileCopyrightText: 2026 Oxicid
# SPDX-License-Identifier: GPL-3.0-or-later

import math
import copy
from mathutils import Vector
from bmesh.types import BMLoop, BMLayerItem


class BBox:
    @classmethod
    def calc_bbox(cls, coords):
        xmin = math.inf
        xmax = -math.inf
        ymin = math.inf
        ymax = -math.inf

        for x, y in coords:
            if xmin > x:
                xmin = x
            if xmax < x:
                xmax = x
            if ymin > y:
                ymin = y
            if ymax < y:
                ymax = y
        return cls(xmin, xmax, ymin, ymax)

    @classmethod
    def calc_bbox_uv(cls, group, uv):
        xmin = math.inf
        xmax = -math.inf
        ymin = math.inf
        ymax = -math.inf

        for face in group:
            for loop in face.loops:
                x, y = loop[uv].uv
                if xmin > x:
                    xmin = x
                if xmax < x:
                    xmax = x
                if ymin > y:
                    ymin = y
                if ymax < y:
                    ymax = y

        return cls(xmin, xmax, ymin, ymax)

    @classmethod
    def calc_bbox_with_extrema_corners(cls, corners, uv: BMLayerItem) -> 'tuple[BBox, tuple[BMLoop, ...]]':
        xmin = math.inf
        xmax = -math.inf
        ymin = math.inf
        ymax = -math.inf
        xmin_crn = xmax_crn = ymin_crn = ymax_crn = corners[0]
        for crn in corners:
            x, y = crn[uv].uv
            if x < xmin:
                xmin = x
                xmin_crn = crn
            if x > xmax:
                xmax = x
                xmax_crn = crn
            if y < ymin:
                ymin = y
                ymin_crn = crn
            if y > ymax:
                ymax = y
                ymax_crn = crn

        return cls(xmin, xmax, ymin, ymax), (xmin_crn, xmax_crn, ymin_crn, ymax_crn)


    @classmethod
    def calc_bbox_uv_corners(cls, group, uv):
        xmin = math.inf
        xmax = -math.inf
        ymin = math.inf
        ymax = -math.inf

        for loop in group:
            x, y = loop[uv].uv
            if xmin > x:
                xmin = x
            if xmax < x:
                xmax = x
            if ymin > y:
                ymin = y
            if ymax < y:
                ymax = y
        return cls(xmin, xmax, ymin, ymax)


    def __init__(
            self,
            xmin: float = math.inf,
            xmax: float = -math.inf,
            ymin: float = math.inf,
            ymax: float = -math.inf):
        self.xmin = xmin
        self.xmax = xmax
        self.ymin = ymin
        self.ymax = ymax

    def __str__(self):
        return f"xmin={self.xmin:.6}, xmax={self.xmax:.6}, ymin={self.ymin:.6}, ymax={self.ymax:.6}, width={self.width:.6}, height={self.height:.6}"

    def __repr__(self):
        return str(self)


    @property
    def max(self):
        return Vector((self.xmax, self.ymax))

    @max.setter
    def max(self, val: Vector):
        self.xmax, self.ymax = val

    @property
    def min(self):
        return Vector((self.xmin, self.ymin))

    @min.setter
    def min(self, val: Vector):
        self.xmin, self.ymin = val


    @property
    def bottom(self):
        return Vector(((self.xmin + self.xmax) * 0.5, self.ymin))

    @property
    def left(self):
        return Vector((self.xmin, (self.ymin + self.ymax) * 0.5))

    @property
    def right(self):
        return Vector((self.xmax, (self.ymin + self.ymax) * 0.5))

    @property
    def center(self):
        return Vector(((self.xmin + self.xmax) * 0.5, (self.ymin + self.ymax) * 0.5))


    @center.setter
    def center(self, new_center):
        delta = new_center - self.center
        self.move(delta)

    def move(self, delta):
        x, y = delta
        self.xmin += x
        self.xmax += x
        self.ymin += y
        self.ymax += y


    @property
    def width(self) -> float:
        return self.xmax - self.xmin

    @property
    def height(self) -> float:
        return self.ymax - self.ymin

    @property
    def max_length(self):
        return max(self.width, self.height)

    @property
    def min_length(self):
        return min(self.width, self.height)


    @property
    def area(self):
        return self.width * self.height


    def union(self, other):
        if self.xmin > other.xmin:
            self.xmin = other.xmin
        if self.xmax < other.xmax:
            self.xmax = other.xmax
        if self.ymin > other.ymin:
            self.ymin = other.ymin
        if self.ymax < other.ymax:
            self.ymax = other.ymax
        return self


    def add(self, co):
        x, y = co
        if self.xmin > x:
            self.xmin = x
        if self.xmax < x:
            self.xmax = x
        if self.ymin > y:
            self.ymin = y
        if self.ymax < y:
            self.ymax = y

    def clamp(self, xmin=0, ymin=0, xmax=1, ymax=1):
        if self.xmin < xmin:
            self.xmin = xmin
        if self.ymin < ymin:
            self.ymin = ymin
        if self.xmax > xmax:
            self.xmax = xmax
        if self.ymax > ymax:
            self.ymax = ymax


    def set_position(self, pos):
        x, y = pos
        self.xmax -= self.xmin - x
        self.ymax -= self.ymin - y
        self.xmin = x
        self.ymin = y


    def scale(self, scale: Vector | float, pivot: Vector | tuple[float, float] | None = None):
        center = self.center if pivot is None else pivot
        self.xmin, self.ymin = (self.min - center) * scale + center
        self.xmax, self.ymax = (self.max - center) * scale + center


    def update(self, coords):
        xmin = self.xmin
        ymin = self.ymin
        xmax = self.xmax
        ymax = self.ymax

        for x, y in coords:
            if x < xmin:
                xmin = x
            if x > xmax:
                xmax = x
            if y < ymin:
                ymin = y
            if y > ymax:
                ymax = y

        self.xmin = xmin
        self.ymin = ymin
        self.xmax = xmax
        self.ymax = ymax


    def distance(self, pt: Vector | tuple[float, float], aspect_y=1.0, with_center=False) -> float:
        """Return minimal distance to bounds"""
        x, y = pt
        y *= aspect_y

        xmin = self.xmin
        xmax = self.xmax
        ymin = self.ymin * aspect_y
        ymax = self.ymax * aspect_y

        dx = max(xmin - x, 0.0, x - xmax)
        dy = max(ymin - y, 0.0, y - ymax)

        if dx == 0.0 and dy == 0.0:
            # Inner
            if with_center:
                center = Vector((xmin+xmax, ymin+ymax))
                center *= 0.5
                dist_to_center = (Vector((x, y)) - center).length

                return min(
                    x - xmin,
                    xmax - x,
                    y - ymin,
                    ymax - y,
                    dist_to_center
                )
            else:
                return min(
                    x - xmin,
                    xmax - x,
                    y - ymin,
                    ymax - y,
                )

        # Outer
        return (dx * dx + dy * dy) ** 0.5


    def isect(self, other: 'BBox') -> 'BBox | None':
        xmin = self.xmin if (self.xmin > other.xmin) else other.xmin
        xmax = self.xmax if (self.xmax < other.xmax) else other.xmax
        ymin = self.ymin if (self.ymin > other.ymin) else other.ymin
        ymax = self.ymax if (self.ymax < other.ymax) else other.ymax

        if xmax >= xmin and ymax >= ymin:
            return BBox(xmin, xmax, ymin, ymax)
        return None


    @property
    def aspect(self):
        min_length = self.min_length

        if not min_length:
            return 0.0
        return self.max_length / min_length


    def copy(self):
        return copy.copy(self)

    def __contains__(self, pt_or_bbox) -> bool:
        if isinstance(pt_or_bbox, BBox):
            bbox = pt_or_bbox
            return (self.xmin <= bbox.xmin) and (self.xmax >= bbox.xmax) and \
                   (self.ymin <= bbox.ymin) and (self.ymax >= bbox.ymax)  # noqa

        x, y = pt_or_bbox
        return self.xmin <= x <= self.xmax and \
               self.ymin <= y <= self.ymax  # noqa

    def __eq__(self, other: 'BBox'):
        if not isinstance(other, BBox):
            return NotImplemented
        return self.min == other.min and self.max == other.max

    def __hash__(self):
        return hash(self.xmin + self.ymin + self.xmax + self.ymax)

    def __and__(self, other: 'BBox'):
        return self.isect(other)

    def __or__(self, other: 'BBox'):
        return self.union(other)
