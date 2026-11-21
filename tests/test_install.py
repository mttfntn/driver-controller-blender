"""Install the built package as an extension and check it works (isolated profile).

    python tests/run_blender.py tests/test_install.py -- dist/driver_controllers-X.Y.Z.zip

Covers what test_addon.py cannot: the real install path, the module name
under bl_ext.*, the add-on preferences, and the "auto-create on file load"
option both on and off.
"""

import os
import sys

import addon_utils
import bpy

MODULE = "bl_ext.user_default.driver_controllers"
zip_path = os.path.abspath(sys.argv[sys.argv.index("--") + 1])
failures = []


def check(cond, msg):
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        failures.append(msg)


print("Blender", bpy.app.version_string, "installing", zip_path)
bpy.ops.extensions.package_install_files(filepath=zip_path, repo="user_default", enable_on_install=True)
check(MODULE in bpy.context.preferences.addons, "enabled as " + MODULE)
check(addon_utils.check(MODULE)[1], "addon_utils reports it loaded")
mod = sys.modules[MODULE]
check(hasattr(bpy.types, "DC_PT_main") and hasattr(bpy.types.Scene, "dc_settings"), "panels and settings registered")
prefs = bpy.context.preferences.addons[MODULE].preferences
check(prefs is not None and prefs.auto_setup is True, "preferences available, auto-setup on by default")

bpy.ops.wm.read_homefile(use_factory_startup=True)
check("CONTROLLERS" in bpy.data.collections and "MainController" in bpy.data.objects,
      "auto-setup ON: CONTROLLERS + MainController created on file load")

prefs.auto_setup = False
bpy.ops.wm.read_homefile(use_factory_startup=True)
check("CONTROLLERS" not in bpy.data.collections, "auto-setup OFF: nothing created on file load")
check(mod.setup_missing(bpy.context.scene), "panel reports the setup as missing")
bpy.ops.dctrl.setup()
check(not mod.setup_missing(bpy.context.scene), "Create Setup button creates it")

bpy.ops.dctrl.prop_add("EXEC_DEFAULT", ctrl_name="MainController", prop_name="h", prop_type="FLOAT",
                       float_value=0.5, min_value=0, max_value=3)
bpy.ops.dctrl.driver_add("EXEC_DEFAULT", ctrl_name="MainController", prop_name="h", target_name="Cube",
                         data_path="scale", array_index=2)
bpy.data.objects["MainController"]["h"] = 2.0
bpy.data.objects["MainController"].update_tag()
bpy.context.view_layer.update()
check(abs(bpy.data.objects["Cube"].scale[2] - 2.0) < 1e-5, "driver from the installed add-on evaluates")

addon_utils.disable(MODULE, default_set=True)
check(not hasattr(bpy.types, "DC_PT_main"), "disabling unregisters cleanly")

print("INSTALL TEST", "FAILED" if failures else "PASSED", f"({len(failures)} failure(s))")
sys.exit(1 if failures else 0)
