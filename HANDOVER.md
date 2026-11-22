# Handover – Driver Controller

## What it is
A Blender 5.3 add-on (packaged as an *extension*) that adds an N-panel, *3D Viewport > Sidebar > Controllers*.
Controllers are objects (normally empties) in the `CONTROLLERS` collection; `MainController` is the default one.
The panel edits the controllers' custom properties and manages every driver in the file that reads them.
Not a fork: there is no upstream project.

## What you need
- **Blender 5.3** (the only supported version; the manifest refuses other versions).
- Python 3 on your PATH, only to start the test runner (Blender brings its own Python for the tests).
- Git and the GitHub CLI (`gh`) for releases.

## Files

| Path | What it is |
|---|---|
| `driver_controller/__init__.py` | The whole add-on (one module). Its header lists the sections in order. |
| `driver_controller/blender_manifest.toml` | Extension manifest: id, version, Blender 5.3 only, license, build excludes. |
| `driver_controller/LICENSE` | GPL-3.0 text shipped inside the package. |
| `tests/run_blender.py` | Starts an **isolated** headless Blender (factory settings, temporary profile) and runs a script in it. |
| `tests/test_addon.py` | Unit tests (38): setup, conversions, properties, drivers, controllers, cache, panel drawing, registration. |
| `tests/test_install.py` | Installs the built zip as an extension in a temporary profile and checks it end to end. |
| `tests/probe_behaviour.py` | Records behaviour on a broad set of inputs as JSON, for before/after comparisons. |
| `tests/compare_probes.py` | Diffs two probe JSON files. |
| `.github/workflows/ci.yml` | CI: tests on push/PR; on a `vX.Y.Z` tag also builds and publishes the release. |
| `.github/ISSUE_TEMPLATE/`, `.github/pull_request_template.md` | Issue forms (bug, feature; blank issues off) and the pull-request checklist. |
| `CONTRIBUTING.md`, `SECURITY.md` | How to contribute; how to report security problems privately. |
| `LICENSE`, `README.md`, `HANDOVER.md`, `AGENTS.md` | Repo documents (not shipped in the package). |

## How it works
1. **Setup.** `ensure_setup()` creates or relinks `CONTROLLERS` and `MainController`. It runs from the `load_post`
   handler (when the *auto-create* preference is on) and from the *Create Setup* button.
2. **Properties** are ordinary ID custom properties on the controller object. Operators carry the controller by
   *name* (`ctrl_name`) and the property by name. Types are detected from the stored value (`detect_type`);
   changing type converts the value (`convert_value`). Renaming rewrites the driver variable paths that read it
   (`rename_prop_in_drivers`) and re-inserts the following properties to keep the order.
3. **Drivers** are not stored by the add-on; they are found by scanning `bpy.data` (`iter_drivers`).
   A driver "uses" a controller when one of its variable targets points to it.
4. **Cache.** The panels read `driver_index()`, a cached list of `(owner key, data path, index, {controller id:
   property names})` built in one scan. It is plain data, dropped by `invalidate_index()` on every depsgraph
   update (except during playback), undo/redo, file load and after the add-on's operators. Stale entries found
   while drawing are skipped and trigger a rebuild.
5. **Copy / paste a driver.** The copy button stores `(controller, property)` in a module-level clipboard.
   The right-click menu entry reads the hovered property from `context.property`, then creates the driver
   with `setup_controller_driver()`.
6. **Expression sync.** A `msgbus` subscription on `Driver.type` plus `sync_expressions()` keep `var` (or the
   equivalent formula) in the hidden expression of non-scripted controller drivers, so switching to
   *Scripted Expression* shows something usable. User-written scripted expressions are never touched.

## Making a change
1. Edit `driver_controller/__init__.py`. Operator tooltips come from `bl_description`; do not add docstrings to
   operator classes (Blender would show them as tooltips).
2. Add or update a test in `tests/test_addon.py`.
3. Run `python tests/run_blender.py` (must end with `OK`).
4. For refactors, compare behaviour with the previous commit:
   ```
   git worktree add ../dc-old HEAD~1
   python tests/run_blender.py --addon-root ../dc-old tests/probe_behaviour.py -- old.json
   python tests/run_blender.py tests/probe_behaviour.py -- new.json
   python tests/compare_probes.py old.json new.json
   ```
   Every difference must be explained.
5. Try it by hand: install the built zip (below) in Blender, or load the module from the repo folder.

## Tests
```
python tests/run_blender.py                                              # 38 unit tests
blender --factory-startup --command extension build --source-dir driver_controller --output-dir dist
python tests/run_blender.py tests/test_install.py -- dist/driver_controller-1.0.0.zip   # install test
```
`run_blender.py` finds Blender via `--blender`, `$BLENDER`, the default Windows path of 5.3, or `blender` on PATH.
It never uses your real profile: `--factory-startup` plus a temporary `BLENDER_USER_RESOURCES`.

## Making a release
1. Bump `version` in `driver_controller/blender_manifest.toml` (and `bl_info["version"]`).
2. Commit, push, wait for the *Tests* workflow to pass.
3. Create an **annotated** tag; its message becomes the release notes:
   `git tag -a v1.2.3 -m "notes…"` then `git push origin v1.2.3`.
4. CI re-runs the tests, checks the tag matches the manifest, builds the zip and publishes the GitHub release.
   The README badges are live (shields.io,
   GitHub): never hard-code versions in them.

## Updates from an original project
None: this project is not a fork.

## Things to know
- **Library-overridable properties have a fixed type in Blender** (int is converted to float, other types raise
  `TypeError`). *Add Property* makes properties overridable by default, so a type change must delete the
  property first (done in the Edit operator).
- `driver_add()` in Blender 5 creates F-Curves with two default keyframes; `copy_driver()` clears them before
  copying the source curve.
- `msgbus` subscriptions are cleared when a file loads; `_on_load` subscribes again.
- `bpy.app.timers` do not run in `--background`; tests call `_on_load(None)` directly.
- `obj.keys()` also lists properties registered by other add-ons; `user_props()` filters them using `bl_rna`.
- The panels are tested by drawing into a fake layout (`FakeLayout` in `tests/test_addon.py`).
- The lock state and the driver clipboard live in memory only (by design: everything starts locked).
- **The name is singular**, like the repo: *Driver Controller*, extension id and folder `driver_controller`.
  The first v1.0.0 upload was named "Driver Controllers" (`driver_controllers`) by mistake; the release was
  rebuilt under the singular name. If an old copy is installed, uninstall it before installing the new zip.
  The plural *Controllers* (sidebar tab, `CONTROLLERS` collection) refers to the controller objects and is intended.

## Known limits
- The Drivers panel draws one box per driver: with ~1200 drivers and no filter a full redraw takes ~14 ms.
  Use the property filter on big rigs; a page/limit would help (not implemented, it would change the UI).
- Boolean arrays are shown and edited as float arrays.
- *Copy to selected* maps owners to objects, shape keys, object data and the active material; other owner
  types are skipped.
- Only Blender 5.3 is supported and tested.
