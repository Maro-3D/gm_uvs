# GM UVs (Game Makers UVs)

Blender 5.0+ UV Editor tools for game artists.

## Use

Open the UV Editing workspace, hover over the UV Editor, press **N**, and select **GM UVs**. Enter mesh Edit Mode and select UVs.

**Align UV Islands to Canvas** uses a compass layout:

```text
↖       ↑       ↗
←     — + |     →
↙       ↓       ↘
```

- Corner buttons move the corresponding corner of the selected UV layout to a corner of the 0–1 UV canvas. For example, ↙ moves the selected layout so its lower-left bound reaches (0, 0).
- Edge buttons move the selection to a canvas edge on one axis; the other axis stays where it is.
- The middle controls center the selection vertically (—), on both axes (+), or horizontally (|).

The add-on gathers UV loops and islands like UniV's alignment workflow. In vertex or edge selection it moves the selected UV loops. In face selection it includes the whole UV island containing each selected face. All affected UVs move by the same offset, preserving their shape and spacing. Unselected islands remain in place.

The **Gravity (Z)** button below the compass orients selected UV islands to the object's world-space direction, like UniV's Gravity tool. It preserves each island's center and works without UniV installed. The redo panel also offers X/Y axes, Flip, Additional Angle, and Correct Aspect.

The **UV Tools** box has native **Quadrify**, **Weld**, and **Weld by Distance** buttons. Quadrify turns connected selected quads into a rectangular UV grid; non-quad and unselected faces stay in place. The panel exposes **Mark Seams**, **Correct Aspect**, and **Scale Independently**, all enabled by default. Scale Independently balances U and V using the quads' 3D proportions, while Correct Aspect accounts for the active image dimensions; Mark Seams marks split UV boundaries. **Weld** now uses the bundled UniV 4.0.0 Weld implementation, including its Stitch fallback for separate UV islands, partial-edge welding, paired selection, and distance modes. It works without a separate UniV installation.

For alignment, the target is the 0–1 UV canvas. If the selection already touches an edge, that axis may not move. The status line below the buttons shows how many UV corners were found and the computed U/V offset. The operator supports UV Sync Selection, multi-object Edit Mode, and Undo. Other tool sections remain placeholders.

## Development

The development extension points to this repository's `gm_uvs` folder. Blender keeps loaded Python code in memory. After a source change, disable and re-enable GM UVs in Preferences > Get Extensions, or restart Blender. The current heading is **Align UV Islands to Canvas**.

Run the regression test with Blender:

```powershell
blender --background --factory-startup --python-exit-code 1 --python tests/test_align.py
blender --background --factory-startup --python-exit-code 1 --python tests/test_gravity.py
blender --background --factory-startup --python-exit-code 1 --python tests/test_quadrify.py
blender --background --factory-startup --python-exit-code 1 --python tests/test_weld.py
```

The alignment test uses a small UV cross inside the canvas, checks all eleven buttons with UV Sync on and off, checks whole-island movement from one selected face, and forces garbage collection between selection and movement to catch invalid BMesh loops.

The alignment and Gravity structures are adapted from [UniV's transform implementation](https://github.com/Oxicid/UniV/blob/main/operators/transform.py). Quadrify follows UniV's [Quadrify](https://github.com/Oxicid/UniV/blob/main/operators/quadrify.py) design. Weld bundles UniV's [original implementation](https://github.com/Oxicid/UniV/blob/main/operators/stitch_and_weld.py) and required core modules; see [VENDORED.md](gm_uvs/_univ/VENDORED.md). UniV and GM UVs are licensed under GPL-3.0-or-later.

