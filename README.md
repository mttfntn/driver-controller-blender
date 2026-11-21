# Driver Controllers (Blender 4.2+ / tested on 5.3)

N-panel addon: **3D Viewport > Sidebar (N) > Controllers**.

## Install
Edit > Preferences > Add-ons > ⌄ > **Install from Disk…** > `driver_controllers.zip`.

## What it does
- **Setup**: creates the `CONTROLLERS` collection and the `MainController` empty (plain axes) when missing –
  automatically on file load (toggle in the addon preferences) or with the *Create Setup* button.
- **Controllers list**: every object in `CONTROLLERS` is a controller. Add / duplicate (with properties) /
  remove (drivers are moved to MainController) / select.
- **Properties** of the active controller, one spaced row each:
  type icon + name, live value, driver count (click = show those drivers), **edit** ✏, **copy** ⧉ and, spaced apart, 🔒 lock + 🗑 bin: the bin only works after unlocking (all locked again on restart).
  - *Add Property* button on top.
  - Edit: name, type (Float, Integer, Boolean, String, Float Array, Integer Array, Color – value is converted), value, min/max,
    soft limits, step, precision, subtype, tooltip, library-overridable. **Renaming updates every driver that reads it** and keeps the property in its place in the list.
  - Copy ⧉ = **copy a driver**: then right-click any property of any object (location, a modifier value,
    a shape key, a material input…) > **Paste Controller Driver**. Also *(All Channels)* for vectors/colors and
    *to Selected* to paste on the same property of every selected object.
  - Delete: optionally with its drivers.
  - native Blender flow also works: right-click a value > *Copy as New Driver*, right-click target > *Paste Driver*
- **Drivers** reading the active controller (anywhere in the file: objects, shape keys, materials, node trees…):
  edit type / expression / variables (each driver shows its live result, e.g. `= 1.500`), select driven object, **copy to selected objects** (optionally re-pointing to
  another controller, creating missing properties), **retarget** to another controller, remove.
  Header buttons do the same on all listed drivers. With a property filter active, *Add Driver from 'prop'*
  drives any object path (`location`, `modifiers["Bevel"].width`, `data.shape_keys.key_blocks["Smile"].value` …).

Typical multi-controller workflow: duplicate `MainController` → select the second character →
*Drivers > Copy to Sel.* with *Controller = the new one*.

## Performance
The panels never scan the file while redrawing: one driver index is cached and rebuilt only after a change
(edit, undo/redo, file load). With ~1200 drivers a redraw costs ~0.13 ms instead of ~5.6 ms.
The cache stores only names/numbers, never Blender memory pointers, so undo can't make it crash.
