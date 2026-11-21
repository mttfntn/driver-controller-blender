"""Record the add-on's behaviour on a broad set of inputs as JSON.

Run it on two versions and diff the files to prove a refactor changed nothing:
    python tests/run_blender.py --addon-root OLD_COPY tests/probe_behaviour.py -- old.json
    python tests/run_blender.py tests/probe_behaviour.py -- new.json
    python tests/compare_probes.py old.json new.json

Only operators and helpers present in every released version are used.
"""

import json
import os
import sys
import types

import bpy

sys.path.insert(0, os.environ["DC_ADDON_ROOT"])
import driver_controllers as dc  # noqa: E402

dc.register()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_addon import FakeLayout  # noqa: E402

O = bpy.ops.dctrl
OUT = {}


def rec(key, value):
    OUT[key] = value


def norm(v):
    if hasattr(v, "to_list"):
        v = v.to_list()
    if isinstance(v, float):
        return round(v, 5)
    if isinstance(v, (list, tuple)):
        return [norm(x) for x in v]
    if isinstance(v, dict):
        return {k: norm(x) for k, x in sorted(v.items())}
    return v


def fresh():
    bpy.ops.wm.read_homefile(use_factory_startup=True)
    dc._on_load(None)
    dc.set_active_controller(bpy.context, bpy.data.objects["MainController"])
    bpy.context.scene.dc_settings.prop_filter = ""
    dc._CLIPBOARD.update(ctrl="", prop="")
    return bpy.data.objects["MainController"]


def drivers_state():
    out = []
    for idb, _ref, fc in dc.iter_drivers():
        d = fc.driver
        out.append([idb.name, fc.data_path, fc.array_index, d.type, d.expression, d.is_valid,
                    [[v.name, v.type, [[t.id.name if t.id else None, t.data_path] for t in v.targets]]
                     for v in d.variables],
                    norm([list(k.co) for k in fc.keyframe_points]),
                    [m.type for m in fc.modifiers]])
    return sorted(out, key=lambda x: (x[0], x[1], x[2]))


def props_state(obj):
    return {n: [dc.detect_type(obj, n), norm(obj[n]), norm(dc.ui_dict(obj, n))] for n in dc.user_props(obj)}


def draw_log():
    log = []
    for cls in (dc.DC_PT_main, dc.DC_PT_properties, dc.DC_PT_drivers):
        lay = FakeLayout(log)
        try:
            cls.draw(types.SimpleNamespace(layout=lay), bpy.context)
        except Exception as e:  # recorded, so a difference shows up in the diff
            log.append(("error", cls.__name__, repr(e)))
    return [list(x) for x in log]


def safe(fn, *a, **kw):
    try:
        return norm(fn(*a, **kw))
    except Exception as e:
        return "EXC " + type(e).__name__


# 1. value conversion matrix
SAMPLES = [0.0, 0.5, 2.5, -1.4, 3, 0, True, False, "", "1.5", "abc", "1, 2, 3", "off", [1.0, 2.0], [1, 2, 3, 4], [0.2]]
TYPES = ["FLOAT", "INT", "BOOL", "STRING", "VECTOR", "COLOR"]
rec("convert", {f"{s!r}->{t}/{n}": safe(dc.convert_value, s, t, n)
                for s in SAMPLES for t in TYPES for n in (1, 3, 4)})

# 2. edit-dialog type changes (source type x target type)
m = fresh()
starts = {"FLOAT": 0.7, "INT": 3, "BOOL": True, "STRING": "2.5", "VECTOR": [1.0, 2.0, 3.0]}
res = {}
for src, val in starts.items():
    for dst in TYPES:
        for with_ui in (False, True):
            m = fresh()
            m["p"] = val
            if with_ui:  # as created by Add Property: UI settings + library overridable (fixed type)
                m.id_properties_ui("p").update(description="tip")
                m.property_overridable_library_set('["p"]', True)
            try:
                st = sorted(O.prop_edit("EXEC_DEFAULT", ctrl_name=m.name, old_name="p", prop_name="p",
                                        prop_type=dst, float_value=0.7, int_value=3, bool_value=True,
                                        string_value="x", vector_value=[0.5] * 32, array_length=3,
                                        min_value=0, max_value=4))
            except Exception as e:
                st = "EXC " + type(e).__name__
            res[f"{src}->{dst}{' (ui)' if with_ui else ''}"] = [st, props_state(m)]
rec("edit_types", res)

# 3. property add with every option
m = fresh()
O.prop_add("EXEC_DEFAULT", ctrl_name=m.name, prop_name="f", prop_type="FLOAT", float_value=0.3, min_value=-2,
           max_value=2, use_soft_limits=True, soft_min=-1, soft_max=1, step=0.5, precision=2,
           float_subtype="ANGLE", description="d", overridable=False)
