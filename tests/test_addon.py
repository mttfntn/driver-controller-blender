"""Test suite for the Driver Controllers add-on.

Runs inside headless Blender (see tests/run_blender.py). Every test starts from
Blender's factory scene (Cube, Camera, Light); loading it fires the add-on's
load_post handler, which creates CONTROLLERS / MainController.

The panels are drawn into a recording fake layout, so the UI code paths are
exercised even without a window.
"""

import os
import sys
import types
import unittest

import bpy

sys.path.insert(0, os.environ.get("DC_ADDON_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import driver_controllers as dc  # noqa: E402

O = bpy.ops.dctrl


# ---------------------------------------------------------------- helpers ---

class FakeLayout:
    """Accepts every UILayout call, records operators and labels."""

    def __init__(self, log=None):
        self.__dict__["log"] = log if log is not None else []

    def __getattr__(self, name):
        def call(*args, **kw):
            if name == "operator":
                self.log.append(("op", args[0], kw.get("text", "")))
                return types.SimpleNamespace()
            if name == "label":
                self.log.append(("label", kw.get("text", args[0] if args else "")))
            if name == "prop":
                self.log.append(("prop", args[1] if len(args) > 1 else ""))
            return FakeLayout(self.log)
        return call

    def __setattr__(self, name, value):
        pass


def draw_panel(cls, context=None):
    lay = FakeLayout()
    cls.draw(types.SimpleNamespace(layout=lay), context or bpy.context)
    return lay.log


def update():
    for o in dc.get_controllers():
        o.update_tag()
    bpy.context.view_layer.update()


def main_ctrl():
    return bpy.data.objects["MainController"]


def add_prop(name, ptype="FLOAT", ctrl=None, **kw):
    ctrl = ctrl or main_ctrl()
    vec = kw.pop("vector", None)
    if vec is not None:
        kw["vector_value"] = list(vec) + [0.0] * (32 - len(vec))
        kw["array_length"] = len(vec)
    ivec = kw.pop("ivector", None)
    if ivec is not None:
        kw["int_vector_value"] = list(ivec) + [0] * (32 - len(ivec))
        kw["array_length"] = len(ivec)
    return O.prop_add("EXEC_DEFAULT", ctrl_name=ctrl.name, prop_name=name, prop_type=ptype, **kw)


def add_driver(prop, target="Cube", path="location", index=-1, ctrl=None, **kw):
    ctrl = ctrl or main_ctrl()
    return O.driver_add("EXEC_DEFAULT", ctrl_name=ctrl.name, prop_name=prop,
                        target_name=target, data_path=path, array_index=index, **kw)


def targets(fc):
    return [(t.id.name if t.id else None, t.data_path) for v in fc.driver.variables for t in v.targets]


class Base(unittest.TestCase):
    def setUp(self):
        bpy.ops.wm.read_homefile(use_factory_startup=True)
        dc._on_load(None)  # what load_post does (handlers may be skipped by read_homefile)
        dc.set_active_controller(bpy.context, main_ctrl())
        bpy.context.scene.dc_settings.prop_filter = ""
        dc._CLIPBOARD.update(ctrl="", prop="")
        dc._UNLOCKED.clear()


# ------------------------------------------------------------------ setup ---

class TestSetup(Base):
    def test_auto_created_on_load(self):
        self.assertIn("CONTROLLERS", bpy.data.collections)
        self.assertEqual(main_ctrl().empty_display_type, "PLAIN_AXES")
        self.assertFalse(dc.setup_missing(bpy.context.scene))

    def test_recreated_when_missing(self):
        bpy.data.objects.remove(main_ctrl())
        bpy.data.collections.remove(bpy.data.collections["CONTROLLERS"])
        self.assertTrue(dc.setup_missing(bpy.context.scene))
        self.assertEqual(O.setup(), {"FINISHED"})
        self.assertFalse(dc.setup_missing(bpy.context.scene))

    def test_relinks_unlinked_parts(self):
        coll = bpy.data.collections["CONTROLLERS"]
        bpy.context.scene.collection.children.unlink(coll)
        coll.objects.unlink(main_ctrl())
        self.assertTrue(dc.setup_missing(bpy.context.scene))
        dc.ensure_setup(bpy.context.scene)
        self.assertFalse(dc.setup_missing(bpy.context.scene))
        self.assertEqual(len([c for c in bpy.data.collections if c.name.startswith("CONTROLLERS")]), 1)

    def test_idempotent(self):
        dc.ensure_setup(bpy.context.scene)
        dc.ensure_setup(bpy.context.scene)
        self.assertEqual(len(bpy.data.collections["CONTROLLERS"].objects), 1)


# ------------------------------------------------------------- conversion ---

class TestConvert(unittest.TestCase):
    def test_scalars(self):
        cv = dc.convert_value
        self.assertEqual(cv(0.5, "INT"), 1)
        self.assertEqual(cv(2.5, "INT"), 3)
        self.assertEqual(cv(-0.4, "INT"), 0)
        self.assertEqual(cv(3, "FLOAT"), 3.0)
        self.assertIs(cv(0.0, "BOOL"), False)
        self.assertIs(cv(0.2, "BOOL"), True)
        self.assertIs(cv("off", "BOOL"), False)
        self.assertIs(cv("yes", "BOOL"), True)
        self.assertEqual(cv(True, "STRING"), "True")
        self.assertEqual(cv(1.5, "STRING"), "1.5")
        self.assertEqual(cv("2.25", "FLOAT"), 2.25)
        self.assertEqual(cv("abc", "FLOAT"), 0.0)

    def test_arrays(self):
        cv = dc.convert_value
        self.assertEqual(cv(2.0, "VECTOR", 3), [2.0, 2.0, 2.0])
        self.assertEqual(cv("1, 2;3", "VECTOR", 3), [1.0, 2.0, 3.0])
        self.assertEqual(cv(0.5, "COLOR", 3), [0.5, 0.5, 0.5])
        self.assertEqual(cv(0.5, "COLOR", 4), [0.5, 0.5, 0.5, 1.0])
        self.assertEqual(cv(1.6, "INT_ARRAY", 2), [2, 2])


# ------------------------------------------------------------- properties ---

class TestProperties(Base):
    def test_add_each_type(self):
        m = main_ctrl()
        add_prop("f", "FLOAT", float_value=0.25, min_value=-1, max_value=2, float_subtype="FACTOR",
                 description="tip", overridable=True)
        add_prop("i", "INT", int_value=4, min_value=0, max_value=10)
        add_prop("b", "BOOL", bool_value=True)
        add_prop("s", "STRING", string_value="hi")
        add_prop("v", "VECTOR", vector=[1, 2, 3], min_value=-5, max_value=5)
        add_prop("c", "COLOR", color_value=(1, 0.5, 0.25, 1))
        add_prop("ia", "INT_ARRAY", ivector=[1, 2], min_value=0, max_value=9)
        self.assertEqual({n: dc.detect_type(m, n) for n in dc.user_props(m)},
                         {"f": "FLOAT", "i": "INT", "b": "BOOL", "s": "STRING", "v": "VECTOR",
                          "c": "COLOR", "ia": "INT_ARRAY"})
        ui = m.id_properties_ui("f").as_dict()
        self.assertEqual((ui["min"], ui["max"], ui["subtype"], ui["description"]), (-1, 2, "FACTOR", "tip"))
        self.assertTrue(m.is_property_overridable_library('["f"]'))
        self.assertEqual(m["v"].to_list(), [1.0, 2.0, 3.0])
        self.assertEqual(len(m["c"]), 3)
        self.assertEqual(m["ia"].to_list(), [1, 2])

    def test_add_rejects_duplicates_and_empty(self):
        add_prop("x")
        with self.assertRaises(RuntimeError):
            add_prop("x")
        with self.assertRaises(RuntimeError):
            add_prop("  ")

    def test_user_props_filtering(self):
        m = main_ctrl()
        m["_hidden"] = 1
        m["ok"] = 1.0
        self.assertEqual(dc.user_props(m), ["ok"])

    def test_edit_type_changes_keep_drivers(self):
        add_prop("h", "FLOAT", float_value=0.6, min_value=0, max_value=2)
        add_driver("h", path="scale", index=2)
        m = main_ctrl()
        for t in ("INT", "FLOAT", "BOOL", "FLOAT", "VECTOR", "COLOR", "INT_ARRAY", "STRING", "FLOAT"):
            O.prop_edit("EXEC_DEFAULT", ctrl_name=m.name, old_name="h",
                        prop_name="h", prop_type=t, float_value=0.6, int_value=1, bool_value=True,
                        vector_value=[0.6] * 32, int_vector_value=[1] * 32, array_length=3,
                        string_value="0.6", min_value=0, max_value=2)
            self.assertEqual(dc.detect_type(m, "h"), t)
        fc = bpy.data.objects["Cube"].animation_data.drivers.find("scale", index=2)
        self.assertEqual(targets(fc), [("MainController", '["h"]')])

    def test_rename_updates_drivers_and_keeps_order(self):
        for n in ("a", "b", "c"):
            add_prop(n)
        add_driver("b", path="scale", index=0)
        m = main_ctrl()
        O.prop_edit("EXEC_DEFAULT", ctrl_name=m.name, old_name="b", prop_name="b2", prop_type="FLOAT",
                    float_value=0.0, min_value=0, max_value=1)
        self.assertEqual(dc.user_props(m), ["a", "b2", "c"])
        fc = bpy.data.objects["Cube"].animation_data.drivers.find("scale", index=0)
        self.assertEqual(targets(fc), [("MainController", '["b2"]')])

    def test_remove_with_and_without_drivers(self):
        add_prop("a")
        add_prop("b")
        add_driver("a", path="scale", index=0)
        add_driver("b", path="scale", index=1)
        m = main_ctrl()
        O.prop_remove("EXEC_DEFAULT", ctrl_name=m.name, prop_name="a", remove_drivers=True)
        O.prop_remove("EXEC_DEFAULT", ctrl_name=m.name, prop_name="b", remove_drivers=False)
        cube = bpy.data.objects["Cube"]
        self.assertIsNone(cube.animation_data.drivers.find("scale", index=0))
        self.assertIsNotNone(cube.animation_data.drivers.find("scale", index=1))
        self.assertEqual(dc.user_props(m), [])

    def test_lock_toggle(self):
        add_prop("a")
        O.prop_lock(ctrl_name="MainController", prop_name="a")
        self.assertIn(("MainController", "a"), dc._UNLOCKED)
        O.prop_lock(ctrl_name="MainController", prop_name="a")
        self.assertNotIn(("MainController", "a"), dc._UNLOCKED)

    def test_filter_toggle(self):
        O.prop_filter(prop_name="a")
        self.assertEqual(bpy.context.scene.dc_settings.prop_filter, "a")
        O.prop_filter(prop_name="a")
        self.assertEqual(bpy.context.scene.dc_settings.prop_filter, "")


# ----------------------------------------------------------------- drivers ---

class TestDrivers(Base):
    def test_scalar_driver_evaluates(self):
        add_prop("h", float_value=0.5, min_value=0, max_value=5)
        add_driver("h", path="scale", index=2)
        main_ctrl()["h"] = 1.75
        update()
        self.assertAlmostEqual(bpy.data.objects["Cube"].scale[2], 1.75, places=5)

    def test_array_driver_matches_indices_and_scripted(self):
        add_prop("off", "VECTOR", vector=[1, 2, 3], min_value=-10, max_value=10)
        add_driver("off", path="location", mode="SCRIPTED", expression="var*2")
        update()
        self.assertEqual([round(x, 4) for x in bpy.data.objects["Cube"].location], [2.0, 4.0, 6.0])

    def test_array_source_fixed_element(self):
        add_prop("off", "VECTOR", vector=[1, 2, 3], min_value=-10, max_value=10)
        add_driver("off", path="location", index=0, match_index=False, element=2)
        fc = bpy.data.objects["Cube"].animation_data.drivers.find("location", index=0)
        self.assertEqual(targets(fc), [("MainController", '["off"][2]')])

    def test_invalid_path_is_skipped(self):
        add_prop("h")
        self.assertEqual(add_driver("h", path="no_such_prop"), {"CANCELLED"})

    def test_shape_key_path(self):
        cube = bpy.data.objects["Cube"]
        cube.shape_key_add(name="Basis")
        cube.shape_key_add(name="Smile")
        add_prop("smile")
        add_driver("smile", path='data.shape_keys.key_blocks["Smile"].value')
        key = cube.data.shape_keys
        self.assertIsNotNone(key.animation_data.drivers.find('key_blocks["Smile"].value'))

    def test_use_selected(self):
        bpy.ops.mesh.primitive_uv_sphere_add()
        sphere = bpy.context.active_object
        bpy.data.objects["Cube"].select_set(True)
        add_prop("h")
        add_driver("h", path="scale", index=0, use_selected=True)
        self.assertIsNotNone(sphere.animation_data.drivers.find("scale", index=0))

    def test_expression_prefilled_and_switch(self):
        add_prop("h")
        add_driver("h", path="scale", index=0)
        fc = bpy.data.objects["Cube"].animation_data.drivers.find("scale", index=0)
        self.assertEqual((fc.driver.type, fc.driver.expression), ("AVERAGE", "var"))
        fc.driver.expression = "1.0"
        dc.sync_expressions()
        self.assertEqual(fc.driver.expression, "var")
        fc.driver.type = "SCRIPTED"
        dc.sync_expressions()
        fc.driver.expression = "5.0"
        dc.sync_expressions()
        self.assertEqual(fc.driver.expression, "5.0")  # user's own scripted constant is kept

    def test_switch_to_scripted_gets_var(self):
        add_prop("h")
        add_driver("h", path="scale", index=0)
        fc = bpy.data.objects["Cube"].animation_data.drivers.find("scale", index=0)
        dc.sync_expressions()
        fc.driver.expression = "1.0"
        fc.driver.type = "SCRIPTED"
        dc.sync_expressions()
        self.assertEqual(fc.driver.expression, "var")

    def test_default_expression_variants(self):
        add_prop("h")
        add_driver("h", path="scale", index=0)
        drv = bpy.data.objects["Cube"].animation_data.drivers.find("scale", index=0).driver
        drv.variables.new().name = "b"
        self.assertEqual(dc.default_expression(drv), "(var + b) / 2")
        drv.type = "SUM"
        self.assertEqual(dc.default_expression(drv), "var + b")

    def test_paste(self):
        add_prop("h")
        add_prop("off", "VECTOR", vector=[1, 2, 3], min_value=-10, max_value=10)
        cam = bpy.data.objects["Camera"]
        rep = []
        fake = types.SimpleNamespace(all_channels=False, use_selected=False, report=lambda *a: rep.append(a))
        O.driver_copy_prop(ctrl_name="MainController", prop_name="h")
        ctrl, p = dc.clipboard_source()
        self.assertEqual((ctrl.name, p), ("MainController", "h"))
        dc.DC_OT_driver_paste.paste(fake, bpy.context, ctrl, p, cam, "rotation_euler", 1)
        self.assertEqual(targets(cam.animation_data.drivers.find("rotation_euler", index=1)),
                         [("MainController", '["h"]')])
        O.driver_copy_prop(ctrl_name="MainController", prop_name="off")
        ctrl, p = dc.clipboard_source()
        fake.all_channels = True
        dc.DC_OT_driver_paste.paste(fake, bpy.context, ctrl, p, cam, "delta_location", 0)
        self.assertEqual([targets(cam.animation_data.drivers.find("delta_location", index=i))[0][1]
                          for i in range(3)], ['["off"][0]', '["off"][1]', '["off"][2]'])

    def test_hovered_property(self):
        cube = bpy.data.objects["Cube"]
        mod = cube.modifiers.new("Bevel", "BEVEL")
        self.assertEqual(dc.hovered_property(types.SimpleNamespace(property=(mod, "width", -1))),
                         (cube, 'modifiers["Bevel"].width', -1))
        self.assertEqual(dc.hovered_property(types.SimpleNamespace(property=(cube, "location", 2))),
                         (cube, "location", 2))
        self.assertIsNone(dc.hovered_property(types.SimpleNamespace(property=None)))

    def test_copy_to_selected_with_retarget_and_curve(self):
        add_prop("h", float_value=0.5, min_value=0, max_value=5)
        add_driver("h", path="scale", index=2)
        cube = bpy.data.objects["Cube"]
        src = cube.animation_data.drivers.find("scale", index=2)
        src.keyframe_points.clear()
        src.keyframe_points.insert(0, 0)
        src.keyframe_points.insert(1, 3)
        src.extrapolation = "LINEAR"
        gen = src.modifiers.new("GENERATOR")
        gen.poly_order = 2
        gen.coefficients = (0.5, 1.0, 0.25)
        O.controller_duplicate()
        c2 = dc.active_controller(bpy.context)
        dc.set_active_controller(bpy.context, main_ctrl())
        bpy.ops.mesh.primitive_uv_sphere_add()
        sphere = bpy.context.active_object
        O.driver_copy("EXEC_DEFAULT", ctrl_name="MainController", owner_ref="", retarget=c2.name)
        fc = sphere.animation_data.drivers.find("scale", index=2)
        self.assertEqual(targets(fc), [(c2.name, '["h"]')])
        self.assertEqual([tuple(k.co) for k in fc.keyframe_points], [(0.0, 0.0), (1.0, 3.0)])
        self.assertEqual(fc.extrapolation, "LINEAR")
        g = [m for m in fc.modifiers if m.type == "GENERATOR"]
        self.assertEqual(len(g), 1)
        self.assertEqual((g[0].poly_order, [round(x, 4) for x in g[0].coefficients]), (2, [0.5, 1.0, 0.25]))

    def test_copy_creates_missing_props(self):
        add_prop("h", float_value=0.5, min_value=0, max_value=5)
        add_driver("h", path="scale", index=2)
        O.controller_add("EXEC_DEFAULT", name="Empty2")
        dc.set_active_controller(bpy.context, main_ctrl())
        bpy.ops.mesh.primitive_uv_sphere_add()
        O.driver_copy("EXEC_DEFAULT", ctrl_name="MainController", owner_ref="", retarget="Empty2",
                      copy_missing=True)
        self.assertIn("h", bpy.data.objects["Empty2"].keys())

    def test_retarget_single_and_bulk(self):
        add_prop("h")
        add_driver("h", path="scale", index=0)
        add_driver("h", path="scale", index=1)
        O.controller_add("EXEC_DEFAULT", name="B")
        cube = bpy.data.objects["Cube"]
        ref = dc.make_ref("objects", "Cube")
        O.driver_retarget("EXEC_DEFAULT", ctrl_name="MainController", owner_ref=ref, data_path="scale",
                          array_index=0, target="B")
        self.assertEqual(targets(cube.animation_data.drivers.find("scale", index=0))[0][0], "B")
        self.assertEqual(targets(cube.animation_data.drivers.find("scale", index=1))[0][0], "MainController")
        O.driver_retarget("EXEC_DEFAULT", ctrl_name="MainController", owner_ref="", target="B")
        self.assertEqual(targets(cube.animation_data.drivers.find("scale", index=1))[0][0], "B")
        self.assertIn("h", bpy.data.objects["B"].keys())

    def test_remove_bulk_respects_filter(self):
        add_prop("a")
        add_prop("b")
        add_driver("a", path="scale", index=0)
        add_driver("b", path="scale", index=1)
        bpy.context.scene.dc_settings.prop_filter = "a"
        O.driver_remove("EXEC_DEFAULT", ctrl_name="MainController", owner_ref="")
        cube = bpy.data.objects["Cube"]
        self.assertIsNone(cube.animation_data.drivers.find("scale", index=0))
        self.assertIsNotNone(cube.animation_data.drivers.find("scale", index=1))

    def test_select_owner(self):
        add_prop("a")
        add_driver("a", path="scale", index=0)
        O.driver_select_owner(ctrl_name="MainController", owner_ref=dc.make_ref("objects", "Cube"),
                              data_path="scale", array_index=0)
        self.assertEqual([o.name for o in bpy.context.selected_objects], ["Cube"])

    def test_value_text_helpers(self):
        add_prop("h", float_value=0.5, min_value=0, max_value=5)
        add_driver("h", path="scale", index=1)
        update()
        cube = bpy.data.objects["Cube"]
        fc = cube.animation_data.drivers.find("scale", index=1)
        self.assertEqual(dc.driven_value_text(cube, fc), "0.500")
        self.assertTrue(dc._is_array_path(cube, fc))


# ------------------------------------------------------------- controllers ---

class TestControllers(Base):
    def test_add_duplicate_remove(self):
        add_prop("h")
        O.controller_add("EXEC_DEFAULT", name="Ctrl")
        self.assertEqual(dc.active_controller(bpy.context).name, "Ctrl")
        dc.set_active_controller(bpy.context, main_ctrl())
        O.controller_duplicate()
        dup = dc.active_controller(bpy.context)
        self.assertEqual(dc.user_props(dup), ["h"])
        add_driver("h", path="scale", index=0, ctrl=dup)
        O.controller_remove("EXEC_DEFAULT", retarget=True)
        self.assertNotIn("MainController.001", bpy.data.objects)
        fc = bpy.data.objects["Cube"].animation_data.drivers.find("scale", index=0)
        self.assertEqual(targets(fc)[0][0], "MainController")

    def test_main_cannot_be_removed(self):
        dc.set_active_controller(bpy.context, main_ctrl())
        self.assertFalse(O.controller_remove.poll())


# ------------------------------------------------------------- cache & UI ---

class TestCacheAndPanels(Base):
    def test_cache_counts_and_stale_entries(self):
        add_prop("a")
        add_driver("a", path="scale", index=0)
        add_driver("a", path="scale", index=1)
        m = main_ctrl()
        self.assertEqual(dc.cached_usage(m), {"a": 2})
        bpy.data.objects["Cube"].driver_remove("scale", 0)  # behind the add-on's back
        self.assertEqual(len(dc.cached_controller_drivers(m)), 1)
        self.assertEqual(dc.cached_usage(m), {"a": 1})

    def test_depsgraph_handler_invalidates(self):
        add_prop("a")
        dc.driver_index()
        dc._on_depsgraph_update(bpy.context.scene)
        self.assertIsNone(dc._INDEX["entries"])

    def test_panels_draw(self):
        add_prop("a")
        add_prop("v", "VECTOR", vector=[1, 2, 3], min_value=-5, max_value=5)
        add_driver("a", path="scale", index=0, mode="SCRIPTED", expression="var*2")
        bpy.context.scene.dc_settings.show_vars = True
        log = draw_panel(dc.DC_PT_main) + draw_panel(dc.DC_PT_properties) + draw_panel(dc.DC_PT_drivers)
        ops = {e[1] for e in log if e[0] == "op"}
        for idname in ("dctrl.prop_add", "dctrl.prop_edit", "dctrl.driver_copy_prop", "dctrl.prop_lock",
                       "dctrl.prop_remove", "dctrl.prop_filter", "dctrl.driver_copy", "dctrl.driver_retarget",
                       "dctrl.driver_remove", "dctrl.controller_add"):
            self.assertIn(idname, ops)
        labels = [e[1] for e in log if e[0] == "label"]
        self.assertIn("= 0.000", labels)
        bpy.context.scene.dc_settings.prop_filter = "a"
        O.driver_copy_prop(ctrl_name="MainController", prop_name="a")
        log = draw_panel(dc.DC_PT_properties) + draw_panel(dc.DC_PT_drivers)
        self.assertTrue(any(e[0] == "op" and e[1] == "dctrl.driver_add" for e in log))
        self.assertTrue(any(e[0] == "label" and "Copied" in e[1] for e in log))

    def test_panel_shows_missing_setup(self):
        bpy.data.objects.remove(main_ctrl())
        log = draw_panel(dc.DC_PT_main)
        self.assertIn(("op", "dctrl.setup", "Create Setup"), log)


class TestRegistration(unittest.TestCase):
    def test_unregister_register_cycle(self):
        dc.unregister()
        self.assertFalse(hasattr(bpy.types.Scene, "dc_settings"))
        self.assertNotIn(dc._on_load, bpy.app.handlers.load_post)
        self.assertNotIn(dc._on_depsgraph_update, bpy.app.handlers.depsgraph_update_post)
        dc.register()
        self.assertTrue(hasattr(bpy.types.Scene, "dc_settings"))
        self.assertIn(dc._on_load, bpy.app.handlers.load_post)


if __name__ == "__main__":
    print("Blender", bpy.app.version_string)
    dc.register()
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__]))
    dc.unregister()
    sys.exit(0 if result.wasSuccessful() else 1)
