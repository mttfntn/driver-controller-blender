# AGENTS.md – Driver Controller

Blender **5.3-only** extension. Single module `driver_controller/__init__.py`; N-panel *View3D > Sidebar > Controllers*.
Controllers = objects in collection `CONTROLLERS` (default `MainController`). Manages their ID custom properties and
every driver in `bpy.data` that reads them. Human-oriented details: `HANDOVER.md`.

## Commands
```
python tests/run_blender.py                                   # unit tests (expect "Ran 38 tests ... OK")
python tests/run_blender.py --blender PATH ...                # other Blender binary ($BLENDER also works)
blender --factory-startup --command extension validate driver_controller
blender --factory-startup --command extension build --source-dir driver_controller --output-dir dist
python tests/run_blender.py tests/test_install.py -- dist/driver_controller-<ver>.zip
python tests/run_blender.py --addon-root <old copy> tests/probe_behaviour.py -- old.json   # behaviour snapshot
python tests/compare_probes.py old.json new.json             # exit 1 on any difference
```
`run_blender.py` = `--background --factory-startup` + temporary `BLENDER_USER_RESOURCES`. Never test in the
user's running Blender or real profile.

## Architecture (file order)
constants → helpers (`prop_path`, `ensure_setup`, `detect_type`, `convert_value`, `copy_prop`, `reinsert_prop`)
→ driver helpers (`iter_drivers`, `controller_drivers`, `copy_driver`, `retarget_fcurve`, `rename_prop_in_drivers`)
→ cache (`driver_index`, `cached_usage`, `cached_controller_drivers`, `invalidate_index`) → operators
(`dctrl.*`: controllers, properties, drivers, copy/paste) → UI (`DC_UL_controllers`, `DC_PT_main`,
`DC_PT_properties`, `DC_PT_drivers`, right-click `draw_paste_menu`) → expression sync (`sync_expressions`, msgbus)
→ handlers + `register()`.

## Data flow
- Operators reference controllers/properties by **name** (`ctrl_name`, `prop_name`), drivers by
  `owner_ref` (`make_ref`: "collection\tname\tembedded") + `data_path` + `array_index`; empty `owner_ref` = all
  listed drivers of the active controller (respecting `dc_settings.prop_filter`).
- Panels read only the cache. Cache = plain tuples, keyed by `as_pointer()` ints; invalidated on
  `depsgraph_update_post` (not during playback), `undo_post`, `redo_post`, `load_post`, and by `tag_update()`.
- After any data change in an operator call `tag_update(context)`.
- Scene state: `Scene.dc_settings` (`ctrl_index`, `prop_filter`, `show_vars`). In-memory only: `_UNLOCKED`,
  `_CLIPBOARD`, `_LAST_TYPES`, `_INDEX`.

## Rules and pitfalls
- No docstrings on Operator/Panel classes (they become tooltips); use `bl_description` and `#` comments.
- Library-overridable ID props have a **fixed type**: delete before assigning a different type.
- `driver_add()` adds two default keyframes; clear before copying curves.
- msgbus is cleared on file load → resubscribe in `_on_load`. Timers don't run in background mode.
- Never keep Python references to Blender data across undo; store names/paths/ints.
- `obj.keys()` includes other add-ons' registered props; filter with `obj.bl_rna.properties`.
- Draw code must not write data (only `invalidate_index()` on a plain dict is allowed).
- Keep `tests/` and repo docs out of the package (the build uses only `driver_controller/`).
- Line endings: LF (`.gitattributes`).
- **Name is singular**, matching the repo: "Driver Controller", id/folder `driver_controller`. The first v1.0.0
  upload used the plural `driver_controllers` by mistake and was rebuilt. Plural "Controllers" (tab, `CONTROLLERS`
  collection, `DC_UL_controllers`) means the controller objects and stays.

## How changes were verified (v1.0.0)
38 unit tests; install test of the built zip; behaviour probe baseline `fe54ef8` vs v1.0.0 → only the two
intended fixes differ (Edit-dialog type change on overridable props; scalar→RGBA alpha = 1.0); noise check 0;
draw benchmark (1200 drivers) 18.6 → 14.4 ms.

## Release checklist
1. Bump `version` in `blender_manifest.toml` and `bl_info["version"]`. README badges are live (shields.io/GitHub):
   never hard-code versions in them.
2. Tests green locally and on CI (`.github/workflows/ci.yml`, ubuntu, Blender 5.3.0 sha256-pinned, mirrors + retries).
3. `git tag -a vX.Y.Z -m "<release notes>"` → `git push origin vX.Y.Z`. CI checks tag == manifest, builds,
   publishes the release with the zip; notes = tag message; then commits `.github/release-size.json` (download-size badge data) to `main`.

## Git
Remote `origin` = https://github.com/mttfntn/driver-controller-blender (public).
Community files: `.github/ISSUE_TEMPLATE/` (forms, blank issues off), `.github/pull_request_template.md`,
`CONTRIBUTING.md`, `SECURITY.md` (private vulnerability reports). Branch `main`. Tags `vX.Y.Z`.
`dist/`, `*.zip`, `*.blend`, `*.blend1` are ignored.