O.prop_add("EXEC_DEFAULT", ctrl_name=m.name, prop_name="i", prop_type="INT", int_value=7, min_value=0, max_value=9)
O.prop_add("EXEC_DEFAULT", ctrl_name=m.name, prop_name="c", prop_type="COLOR", color_value=(0.1, 0.2, 0.3, 0.4),
           color_alpha=True)
O.prop_add("EXEC_DEFAULT", ctrl_name=m.name, prop_name="v", prop_type="VECTOR", array_length=2,
           vector_value=[4, 5] + [0] * 30, vector_subtype="EULER", min_value=-9, max_value=9)
rec("add_props", props_state(m))
rec("overridable", {n: m.is_property_overridable_library(dc.prop_path(n)) for n in dc.user_props(m)})

# 4. drivers: add, rename, copy, retarget, paste, remove, expressions
add = lambda prop, path, idx=-1, **kw: O.driver_add("EXEC_DEFAULT", ctrl_name="MainController", prop_name=prop,
                                                    target_name="Cube", data_path=path, array_index=idx, **kw)
add("f", "scale", 2)
add("v", "location", -1, mode="SCRIPTED", expression="var*3")
add("v", "rotation_euler", 0, match_index=False, element=1)
add("i", "nonexistent")
cube = bpy.data.objects["Cube"]
cube.shape_key_add(name="Basis")
cube.shape_key_add(name="Smile")
add("f", 'data.shape_keys.key_blocks["Smile"].value')
rec("drivers_after_add", drivers_state())
O.prop_edit("EXEC_DEFAULT", ctrl_name="MainController", old_name="f", prop_name="f_renamed", prop_type="FLOAT",
            float_value=0.3, min_value=-2, max_value=2)
rec("props_after_rename", list(dc.user_props(m)))
rec("drivers_after_rename", drivers_state())
O.controller_duplicate()
c2 = dc.active_controller(bpy.context)
dc.set_active_controller(bpy.context, m)
bpy.ops.mesh.primitive_uv_sphere_add()
O.driver_copy("EXEC_DEFAULT", ctrl_name="MainController", owner_ref="", retarget=c2.name)
rec("drivers_after_copy", drivers_state())
O.controller_add("EXEC_DEFAULT", name="Third")
dc.set_active_controller(bpy.context, m)
O.driver_retarget("EXEC_DEFAULT", ctrl_name="MainController", owner_ref=dc.make_ref("objects", "Cube"),
                  data_path="scale", array_index=2, target="Third")
rec("drivers_after_retarget", drivers_state())
rec("third_props", props_state(bpy.data.objects["Third"]))
O.driver_copy_prop(ctrl_name="MainController", prop_name="v")
ctrl, pname = dc.clipboard_source()
fake = types.SimpleNamespace(all_channels=True, use_selected=False, report=lambda *a: None)
dc.DC_OT_driver_paste.paste(fake, bpy.context, ctrl, pname, bpy.data.objects["Camera"], "location", 0)
rec("drivers_after_paste", drivers_state())
for fc in bpy.data.objects["Camera"].animation_data.drivers:
    fc.driver.expression = "1.0"
dc.sync_expressions()
rec("expr_after_sync", drivers_state())
for c in dc.get_controllers():
    c.update_tag()
bpy.context.view_layer.update()
rec("evaluated", {o.name: norm([list(o.location), list(o.scale), list(o.rotation_euler)])
                  for o in bpy.data.objects if o.type != "EMPTY"})
rec("cache_usage", {c.name: norm(dc.cached_usage(c)) for c in dc.get_controllers()})
bpy.context.scene.dc_settings.show_vars = True
rec("draw_unfiltered", draw_log())
bpy.context.scene.dc_settings.prop_filter = "v"
rec("draw_filtered", draw_log())
bpy.context.scene.dc_settings.prop_filter = "v"
O.driver_remove("EXEC_DEFAULT", ctrl_name="MainController", owner_ref="")
rec("drivers_after_bulk_remove", drivers_state())
O.prop_remove("EXEC_DEFAULT", ctrl_name="MainController", prop_name="i", remove_drivers=True)
dc.set_active_controller(bpy.context, c2)
O.controller_remove("EXEC_DEFAULT", retarget=True)
rec("final_drivers", drivers_state())
rec("final_controllers", sorted(o.name for o in dc.get_controllers()))
rec("final_props", {c.name: props_state(c) for c in dc.get_controllers()})

out = sys.argv[sys.argv.index("--") + 1] if "--" in sys.argv else "probe.json"
with open(out, "w", encoding="utf-8") as f:
    json.dump(OUT, f, indent=1, sort_keys=True, default=str)
print("probe written:", out, len(OUT), "sections")
