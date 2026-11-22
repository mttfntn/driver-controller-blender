# Driver Controller

[![Blender](https://img.shields.io/badge/dynamic/toml?url=https%3A%2F%2Fraw.githubusercontent.com%2Fmttfntn%2Fdriver-controller-blender%2Fmain%2Fdriver_controller%2Fblender_manifest.toml&query=%24.blender_version_min&label=Blender&color=E87D0D&logo=blender&logoColor=white)](https://www.blender.org/download/)
[![Release](https://img.shields.io/github/v/release/mttfntn/driver-controller-blender)](https://github.com/mttfntn/driver-controller-blender/releases/latest)
[![Download size](https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2Fmttfntn%2Fdriver-controller-blender%2Fmain%2F.github%2Frelease-size.json)](https://github.com/mttfntn/driver-controller-blender/releases/latest)
[![Tests](https://github.com/mttfntn/driver-controller-blender/actions/workflows/ci.yml/badge.svg)](https://github.com/mttfntn/driver-controller-blender/actions/workflows/ci.yml)
[![License](https://img.shields.io/github/license/mttfntn/driver-controller-blender)](LICENSE)
[![Language](https://img.shields.io/github/languages/top/mttfntn/driver-controller-blender)](driver_controller/__init__.py)

Blender add-on to drive a rig or a scene from **controller empties**: their custom properties
are edited in one N-panel, and every driver that reads them is listed, previewed and managed there.

**3D Viewport > Sidebar (N) > Controllers** · Blender **5.3** only.

## Install
1. Download `driver_controller-X.Y.Z.zip` from the [latest release](https://github.com/mttfntn/driver-controller-blender/releases/latest).
2. Blender: *Edit > Preferences > Get Extensions > ⌄ > Install from Disk…* and pick the zip.
   If an earlier upload named "Driver Controllers" is installed, uninstall it first.

## What it does
- **Setup**: creates the `CONTROLLERS` collection and the `MainController` empty (plain axes) when missing –
  automatically on file load (option in the add-on preferences) or with the *Create Setup* button.
- **Controllers list**: every object in `CONTROLLERS` is a controller. Add / duplicate (with properties) /
  remove (by default its drivers move to MainController) / select.
- **Properties** of the active controller, one row each: type icon, name, live value, driver count
  (click = show those drivers), **edit** ✏, **copy driver** ⧉ and, set apart, 🔒 lock + 🗑 bin
  (the bin works only after unlocking; everything is locked again after a restart).
  - *Add Property* on top.
  - Edit: name, type (Float, Integer, Boolean, String, Float Array, Integer Array, Color – the value is converted),
    value, min/max, soft limits, step, precision, subtype, tooltip, library-overridable.
    **Renaming updates every driver that reads the property** and keeps it in its place in the list.
  - Copy driver ⧉, then right-click any property of any object (location, a modifier value, a shape key,
    a material input…) > **Paste Controller Driver**; also *(All Channels)* for vectors/colors and
    *to Selected* for the same property on every selected object.
  - Delete: optionally with its drivers.
  - Blender's own flow works too: right-click a value > *Copy as New Driver*, right-click a target > *Paste Driver*.
- **Drivers** reading the active controller (anywhere in the file: objects, shape keys, materials, node trees…):
  edit type / expression / variables, see each driver's live result (e.g. `= 1.500`), select the driven object,
  **copy to selected objects** (optionally re-pointed to another controller, creating missing properties),
  **retarget** to another controller, remove. Header buttons act on all listed drivers. With a property filter on,
  *Add Driver from 'prop'* drives any object path (`location`, `modifiers["Bevel"].width`,
  `data.shape_keys.key_blocks["Smile"].value` …).
- Switching a driver from *Averaged Value* to *Scripted Expression* shows `var`, ready to edit.

Typical multi-controller workflow: duplicate `MainController` → select the second character →
*Drivers > Copy to Sel.* with *Controller = the new one*.

## Performance
Panels don't scan the file while redrawing: the list of drivers that read a controller is cached and rebuilt
only after a change (data edit, undo/redo, file load). Measured with ~1200 drivers: looking up the panels' data
takes ~0.13 ms instead of a ~5.6 ms full scan.

## Development
Tests run in an isolated, headless Blender 5.3 (your profile is never used):

```
python tests/run_blender.py
```

See **[HANDOVER.md](HANDOVER.md)** (for people) and **[AGENTS.md](AGENTS.md)** (for AI assistants) for the
architecture, tests, release steps and known limits.

## Contributing
Bug reports, ideas and pull requests are welcome: see **[CONTRIBUTING.md](CONTRIBUTING.md)**. Open an issue with one
of the [forms](https://github.com/mttfntn/driver-controller-blender/issues/new/choose); report security problems
privately as described in **[SECURITY.md](SECURITY.md)**.

## License
GPL-3.0-or-later – see [LICENSE](LICENSE). © 2026 Matteo Fontana.
