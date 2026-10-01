"""Match UV polygon layouts by translation, rotation, and uniform scale."""


def _signature(polygons):
    result = []
    for polygon in polygons:
        points = [(round(p.real, 6), round(p.imag, 6)) for p in polygon]
        variants = [tuple(points[i:]+points[:i]) for i in range(len(points))]
        points.reverse()
        variants.extend(tuple(points[i:]+points[:i]) for i in range(len(points)))
        result.append(min(variants))
    return sorted(result)


def align_polygons(source, target):
    """Return aligned source coordinates only if every polygon matches.

    Face order and corner order need not match. Reflections are not generated.
    """
    if sorted(map(len, source)) != sorted(map(len, target)):
        return None
    edges = [(a, b) for poly in source for a, b in zip(poly, poly[1:]+poly[:1])]
    origin, end = max(edges, key=lambda edge: abs(edge[1]-edge[0]))
    delta = end-origin
    if abs(delta) < 1e-10:
        return None
    target_edges = [(a, b) for poly in target for a, b in zip(poly, poly[1:]+poly[:1])]
    longest = max(abs(b-a) for a, b in target_edges)
    signature = _signature(target)
    for a, b in target_edges:
        if abs(abs(b-a)-longest) > 1e-6:
            continue
        for start, finish in ((a, b), (b, a)):
            ratio = (finish-start)/delta
            aligned = [[start+(p-origin)*ratio for p in poly] for poly in source]
            if _signature(aligned) == signature:
                return [p for poly in aligned for p in poly]
    return None
