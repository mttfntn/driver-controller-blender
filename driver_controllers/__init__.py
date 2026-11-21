# SPDX-License-Identifier: GPL-3.0-or-later
"""
Driver Controllers
==================

N-panel (3D Viewport > Sidebar > Controllers) to manage "controller" empties that
live in the CONTROLLERS collection (MainController is the default one), their
custom properties, and every driver in the file that reads from them.

* Creates the CONTROLLERS collection and the MainController empty when missing.
* Add / edit / rename / delete custom properties, change their type in one click
  (Float, Integer, Boolean, String, Float Array, Color) keeping the value.
* Renaming a property also fixes every driver that reads it.
* Lists all drivers that use the active controller, lets you edit type /
  expression / variables, select the driven object, remove them,
  copy them to the selected objects and retarget them to another controller.
"""

bl_info = {
    "name": "Driver Controllers",
    "author": "Matteo Fontana",
    "version": (1, 0, 0),
    "blender": (4, 2, 0),
    "location": "3D Viewport > Sidebar (N) > Controllers",
    "description": "Manage controller empties, their custom properties and the drivers that use them",
    "category": "Animation",
}

import math
import re

import bpy
from bpy.app.handlers import persistent
from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    FloatVectorProperty,
    IntVectorProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)
from bpy.types import AddonPreferences, Operator, Panel, PropertyGroup, UIList

COLL_NAME = "CONTROLLERS"
MAIN_NAME = "MainController"

PROP_TYPES = [
    ("FLOAT", "Float", "Single floating point value"),
    ("INT", "Integer", "Single integer value"),
    ("BOOL", "Boolean", "True / False"),
    ("STRING", "String", "Text"),
    ("VECTOR", "Float Array", "Array / vector of floats"),
    ("INT_ARRAY", "Integer Array", "Array of integers"),
    ("COLOR", "Color", "RGB or RGBA color"),
]
TYPE_LABEL = {k: n for k, n, _ in PROP_TYPES}
TYPE_ICON = {
    "FLOAT": "LINENUMBERS_ON",
    "INT": "LINENUMBERS_OFF",
    "BOOL": "CHECKBOX_HLT",
    "STRING": "FONT_DATA",
    "VECTOR": "EMPTY_ARROWS",
    "INT_ARRAY": "MOD_ARRAY",
    "COLOR": "COLOR",
}
FLOAT_SUBTYPES = [
    ("NONE", "Plain", ""),
    ("FACTOR", "Factor", ""),
    ("PERCENTAGE", "Percentage", ""),
    ("ANGLE", "Angle", ""),
    ("DISTANCE", "Distance", ""),
    ("TIME_ABSOLUTE", "Time", ""),
    ("PIXEL", "Pixel", ""),
]
VECTOR_SUBTYPES = [
    ("NONE", "Plain", ""),
    ("TRANSLATION", "Translation", ""),
    ("EULER", "Euler Angles", ""),
    ("XYZ", "XYZ", ""),
    ("DIRECTION", "Direction", ""),
]
DRIVER_MODES = [
    ("DIRECT", "Direct Value", "Driven value = controller property"),
    ("SCRIPTED", "Expression", "Use a scripted expression (the property is the variable 'var')"),
]
NUMERIC_UI_KEYS = ("min", "max", "soft_min", "soft_max", "step", "precision")

# Data-block collections that can hold drivers.
ID_COLLECTIONS = (
    "objects", "meshes", "shape_keys", "materials", "node_groups", "armatures",
    "cameras", "lights", "curves", "worlds", "scenes", "textures", "lattices",
    "metaballs", "grease_pencils", "grease_pencils_v3", "particles", "speakers",
    "volumes", "pointclouds", "hair_curves", "linestyles", "lightprobes",
)
ID_ICON = {
    "OBJECT": "OBJECT_DATA", "KEY": "SHAPEKEY_DATA", "MESH": "MESH_DATA",
    "MATERIAL": "MATERIAL", "NODETREE": "NODETREE", "ARMATURE": "ARMATURE_DATA",
    "CAMERA": "CAMERA_DATA", "LIGHT": "LIGHT", "CURVE": "CURVE_DATA",
    "WORLD": "WORLD", "SCENE": "SCENE_DATA", "TEXTURE": "TEXTURE",
}


# -----------------------------------------------------------------------------
# Generic helpers
# -----------------------------------------------------------------------------

def addon_prefs():
    addon = bpy.context.preferences.addons.get(__package__ or __name__)
    return addon.preferences if addon else None


def prop_path(name):
    return '["%s"]' % bpy.utils.escape_identifier(name)


_PATH_RE = re.compile(r"""^\[(["'])((?:\\.|(?!\1).)*)\1\]""")


def path_prop_name(path):
    """'["foo"][1]' -> 'foo' ; anything else -> None."""
    m = _PATH_RE.match(path or "")
    if not m:
        return None
    return bpy.utils.unescape_identifier(m.group(2))


def get_collection():
    return bpy.data.collections.get(COLL_NAME)


def get_controllers():
    coll = get_collection()
    return list(coll.objects) if coll else []


def is_controller(obj):
    coll = get_collection()
    return bool(coll and obj and coll.objects.get(obj.name) == obj)


def setup_missing(scene):
    coll = get_collection()
    main = bpy.data.objects.get(MAIN_NAME)
    return (
        coll is None
        or main is None
        or coll.objects.get(MAIN_NAME) is None
        or coll not in scene.collection.children_recursive
    )


def ensure_setup(scene):
    """Create the CONTROLLERS collection and the MainController empty if missing."""
    coll = get_collection()
    if coll is None:
        coll = bpy.data.collections.new(COLL_NAME)
    if scene is not None and coll not in scene.collection.children_recursive:
        scene.collection.children.link(coll)
    main = bpy.data.objects.get(MAIN_NAME)
    if main is None:
        main = bpy.data.objects.new(MAIN_NAME, None)
        main.empty_display_type = "PLAIN_AXES"
        main.empty_display_size = 1.0
    if coll.objects.get(MAIN_NAME) is None:
        coll.objects.link(main)
    return coll, main


def active_controller(context):
    coll = get_collection()
    if not coll or not len(coll.objects):
        return None
    idx = context.scene.dc_settings.ctrl_index
    if 0 <= idx < len(coll.objects):
        return coll.objects[idx]
    return coll.objects.get(MAIN_NAME) or coll.objects[0]


def set_active_controller(context, obj):
    coll = get_collection()
    if coll and obj:
        idx = coll.objects.find(obj.name)
        if idx >= 0:
            context.scene.dc_settings.ctrl_index = idx


def controller_from_name(context, name):
    if name:
        obj = bpy.data.objects.get(name)
        if obj:
            return obj
    return active_controller(context)


def user_props(obj):
    """Custom (user) properties of obj that this addon can edit."""
    if obj is None:
        return []
    rna = obj.bl_rna.properties
    out = []
    for k in obj.keys():
        if k.startswith("_") or k in rna:
            continue
        v = obj[k]
        if isinstance(v, (bool, int, float, str)) or hasattr(v, "typecode"):
            out.append(k)
    return out


def ui_dict(obj, name):
    try:
        return obj.id_properties_ui(name).as_dict()
    except Exception:
        return {}


def detect_type(obj, name):
    v = obj[name]
    if isinstance(v, bool):
        return "BOOL"
    if isinstance(v, int):
        return "INT"
    if isinstance(v, float):
        return "FLOAT"
    if isinstance(v, str):
        return "STRING"
    if getattr(v, "typecode", "") == "i":
        return "INT_ARRAY"
    if ui_dict(obj, name).get("subtype") in {"COLOR", "COLOR_GAMMA"}:
        return "COLOR"
    return "VECTOR"


def _as_list(v):
    return list(v.to_list()) if hasattr(v, "to_list") else None


def _fmt(x):
    return ("%g" % x) if isinstance(x, float) else str(x)


def to_scalar(v):
    lst = _as_list(v)
    if lst is not None:
        v = lst[0] if lst else 0.0
    if isinstance(v, str):
        try:
            return float(v.strip())
        except ValueError:
            return 0.0
    return float(v)


def _parse_list(s):
    out = []
    for part in s.replace(";", ",").split(","):
        try:
            out.append(float(part.strip()))
        except ValueError:
            pass
    return out


def convert_value(v, new_type, length=3):
    """Convert any custom property value to new_type, keeping as much as possible."""
    if new_type == "FLOAT":
        return to_scalar(v)
    if new_type == "INT":
        return int(math.floor(to_scalar(v) + 0.5))
    if new_type == "BOOL":
        if isinstance(v, str):
            return v.strip().lower() not in ("", "0", "false", "no", "off")
        return bool(to_scalar(v))
    if new_type == "STRING":
        lst = _as_list(v)
        if lst is not None:
            return ", ".join(_fmt(x) for x in lst)
        if isinstance(v, bool):
            return "True" if v else "False"
        return _fmt(v)
    # arrays
    lst = _as_list(v)
    if lst is None:
        lst = _parse_list(v) if isinstance(v, str) else []
        if not lst:
            # a single value fills the RGB channels; alpha is added below
            lst = [to_scalar(v)] * (3 if new_type == "COLOR" else length)
    lst = [float(x) for x in lst]
    if new_type == "COLOR":
        if len(lst) == 1:
            lst = lst * 3
        lst = (lst + [1.0, 1.0, 1.0, 1.0])[: (4 if length >= 4 else 3)]
        return lst
    if length:
        lst = (lst + [0.0] * length)[:length]
    if new_type == "INT_ARRAY":
        return [int(math.floor(x + 0.5)) for x in lst]
    return lst


def copy_prop(src, dst, name, overwrite=True):
    if name in dst.keys() and not overwrite:
        return False
    v = src[name]
    lst = _as_list(v)
    dst[name] = lst if lst is not None else v
    ui = ui_dict(src, name)
    if ui:
        try:
            dst.id_properties_ui(name).update(**ui)
        except Exception:
            pass
    try:
        p = prop_path(name)
        dst.property_overridable_library_set(p, src.is_property_overridable_library(p))
    except Exception:
        pass
    return True


def reinsert_prop(obj, name):
    """Delete and re-add a property (value, settings, override flag): moves it to the end."""
    v = obj[name]
    lst = _as_list(v)
    ui = ui_dict(obj, name)
    p = prop_path(name)
    try:
        ovr = obj.is_property_overridable_library(p)
    except Exception:
        ovr = None
    del obj[name]
    obj[name] = lst if lst is not None else v
    if ui:
        try:
            obj.id_properties_ui(name).update(**ui)
        except Exception:
            pass
    if ovr is not None:
        try:
            obj.property_overridable_library_set(p, ovr)
        except Exception:
            pass


# -----------------------------------------------------------------------------
# Driver helpers
# -----------------------------------------------------------------------------

def make_ref(attr, name, embedded=""):
    return "\t".join((attr, name, embedded))


def resolve_ref(ref):
    try:
        attr, name, emb = ref.split("\t")
    except ValueError:
        return None
    coll = getattr(bpy.data, attr, None)
    idb = coll.get(name) if coll is not None else None
    if idb is not None and emb:
        idb = getattr(idb, emb, None)
    return idb


def iter_anim_ids():
    for attr in ID_COLLECTIONS:
        coll = getattr(bpy.data, attr, None)
        if coll is None:
            continue
        for idb in coll:
            yield idb, make_ref(attr, idb.name)
            nt = getattr(idb, "node_tree", None)
            if nt is not None and attr != "node_groups":
                yield nt, make_ref(attr, idb.name, "node_tree")


def iter_drivers():
    for idb, ref in iter_anim_ids():
        ad = getattr(idb, "animation_data", None)
        if ad is None:
            continue
        for fc in ad.drivers:
            yield idb, ref, fc


def driver_ctrl_props(fc, ctrl):
    """Return (uses_ctrl, set_of_prop_names_read)."""
    uses = False
    props = set()
    for var in fc.driver.variables:
        for t in var.targets:
            if t.id is not None and t.id == ctrl:
                uses = True
                if var.type == "SINGLE_PROP":
                    n = path_prop_name(t.data_path)
                    if n is not None:
                        props.add(n)
    return uses, props


def controller_drivers(ctrl, prop_filter=""):
    """All drivers that read ctrl: list of (idb, ref, fc, props)."""
    out = []
    if ctrl is None:
        return out
    for idb, ref, fc in iter_drivers():
        uses, props = driver_ctrl_props(fc, ctrl)
        if not uses:
            continue
        if prop_filter and prop_filter not in props:
            continue
        out.append((idb, ref, fc, props))
    return out


# --- Cached driver index (used by the panels) ---------------------------------
# Panels redraw very often (mouse hover, playback...). Instead of scanning every
# driver of the file on each redraw, one scan is cached and rebuilt only after
# a data change (depsgraph update, undo/redo, file load, our own operators).
# Only plain data is stored (strings / ints), never RNA pointers, so the cache
# can never point to freed memory after an undo.

_INDEX = {"entries": None}


def invalidate_index(*_args):
    _INDEX["entries"] = None


def driver_index():
    """[(ref, data_path, array_index, {controller pointer: frozenset(prop names)})]."""
    if _INDEX["entries"] is None:
        ptrs = {o.as_pointer() for o in get_controllers()}
        out = []
        if ptrs:
            for _idb, ref, fc in iter_drivers():
                uses = {}
                for var in fc.driver.variables:
                    single = var.type == "SINGLE_PROP"
                    for t in var.targets:
                        tid = t.id
                        if tid is None:
                            continue
                        p = tid.as_pointer()
                        if p in ptrs:
                            names = uses.setdefault(p, set())
                            if single:
                                n = path_prop_name(t.data_path)
                                if n is not None:
                                    names.add(n)
                if uses:
                    out.append((ref, fc.data_path, fc.array_index,
                                {k: frozenset(v) for k, v in uses.items()}))
        _INDEX["entries"] = out
    return _INDEX["entries"]


def cached_usage(ctrl):
    """{prop name: number of drivers reading it} for ctrl, from the cache."""
    usage = {}
    key = ctrl.as_pointer()
    for _ref, _path, _idx, uses in driver_index():
        for p in uses.get(key, ()):
            usage[p] = usage.get(p, 0) + 1
    return usage


def cached_controller_drivers(ctrl, prop_filter=""):
    """Like controller_drivers() but from the cache: only the listed drivers are resolved."""
    out = []
    key = ctrl.as_pointer()
    stale = False
    for ref, path, idx, uses in driver_index():
        props = uses.get(key)
        if props is None or (prop_filter and prop_filter not in props):
            continue
        idb = resolve_ref(ref)
        fc = find_fcurve(idb, path, idx) if idb is not None else None
        if fc is None:
            stale = True
            continue
        out.append((idb, ref, fc, props))
    if stale:
        invalidate_index()
    return out


@persistent
def _on_depsgraph_update(_scene, _depsgraph=None):
    screen = getattr(bpy.context, "screen", None)
    if screen is not None and screen.is_animation_playing:
        return  # nothing is edited during playback, keep the cache
    invalidate_index()


def find_fcurve(idb, data_path, index):
    ad = getattr(idb, "animation_data", None)
    if ad is None:
        return None
    return ad.drivers.find(data_path, index=index)


def refresh_driver(fc):
    try:
        fc.driver.is_valid = True
        fc.driver.expression = fc.driver.expression
    except Exception:
        pass


def tag_update(context):
    invalidate_index()
    try:
        sync_expressions(refresh_invalid=True)
    except Exception:
        pass
    for obj in get_controllers():
        obj.update_tag()
    try:
        context.view_layer.update()
    except Exception:
        pass
    for area in getattr(context.screen, "areas", []):
        area.tag_redraw()


def rename_prop_in_drivers(ctrl, old, new):
    count = 0
    for _idb, _ref, fc in iter_drivers():
        changed = False
        for var in fc.driver.variables:
            for t in var.targets:
                if t.id is not None and t.id == ctrl and path_prop_name(t.data_path) == old:
                    m = _PATH_RE.match(t.data_path)
                    t.data_path = prop_path(new) + t.data_path[m.end():]
                    changed = True
        if changed:
            refresh_driver(fc)
            count += 1
    return count


def retarget_fcurve(fc, old_ctrl, new_ctrl, copy_missing=True):
    for var in fc.driver.variables:
        for t in var.targets:
            if t.id is not None and t.id == old_ctrl:
                if copy_missing and var.type == "SINGLE_PROP":
                    n = path_prop_name(t.data_path)
                    if n is not None and n in old_ctrl.keys() and n not in new_ctrl.keys():
                        copy_prop(old_ctrl, new_ctrl, n)
                t.id = new_ctrl
    refresh_driver(fc)


def objects_for_id(idb):
    if isinstance(idb, bpy.types.Object):
        return [idb]
    objs = bpy.data.objects
    if isinstance(idb, bpy.types.Key):
        return [o for o in objs if o.data is not None and getattr(o.data, "shape_keys", None) == idb]
    if isinstance(idb, bpy.types.Material):
        return [o for o in objs if any(s.material == idb for s in o.material_slots)]
    if isinstance(idb, bpy.types.NodeTree):
        return [o for o in objs if any(s.material and s.material.node_tree == idb for s in o.material_slots)]
    return [o for o in objs if o.data is not None and o.data == idb]


def counterpart_id(src_idb, obj):
    """The data-block on obj that corresponds to the driver owner src_idb."""
    if isinstance(src_idb, bpy.types.Object):
        return obj
    if isinstance(src_idb, bpy.types.Key):
        return getattr(obj.data, "shape_keys", None) if obj.data is not None else None
    if isinstance(src_idb, bpy.types.Material):
        return obj.active_material
    if isinstance(src_idb, bpy.types.NodeTree):
        mat = obj.active_material
        return mat.node_tree if mat else None
    if obj.data is not None and type(obj.data) is type(src_idb):
        return obj.data
    return None


def copy_driver(src_fc, src_owner, dst_id, old_ctrl=None, new_ctrl=None, copy_missing=True):
    path, idx = src_fc.data_path, src_fc.array_index
    try:
        dst_id.driver_remove(path, idx)
    except Exception:
        pass
    try:
        new_fc = dst_id.driver_add(path, idx)
    except TypeError:
        new_fc = dst_id.driver_add(path)
    if isinstance(new_fc, (list, tuple)):
        new_fc = new_fc[0]
    sd, dd = src_fc.driver, new_fc.driver
    dd.type = sd.type
    dd.expression = sd.expression
    dd.use_self = sd.use_self
    for v in list(dd.variables):
        dd.variables.remove(v)
    for v in sd.variables:
        nv = dd.variables.new()
        nv.name = v.name
        nv.type = v.type
        for attr in ("use_fallback_value", "fallback_value"):
            if hasattr(v, attr):
                try:
                    setattr(nv, attr, getattr(v, attr))
                except Exception:
                    pass
        for i, t in enumerate(v.targets):
            nt = nv.targets[i]
            if v.type == "SINGLE_PROP":
                nt.id_type = t.id_type
            tid = t.id
            if tid is not None:
                if new_ctrl is not None and tid == old_ctrl:
                    if copy_missing and v.type == "SINGLE_PROP":
                        n = path_prop_name(t.data_path)
                        if n is not None and n in old_ctrl.keys() and n not in new_ctrl.keys():
                            copy_prop(old_ctrl, new_ctrl, n)
                    tid = new_ctrl
                elif tid == src_owner:
                    tid = dst_id  # self reference follows the copy
            for attr in ("context_property",):
                if hasattr(t, attr):
                    try:
                        setattr(nt, attr, getattr(t, attr))
                    except Exception:
                        pass
            try:
                nt.id = tid
            except Exception:
                pass
            for attr in ("data_path", "bone_target", "transform_type", "transform_space", "rotation_mode"):
                try:
                    setattr(nt, attr, getattr(t, attr))
                except Exception:
                    pass
    # F-Curve shape (keyframes / generator) so mapped drivers keep their curve
    for m in list(new_fc.modifiers):
        new_fc.modifiers.remove(m)
    new_fc.keyframe_points.clear()  # new drivers come with default (0,0)-(1,1) keys
    new_fc.extrapolation = src_fc.extrapolation
    kps = src_fc.keyframe_points
    if len(kps):
        new_fc.keyframe_points.add(len(kps))
        for a, b in zip(kps, new_fc.keyframe_points):
            b.co = a.co
            b.interpolation = a.interpolation
            b.handle_left_type = a.handle_left_type
            b.handle_right_type = a.handle_right_type
            b.handle_left = a.handle_left
            b.handle_right = a.handle_right
    for m in src_fc.modifiers:
        if m.type != "GENERATOR":
            continue
        nm = new_fc.modifiers.new("GENERATOR")
        try:
            nm.mode = m.mode
            nm.use_additive = m.use_additive
            nm.poly_order = m.poly_order
            nm.coefficients = tuple(m.coefficients)
        except Exception:
            pass
    refresh_driver(new_fc)
    return new_fc


def split_owner(obj, path):
    """'data.shape_keys.key_blocks["A"].value' on obj -> (Key, 'key_blocks["A"].value')."""
    sk = getattr(obj.data, "shape_keys", None) if obj.data is not None else None
    if path.startswith("data.shape_keys.") and sk:
        return sk, path[len("data.shape_keys."):]
    if path.startswith("key_blocks") and sk:
        return sk, path
    if path.startswith("data.") and obj.data is not None:
        return obj.data, path[len("data."):]
    if path.startswith("active_material.") and obj.active_material:
        return obj.active_material, path[len("active_material."):]
    return obj, path


# Dynamic enum items must stay referenced from Python.
_ENUM_CACHE = {}


def _controller_items(key, extra):
    items = [(i, n, d, ic, k) for k, (i, n, d, ic) in enumerate(extra)]
    for o in get_controllers():
        items.append((o.name, o.name, "Controller " + o.name, "OUTLINER_OB_EMPTY", len(items)))
    if not items:
        items = [("NONE", "No Controllers", "", "ERROR", 0)]
    _ENUM_CACHE[key] = items
    return items


def ctrl_items(self, context):
    return _controller_items("plain", ())


def ctrl_items_keep(self, context):
    return _controller_items("keep", (("KEEP", "Keep Same Controller", "Do not change the controller", "LINKED"),))


# -----------------------------------------------------------------------------
# Settings / preferences
# -----------------------------------------------------------------------------

class DC_Settings(PropertyGroup):
    ctrl_index: IntProperty(name="Active Controller", default=0)
    prop_filter: StringProperty(name="Driver Filter", description="Only show drivers using this property")
    active_prop: StringProperty(name="Active Property")
    show_vars: BoolProperty(name="Show Variables", default=False)


class DC_Preferences(AddonPreferences):
    bl_idname = __package__ or __name__

    auto_setup: BoolProperty(
        name="Auto-create CONTROLLERS on file load",
        description="Create the CONTROLLERS collection and MainController automatically in every opened file",
        default=True,
    )

    def draw(self, context):
        self.layout.prop(self, "auto_setup")


# -----------------------------------------------------------------------------
# Controller operators
# -----------------------------------------------------------------------------

class DC_OT_setup(Operator):
    bl_idname = "dctrl.setup"
    bl_label = "Create Controllers Setup"
    bl_description = "Create the CONTROLLERS collection and the MainController empty if missing"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        _coll, main = ensure_setup(context.scene)
        set_active_controller(context, main)
        return {"FINISHED"}


class DC_OT_controller_add(Operator):
    bl_idname = "dctrl.controller_add"
    bl_label = "Add Controller"
    bl_description = "Add a new controller empty to the CONTROLLERS collection"
    bl_options = {"REGISTER", "UNDO"}

    name: StringProperty(name="Name", default="Controller")
    display: EnumProperty(
        name="Display",
        items=[(i, n, "") for i, n in (
            ("PLAIN_AXES", "Plain Axes"), ("ARROWS", "Arrows"), ("SPHERE", "Sphere"),
            ("CUBE", "Cube"), ("CIRCLE", "Circle"), ("SINGLE_ARROW", "Single Arrow"),
        )],
        default="PLAIN_AXES",
    )
    at_cursor: BoolProperty(name="At 3D Cursor", default=True)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        coll, _main = ensure_setup(context.scene)
        obj = bpy.data.objects.new(self.name or "Controller", None)
        obj.empty_display_type = self.display
        if self.at_cursor:
            obj.location = context.scene.cursor.location
        coll.objects.link(obj)
        set_active_controller(context, obj)
        return {"FINISHED"}


class DC_OT_controller_duplicate(Operator):
    bl_idname = "dctrl.controller_duplicate"
    bl_label = "Duplicate Controller"
    bl_description = "Duplicate the active controller with all its custom properties"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return active_controller(context) is not None

    def execute(self, context):
        src = active_controller(context)
        coll, _ = ensure_setup(context.scene)
        new = src.copy()
        if new.animation_data:
            new.animation_data_clear()
        coll.objects.link(new)
        set_active_controller(context, new)
        self.report({"INFO"}, f"Duplicated {src.name} -> {new.name}")
        return {"FINISHED"}


class DC_OT_controller_remove(Operator):
    bl_idname = "dctrl.controller_remove"
    bl_label = "Remove Controller"
    bl_description = "Delete the active controller (MainController cannot be removed here)"
    bl_options = {"REGISTER", "UNDO"}

    retarget: BoolProperty(
        name="Move drivers to MainController",
        description="Retarget the drivers using this controller to MainController before deleting it",
        default=True,
    )

    @classmethod
    def poll(cls, context):
        c = active_controller(context)
        return c is not None and c.name != MAIN_NAME

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        c = active_controller(context)
        n = len(controller_drivers(c))
        self.layout.label(text=f"Delete '{c.name}'? ({n} driver(s) use it)", icon="ERROR")
        self.layout.prop(self, "retarget")

    def execute(self, context):
        c = active_controller(context)
        if self.retarget:
            _coll, main = ensure_setup(context.scene)
            for _idb, _ref, fc, _p in controller_drivers(c):
                retarget_fcurve(fc, c, main)
        bpy.data.objects.remove(c, do_unlink=True)
        s = context.scene.dc_settings
        s.ctrl_index = max(0, s.ctrl_index - 1)
        tag_update(context)
        return {"FINISHED"}


class DC_OT_controller_select(Operator):
    bl_idname = "dctrl.controller_select"
    bl_label = "Select Controller"
    bl_description = "Select the active controller in the viewport"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return active_controller(context) is not None

    def execute(self, context):
        c = active_controller(context)
        for o in context.selected_objects:
            o.select_set(False)
        try:
            c.hide_set(False)
            c.select_set(True)
            context.view_layer.objects.active = c
        except RuntimeError:
            self.report({"WARNING"}, f"{c.name} is not in the current view layer")
        return {"FINISHED"}


# -----------------------------------------------------------------------------
# Property operators
# -----------------------------------------------------------------------------

class DC_PropFields:
    """Shared fields for the add / edit property dialogs."""

    ctrl_name: StringProperty(options={"HIDDEN"})
    prop_name: StringProperty(name="Name", default="prop")
    prop_type: EnumProperty(name="Type", items=PROP_TYPES, default="FLOAT")

    float_value: FloatProperty(name="Value", default=0.0)
    int_value: IntProperty(name="Value", default=0)
    bool_value: BoolProperty(name="Value", default=False)
    string_value: StringProperty(name="Value", default="")
    vector_value: FloatVectorProperty(name="Value", size=32)
    int_vector_value: IntVectorProperty(name="Value", size=32)
    array_length: IntProperty(name="Length", default=3, min=1, max=32)
    color_value: FloatVectorProperty(name="Value", size=4, subtype="COLOR", min=0.0, max=1.0, default=(1, 1, 1, 1))
    color_alpha: BoolProperty(name="Alpha", description="Store RGBA instead of RGB", default=False)

    min_value: FloatProperty(name="Min", default=0.0)
    max_value: FloatProperty(name="Max", default=1.0)
    use_soft_limits: BoolProperty(name="Soft Limits", default=False)
    soft_min: FloatProperty(name="Soft Min", default=0.0)
    soft_max: FloatProperty(name="Soft Max", default=1.0)
    step: FloatProperty(name="Step", default=1.0, min=0.001)
    precision: IntProperty(name="Precision", default=3, min=0, max=8)
    float_subtype: EnumProperty(name="Subtype", items=FLOAT_SUBTYPES, default="NONE")
    vector_subtype: EnumProperty(name="Subtype", items=VECTOR_SUBTYPES, default="NONE")
    description: StringProperty(name="Tooltip", default="")
    overridable: BoolProperty(name="Library Overridable", default=True)

    def draw_fields(self, layout):
        layout.use_property_split = True
        layout.use_property_decorate = False
        col = layout.column()
        col.prop(self, "prop_name")
        col.prop(self, "prop_type")
        t = self.prop_type
        col.separator()
        if t == "FLOAT":
            col.prop(self, "float_value")
        elif t == "INT":
            col.prop(self, "int_value")
        elif t == "BOOL":
            col.prop(self, "bool_value")
        elif t == "STRING":
            col.prop(self, "string_value")
        elif t in {"VECTOR", "INT_ARRAY"}:
            col.prop(self, "array_length")
            sub = col.column(align=True)
            field = "vector_value" if t == "VECTOR" else "int_vector_value"
            for i in range(self.array_length):
                sub.prop(self, field, index=i, text="Value" if i == 0 else " ")
        elif t == "COLOR":
            col.prop(self, "color_alpha")
            col.prop(self, "color_value")
        if t in {"FLOAT", "INT", "VECTOR", "INT_ARRAY"}:
            col.separator()
            sub = col.column(align=True)
            sub.prop(self, "min_value")
            sub.prop(self, "max_value")
            col.prop(self, "use_soft_limits")
            if self.use_soft_limits:
                sub = col.column(align=True)
                sub.prop(self, "soft_min")
                sub.prop(self, "soft_max")
            col.prop(self, "step")
            if t in {"FLOAT", "VECTOR"}:
                col.prop(self, "precision")
                col.prop(self, "float_subtype" if t == "FLOAT" else "vector_subtype")
        col.separator()
        col.prop(self, "description")
        col.prop(self, "overridable")

    def fill_from(self, obj, name):
        v = obj[name]
        t = detect_type(obj, name)
        self.prop_name = name
        self.prop_type = t
        self.float_value = convert_value(v, "FLOAT")
        self.int_value = convert_value(v, "INT")
        self.bool_value = convert_value(v, "BOOL")
        self.string_value = convert_value(v, "STRING")
        lst = _as_list(v)
        vec = convert_value(v, "VECTOR", len(lst) if lst else 3)
        self.array_length = max(1, min(32, len(vec)))
        vv = list(self.vector_value)
        vv[: len(vec)] = vec[:32]
        self.vector_value = vv
        iv = list(self.int_vector_value)
        ints = convert_value(v, "INT_ARRAY", len(vec))
        iv[: len(ints)] = ints[:32]
        self.int_vector_value = iv
        col = convert_value(v, "COLOR", 4)
        self.color_value = col
        self.color_alpha = bool(lst) and len(lst) >= 4
        d = ui_dict(obj, name)
        big = 1e30
        self.min_value = max(-big, d.get("min", 0.0))
        self.max_value = min(big, d.get("max", 1.0))
        smin, smax = d.get("soft_min", self.min_value), d.get("soft_max", self.max_value)
        self.soft_min, self.soft_max = max(-big, smin), min(big, smax)
        self.use_soft_limits = (smin, smax) != (d.get("min"), d.get("max"))
        self.step = max(0.001, float(d.get("step", 1.0)))
        self.precision = int(d.get("precision", 3))
        sub = d.get("subtype", "NONE")
        if sub in {i for i, _n, _d in FLOAT_SUBTYPES}:
            self.float_subtype = sub
        if sub in {i for i, _n, _d in VECTOR_SUBTYPES}:
            self.vector_subtype = sub
        self.description = d.get("description", "")
        try:
            self.overridable = obj.is_property_overridable_library(prop_path(name))
        except Exception:
            pass

    def value(self):
        t = self.prop_type
        if t == "FLOAT":
            return float(self.float_value)
        if t == "INT":
            return int(self.int_value)
        if t == "BOOL":
            return bool(self.bool_value)
        if t == "STRING":
            return str(self.string_value)
        if t == "VECTOR":
            return [float(self.vector_value[i]) for i in range(self.array_length)]
        if t == "INT_ARRAY":
            return [int(self.int_vector_value[i]) for i in range(self.array_length)]
        return [float(x) for x in self.color_value[: 4 if self.color_alpha else 3]]

    def apply_ui(self, obj, name, set_default=True):
        t = self.prop_type
        ui = obj.id_properties_ui(name)
        kw = {"description": self.description}
        if set_default:
            v = obj[name]
            lst = _as_list(v)
            kw["default"] = lst if lst is not None else v
        lo, hi = self.min_value, self.max_value
        slo, shi = (self.soft_min, self.soft_max) if self.use_soft_limits else (lo, hi)
        if t in {"FLOAT", "VECTOR"}:
            kw.update(min=lo, max=hi, soft_min=slo, soft_max=shi, step=self.step,
                      precision=self.precision,
                      subtype=self.float_subtype if t == "FLOAT" else self.vector_subtype)
        elif t in {"INT", "INT_ARRAY"}:
            kw.update(min=int(lo), max=int(hi), soft_min=int(slo), soft_max=int(shi), step=max(1, int(self.step)))
        elif t == "COLOR":
            kw.update(min=0.0, max=1.0, soft_min=0.0, soft_max=1.0, subtype="COLOR")
        ui.update(**kw)
        try:
            obj.property_overridable_library_set(prop_path(name), self.overridable)
        except Exception:
            pass


class DC_OT_prop_add(DC_PropFields, Operator):
    bl_idname = "dctrl.prop_add"
    bl_label = "Add Controller Property"
    bl_description = "Add a custom property to the controller"
    bl_options = {"REGISTER", "UNDO"}

    def invoke(self, context, event):
        ctrl = controller_from_name(context, self.ctrl_name)
        if ctrl is None:
            _coll, ctrl = ensure_setup(context.scene)
        self.ctrl_name = ctrl.name
        base, i = "prop", 1
        name = base
        while name in ctrl.keys():
            name = f"{base}_{i}"
            i += 1
        self.prop_name = name
        return context.window_manager.invoke_props_dialog(self, width=320)

    def draw(self, context):
        self.draw_fields(self.layout)

    def execute(self, context):
        ctrl = controller_from_name(context, self.ctrl_name)
        if ctrl is None:
            _coll, ctrl = ensure_setup(context.scene)
        name = self.prop_name.strip()
        if not name:
            self.report({"ERROR"}, "Name is empty")
            return {"CANCELLED"}
        if name in ctrl.keys():
            self.report({"ERROR"}, f"'{name}' already exists on {ctrl.name}")
            return {"CANCELLED"}
        ctrl[name] = self.value()
        self.apply_ui(ctrl, name)
        context.scene.dc_settings.active_prop = name
        tag_update(context)
        return {"FINISHED"}


class DC_OT_prop_edit(DC_PropFields, Operator):
    bl_idname = "dctrl.prop_edit"
    bl_label = "Edit Controller Property"
    bl_description = "Edit name, type, value, limits and tooltip of the property (drivers are kept)"
    bl_options = {"REGISTER", "UNDO"}

    old_name: StringProperty(options={"HIDDEN"})
    set_default: BoolProperty(name="Set Default to Value", default=False,
                              description="Use the current value as the 'Reset to Default' value")

    def invoke(self, context, event):
        ctrl = controller_from_name(context, self.ctrl_name)
        if ctrl is None or self.old_name not in ctrl.keys():
            return {"CANCELLED"}
        self.ctrl_name = ctrl.name
        self.fill_from(ctrl, self.old_name)
        self.set_default = False
        return context.window_manager.invoke_props_dialog(self, width=320)

    def draw(self, context):
        self.draw_fields(self.layout)
        self.layout.prop(self, "set_default")

    def execute(self, context):
        ctrl = controller_from_name(context, self.ctrl_name)
        old = self.old_name
        if ctrl is None or old not in ctrl.keys():
            self.report({"ERROR"}, "Property not found")
            return {"CANCELLED"}
        new = self.prop_name.strip() or old
        if new != old and new in ctrl.keys():
            self.report({"ERROR"}, f"'{new}' already exists")
            return {"CANCELLED"}
        old_type = detect_type(ctrl, old)
        type_changed = old_type != self.prop_type
        order = user_props(ctrl)
        if new != old:
            old_list = _as_list(ctrl[old])
            ctrl[new] = old_list if old_list is not None else ctrl[old]
            try:
                ctrl.id_properties_ui(new).update(**ui_dict(ctrl, old))
            except Exception:
                pass
            del ctrl[old]
            n = rename_prop_in_drivers(ctrl, old, new)
            if n:
                self.report({"INFO"}, f"Renamed '{old}' -> '{new}', updated {n} driver(s)")
        if type_changed:
            # Assigning to an existing ID property converts the value to the OLD
            # type (or raises), so the property must be removed first.
            del ctrl[new]
        ctrl[new] = self.value()
        self.apply_ui(ctrl, new, set_default=self.set_default or type_changed)
        if new != old:
            # the renamed property went to the end: move the ones that followed it after it
            for n in order[order.index(old) + 1:]:
                reinsert_prop(ctrl, n)
        s = context.scene.dc_settings
        s.active_prop = new
        if s.prop_filter == old:
            s.prop_filter = new
        tag_update(context)
        return {"FINISHED"}


class DC_OT_prop_set_type(Operator):
    bl_idname = "dctrl.prop_set_type"
    bl_label = "Change Property Type"
    bl_description = "Change the type of the property, converting its value (drivers are kept)"
    bl_options = {"REGISTER", "UNDO"}

    ctrl_name: StringProperty(options={"HIDDEN"})
    prop_name: StringProperty(options={"HIDDEN"})
    new_type: EnumProperty(name="Type", items=PROP_TYPES)

    def invoke(self, context, event):
        ctrl = controller_from_name(context, self.ctrl_name)
        if ctrl is None or self.prop_name not in ctrl.keys():
            return {"CANCELLED"}
        cname, pname = ctrl.name, self.prop_name
        current = detect_type(ctrl, pname)

        def draw_menu(menu, _ctx):
            lay = menu.layout
            for ident, label, _d in PROP_TYPES:
                op = lay.operator(DC_OT_prop_set_type.bl_idname, text=label, icon=TYPE_ICON[ident],
                                  depress=(ident == current))
                op.ctrl_name = cname
                op.prop_name = pname
                op.new_type = ident

        context.window_manager.popup_menu(draw_menu, title=f"Type of '{pname}'", icon="PROPERTIES")
        return {"FINISHED"}

    def execute(self, context):
        ctrl = controller_from_name(context, self.ctrl_name)
        name = self.prop_name
        if ctrl is None or name not in ctrl.keys():
            return {"CANCELLED"}
        old_type = detect_type(ctrl, name)
        if old_type == self.new_type:
            return {"CANCELLED"}
        old_val = ctrl[name]
        old_list = _as_list(old_val)
        old_ui = ui_dict(ctrl, name)
        length = len(old_list) if old_list else (4 if self.new_type == "COLOR" else 3)
        new_val = convert_value(old_val, self.new_type, length)
        try:
            ovr = ctrl.is_property_overridable_library(prop_path(name))
        except Exception:
            ovr = False
        del ctrl[name]
        ctrl[name] = new_val
        kw = {"description": old_ui.get("description", "")}
        lst = _as_list(ctrl[name])
        kw["default"] = lst if lst is not None else ctrl[name]
        if self.new_type in {"FLOAT", "VECTOR", "INT", "INT_ARRAY"}:
            for k in NUMERIC_UI_KEYS:
                if k in old_ui:
                    kw[k] = old_ui[k]
            if self.new_type in {"INT", "INT_ARRAY"}:
                kw.pop("precision", None)
                for k in ("min", "max", "soft_min", "soft_max"):
                    if k in kw:
                        kw[k] = int(max(-2**31, min(2**31 - 1, kw[k])))
                if "step" in kw:
                    kw["step"] = max(1, int(kw["step"]))
        elif self.new_type == "COLOR":
            kw.update(min=0.0, max=1.0, soft_min=0.0, soft_max=1.0, subtype="COLOR")
        try:
            ctrl.id_properties_ui(name).update(**kw)
        except Exception as e:
            print("Driver Controllers:", e)
        try:
            ctrl.property_overridable_library_set(prop_path(name), ovr)
        except Exception:
            pass
        tag_update(context)
        self.report({"INFO"}, f"'{name}': {TYPE_LABEL[old_type]} -> {TYPE_LABEL[self.new_type]}")
        return {"FINISHED"}


class DC_OT_prop_remove(Operator):
    bl_idname = "dctrl.prop_remove"
    bl_label = "Remove Controller Property"
    bl_description = "Delete the custom property"
    bl_options = {"REGISTER", "UNDO"}

    ctrl_name: StringProperty(options={"HIDDEN"})
    prop_name: StringProperty(options={"HIDDEN"})
    remove_drivers: BoolProperty(name="Also remove the drivers using it", default=False)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        ctrl = controller_from_name(context, self.ctrl_name)
        n = len(controller_drivers(ctrl, self.prop_name)) if ctrl else 0
        self.layout.label(text=f"Delete '{self.prop_name}'? {n} driver(s) use it", icon="ERROR")
        self.layout.prop(self, "remove_drivers")

    def execute(self, context):
        ctrl = controller_from_name(context, self.ctrl_name)
        if ctrl is None or self.prop_name not in ctrl.keys():
            return {"CANCELLED"}
        if self.remove_drivers:
            for idb, _ref, fc, _p in controller_drivers(ctrl, self.prop_name):
                idb.animation_data.drivers.remove(fc)
        del ctrl[self.prop_name]
        _UNLOCKED.discard((ctrl.name, self.prop_name))
        s = context.scene.dc_settings
        if s.prop_filter == self.prop_name:
            s.prop_filter = ""
        tag_update(context)
        return {"FINISHED"}


# Properties whose delete button is unlocked: (controller name, property name).
# Kept in memory only, so everything starts locked again after a restart.
_UNLOCKED = set()


class DC_OT_prop_lock(Operator):
    bl_idname = "dctrl.prop_lock"
    bl_label = "Lock / Unlock Delete"
    bl_description = "Unlock to enable the delete button of this property"

    ctrl_name: StringProperty(options={"HIDDEN"})
    prop_name: StringProperty(options={"HIDDEN"})

    def execute(self, context):
        key = (self.ctrl_name, self.prop_name)
        if key in _UNLOCKED:
            _UNLOCKED.discard(key)
        else:
            _UNLOCKED.add(key)
        for area in context.screen.areas:
            area.tag_redraw()
        return {"FINISHED"}


class DC_OT_prop_select(Operator):
    bl_idname = "dctrl.prop_select"
    bl_label = "Select Property"
    bl_description = "Select this property (the buttons on the right act on it)"

    prop_name: StringProperty(options={"HIDDEN"})

    def execute(self, context):
        s = context.scene.dc_settings
        s.active_prop = self.prop_name
        if s.prop_filter:  # keep the drivers list in sync with the selection
            s.prop_filter = self.prop_name
        return {"FINISHED"}


class DC_OT_prop_filter(Operator):
    bl_idname = "dctrl.prop_filter"
    bl_label = "Show Drivers of Property"
    bl_description = "Show only the drivers that use this property (click again to show all)"

    prop_name: StringProperty(options={"HIDDEN"})

    def execute(self, context):
        s = context.scene.dc_settings
        s.prop_filter = "" if s.prop_filter == self.prop_name else self.prop_name
        return {"FINISHED"}


# -----------------------------------------------------------------------------
# Driver operators
# -----------------------------------------------------------------------------

def setup_controller_driver(fc, ctrl, pname, element=None, mode="DIRECT", expression="var"):
    """Make fc read ctrl[pname] (or ctrl[pname][element] for arrays)."""
    drv = fc.driver
    for v in list(drv.variables):
        drv.variables.remove(v)
    var = drv.variables.new()
    var.name = "var"
    var.type = "SINGLE_PROP"
    t = var.targets[0]
    t.id_type = "OBJECT"
    t.id = ctrl
    t.data_path = prop_path(pname) + (f"[{element}]" if element is not None else "")
    # expression is filled in Direct mode too, so switching to Scripted shows "var"
    drv.expression = (expression or "var") if mode != "DIRECT" else "var"
    drv.type = "AVERAGE" if mode == "DIRECT" else "SCRIPTED"
    refresh_driver(fc)


# Driver "clipboard": the controller property copied with the copy button.
_CLIPBOARD = {"ctrl": "", "prop": ""}


def clipboard_source():
    ctrl = bpy.data.objects.get(_CLIPBOARD["ctrl"])
    if ctrl is None or _CLIPBOARD["prop"] not in ctrl.keys():
        return None, None
    return ctrl, _CLIPBOARD["prop"]


class DC_OT_driver_copy_prop(Operator):
    bl_idname = "dctrl.driver_copy_prop"
    bl_label = "Copy Driver"
    bl_description = ("Copy a driver reading this property. Then right-click any property of any object "
                      "> Paste Controller Driver")

    ctrl_name: StringProperty(options={"HIDDEN"})
    prop_name: StringProperty(options={"HIDDEN"})

    def execute(self, context):
        _CLIPBOARD["ctrl"], _CLIPBOARD["prop"] = self.ctrl_name, self.prop_name
        for area in context.screen.areas:
            area.tag_redraw()
        self.report({"INFO"}, f"Copied driver '{self.prop_name}' – right-click a property > Paste Controller Driver")
        return {"FINISHED"}


def hovered_property(context):
    """(owner ID, data path from the ID, array index) of the right-clicked property, or None."""
    prop = getattr(context, "property", None)
    try:
        ptr, rel, index = prop
    except (TypeError, ValueError):
        return None
    owner = getattr(ptr, "id_data", None)
    if owner is None:
        return None
    full = rel
    if ptr != owner:
        try:
            full = ptr.path_from_id(rel)
        except Exception:
            pass
    return owner, full, index


class DC_OT_driver_paste(Operator):
    bl_idname = "dctrl.driver_paste"
    bl_label = "Paste Controller Driver"
    bl_description = "Drive this property with the copied controller property"
    bl_options = {"REGISTER", "UNDO"}

    all_channels: BoolProperty(name="All Channels", default=False)
    use_selected: BoolProperty(name="Also on Selected Objects", default=False,
                               description="Paste on the same property of every selected object")

    @classmethod
    def poll(cls, context):
        return clipboard_source()[0] is not None and getattr(context, "property", None) is not None

    def execute(self, context):
        ctrl, pname = clipboard_source()
        hovered = hovered_property(context)
        if hovered is None:
            self.report({"ERROR"}, "Right-click the property to drive")
            return {"CANCELLED"}
        owner, full, index = hovered
        return self.paste(context, ctrl, pname, owner, full, index)

    def paste(self, context, ctrl, pname, owner, full, index):
        try:
            is_target_array = not isinstance(owner.path_resolve(full), str) and hasattr(owner.path_resolve(full), "__len__")
        except Exception:
            is_target_array = False
        if not is_target_array:
            idx = -1
        elif self.all_channels or index < 0:
            idx = -1
        else:
            idx = index

        owners = [owner]
        if self.use_selected:
            for o in context.selected_objects:
                dst = counterpart_id(owner, o) if not isinstance(owner, bpy.types.Object) else o
                if dst is not None and dst not in owners and not is_controller(o):
                    owners.append(dst)

        src_len = len(_as_list(ctrl[pname]) or [])
        made = 0
        for own in owners:
            try:
                res = own.driver_add(full, idx)
            except Exception as e:
                self.report({"WARNING"}, f"{own.name}: {e}")
                continue
            for fc in (res if isinstance(res, (list, tuple)) else [res]):
                elem = None
                if src_len:
                    elem = fc.array_index if fc.array_index < src_len else 0
                setup_controller_driver(fc, ctrl, pname, elem)
                made += 1
        tag_update(context)
        self.report({"INFO"}, f"{made} driver(s) now read {ctrl.name} ▸ {pname}")
        return {"FINISHED"} if made else {"CANCELLED"}


def draw_paste_menu(self, context):
    ctrl, pname = clipboard_source()
    hovered = hovered_property(context) if ctrl is not None else None
    if hovered is None:
        return
    owner, full, _i = hovered
    lay = self.layout
    lay.separator()
    lay.operator_context = "EXEC_DEFAULT"
    lay.operator(DC_OT_driver_paste.bl_idname, text=f"Paste Controller Driver ({pname})",
                 icon="DRIVER").all_channels = False
    try:
        v = owner.path_resolve(full)
        is_arr = hasattr(v, "__len__") and not isinstance(v, str)
    except Exception:
        is_arr = False
    if is_arr:
        lay.operator(DC_OT_driver_paste.bl_idname, text="Paste Controller Driver (All Channels)",
                     icon="DRIVER").all_channels = True
    op = lay.operator(DC_OT_driver_paste.bl_idname, text="Paste Controller Driver to Selected", icon="DRIVER")
    op.all_channels = is_arr
    op.use_selected = True


class DC_OT_driver_add(Operator):
    bl_idname = "dctrl.driver_add"
    bl_label = "Add Driver from Controller"
    bl_description = "Drive a property of an object with this controller property"
    bl_options = {"REGISTER", "UNDO"}

    ctrl_name: StringProperty(options={"HIDDEN"})
    prop_name: StringProperty(options={"HIDDEN"})
    target_name: StringProperty(name="Object")
    data_path: StringProperty(
        name="Data Path", default="location",
        description="Path relative to the object, e.g. location, modifiers[\"Bevel\"].width, "
                    "data.shape_keys.key_blocks[\"Smile\"].value, active_material.diffuse_color",
    )
    array_index: IntProperty(name="Index", default=-1, min=-1, description="-1 = all channels")
    element: IntProperty(name="Controller Element", default=0, min=0,
                         description="Which element of the controller array to read")
    match_index: BoolProperty(name="Match Indices", default=True,
                              description="Channel N reads element N of the controller array")
    mode: EnumProperty(name="Mode", items=DRIVER_MODES, default="DIRECT")
    expression: StringProperty(name="Expression", default="var")
    use_selected: BoolProperty(name="Also on Selected Objects", default=False)

    def invoke(self, context, event):
        ob = context.active_object
        if ob is not None and not is_controller(ob):
            self.target_name = ob.name
        return context.window_manager.invoke_props_dialog(self, width=380)

    def draw(self, context):
        lay = self.layout
        lay.use_property_split = True
        lay.use_property_decorate = False
        ctrl = controller_from_name(context, self.ctrl_name)
        lay.label(text=f"Source: {ctrl.name if ctrl else '?'} ▸ {self.prop_name}", icon="DRIVER")
        lay.prop_search(self, "target_name", bpy.data, "objects")
        lay.prop(self, "data_path")
        lay.prop(self, "array_index")
        if ctrl and self.prop_name in ctrl.keys() and _as_list(ctrl[self.prop_name]) is not None:
            lay.prop(self, "match_index")
            if not self.match_index or self.array_index >= 0:
                lay.prop(self, "element")
        lay.prop(self, "mode")
        if self.mode == "SCRIPTED":
            lay.prop(self, "expression")
        lay.prop(self, "use_selected")

    def execute(self, context):
        ctrl = controller_from_name(context, self.ctrl_name)
        if ctrl is None or self.prop_name not in ctrl.keys():
            self.report({"ERROR"}, "Controller property not found")
            return {"CANCELLED"}
        objs = []
        ob = bpy.data.objects.get(self.target_name)
        if ob:
            objs.append(ob)
        if self.use_selected:
            objs += [o for o in context.selected_objects if o not in objs and not is_controller(o)]
        if not objs:
            self.report({"ERROR"}, "No target object")
            return {"CANCELLED"}
        is_array = _as_list(ctrl[self.prop_name]) is not None
        made = 0
        for o in objs:
            owner, rel = split_owner(o, self.data_path.strip())
            try:
                owner.path_resolve(rel)
            except Exception:
                self.report({"WARNING"}, f"{o.name}: path '{self.data_path}' not found, skipped")
                continue
            try:
                res = owner.driver_add(rel, self.array_index)
            except Exception as e:
                self.report({"WARNING"}, f"{o.name}: {e}")
                continue
            fcs = res if isinstance(res, (list, tuple)) else [res]
            for fc in fcs:
                if is_array:
                    elem = fc.array_index if (self.match_index and self.array_index < 0) else self.element
                else:
                    elem = None
                setup_controller_driver(fc, ctrl, self.prop_name, elem, self.mode, self.expression)
                made += 1
        tag_update(context)
        self.report({"INFO"}, f"Created {made} driver(s)")
        return {"FINISHED"} if made else {"CANCELLED"}


class DC_DriverRef:
    """Identifies one driver, or (owner_ref empty) all listed drivers of the controller."""

    ctrl_name: StringProperty(options={"HIDDEN"})
    owner_ref: StringProperty(options={"HIDDEN"})
    data_path: StringProperty(options={"HIDDEN"})
    array_index: IntProperty(options={"HIDDEN"})

    def collect(self, context):
        ctrl = controller_from_name(context, self.ctrl_name)
        if self.owner_ref:
            idb = resolve_ref(self.owner_ref)
            fc = find_fcurve(idb, self.data_path, self.array_index) if idb else None
            return ctrl, ([(idb, fc)] if fc else [])
        flt = context.scene.dc_settings.prop_filter
        return ctrl, [(idb, fc) for idb, _r, fc, _p in controller_drivers(ctrl, flt)]


class DC_OT_driver_remove(DC_DriverRef, Operator):
    bl_idname = "dctrl.driver_remove"
    bl_label = "Remove Driver"
    bl_description = "Remove the driver (without owner: all listed drivers)"
    bl_options = {"REGISTER", "UNDO"}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        _ctrl, items = self.collect(context)
        keys = [(idb, fc.data_path, fc.array_index) for idb, fc in items]
        for idb, path, idx in keys:
            fc = find_fcurve(idb, path, idx)
            if fc:
                idb.animation_data.drivers.remove(fc)
        tag_update(context)
        self.report({"INFO"}, f"Removed {len(keys)} driver(s)")
        return {"FINISHED"}


class DC_OT_driver_copy(DC_DriverRef, Operator):
    bl_idname = "dctrl.driver_copy"
    bl_label = "Copy Driver to Selected"
    bl_description = ("Copy the driver (without owner: all listed drivers) to the selected objects, "
                      "optionally reading from another controller")
    bl_options = {"REGISTER", "UNDO"}

    retarget: EnumProperty(name="Controller", items=ctrl_items_keep,
                           description="Controller the copied drivers will read from")
    copy_missing: BoolProperty(name="Create missing properties", default=True,
                               description="Copy the needed properties to the new controller if it lacks them")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=340)

    def draw(self, context):
        lay = self.layout
        sel = [o for o in context.selected_objects if not is_controller(o)]
        _ctrl, items = self.collect(context)
        lay.label(text=f"{len(items)} driver(s) -> {len(sel)} selected object(s)", icon="COPYDOWN")
        lay.prop(self, "retarget")
        if self.retarget != "KEEP":
            lay.prop(self, "copy_missing")

    def execute(self, context):
        ctrl, items = self.collect(context)
        new_ctrl = None if self.retarget in {"KEEP", "NONE"} else bpy.data.objects.get(self.retarget)
        sel = [o for o in context.selected_objects if not is_controller(o)]
        if not sel:
            self.report({"ERROR"}, "Select the objects to copy the drivers to")
            return {"CANCELLED"}
        done = skipped = 0
        for src_idb, fc in items:
            for o in sel:
                dst = counterpart_id(src_idb, o)
                if dst is None or dst == src_idb:
                    if dst is None:
                        skipped += 1
                    continue
                try:
                    copy_driver(fc, src_idb, dst, ctrl, new_ctrl, self.copy_missing)
                    done += 1
                except Exception as e:
                    skipped += 1
                    print(f"Driver Controllers: {o.name} {fc.data_path}: {e}")
        tag_update(context)
        self.report({"INFO"}, f"Copied {done} driver(s)" + (f", skipped {skipped}" if skipped else ""))
        return {"FINISHED"}


class DC_OT_driver_retarget(DC_DriverRef, Operator):
    bl_idname = "dctrl.driver_retarget"
    bl_label = "Retarget Driver"
    bl_description = "Make the driver (without owner: all listed drivers) read from another controller"
    bl_options = {"REGISTER", "UNDO"}

    target: EnumProperty(name="New Controller", items=ctrl_items)
    copy_missing: BoolProperty(name="Create missing properties", default=True)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        _ctrl, items = self.collect(context)
        self.layout.label(text=f"Retarget {len(items)} driver(s)", icon="DRIVER")
        self.layout.prop(self, "target")
        self.layout.prop(self, "copy_missing")

    def execute(self, context):
        ctrl, items = self.collect(context)
        new = bpy.data.objects.get(self.target)
        if new is None or new == ctrl:
            self.report({"WARNING"}, "Choose a different controller")
            return {"CANCELLED"}
        for _idb, fc in items:
            retarget_fcurve(fc, ctrl, new, self.copy_missing)
        tag_update(context)
        self.report({"INFO"}, f"{len(items)} driver(s) now read from {new.name}")
        return {"FINISHED"}


class DC_OT_driver_select_owner(DC_DriverRef, Operator):
    bl_idname = "dctrl.driver_select_owner"
    bl_label = "Select Driven Object"
    bl_description = "Select the object(s) owning this driver"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        _ctrl, items = self.collect(context)
        objs = []
        for idb, _fc in items:
            objs += [o for o in objects_for_id(idb) if o not in objs]
        if not objs:
            self.report({"WARNING"}, "No object found for this driver")
            return {"CANCELLED"}
        for o in context.selected_objects:
            o.select_set(False)
        for o in objs:
            try:
                o.select_set(True)
            except RuntimeError:
                pass
        if objs[0].name in context.view_layer.objects:
            context.view_layer.objects.active = objs[0]
        return {"FINISHED"}


# -----------------------------------------------------------------------------
# UI
# -----------------------------------------------------------------------------

class DC_UL_controllers(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        ic = "OUTLINER_OB_EMPTY" if item.type == "EMPTY" else "OBJECT_DATA"
        row.prop(item, "name", text="", emboss=False, icon=ic)
        n = len(user_props(item))
        row.label(text=str(n), icon="PROPERTIES")
        row.prop(item, "hide_viewport", text="", emboss=False)


class DC_PT_main(Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Controllers"
    bl_label = "Controllers"

    def draw(self, context):
        lay = self.layout
        if setup_missing(context.scene):
            box = lay.box()
            box.alert = True
            box.label(text="CONTROLLERS / MainController missing", icon="ERROR")
            box.operator(DC_OT_setup.bl_idname, text="Create Setup", icon="ADD")
        coll = get_collection()
        if coll is None:
            return
        s = context.scene.dc_settings
        row = lay.row()
        row.template_list("DC_UL_controllers", "", coll, "objects", s, "ctrl_index", rows=3)
        col = row.column(align=True)
        col.operator(DC_OT_controller_add.bl_idname, text="", icon="ADD")
        col.operator(DC_OT_controller_remove.bl_idname, text="", icon="REMOVE")
        col.separator()
        col.operator(DC_OT_controller_duplicate.bl_idname, text="", icon="DUPLICATE")
        col.operator(DC_OT_controller_select.bl_idname, text="", icon="RESTRICT_SELECT_OFF")


class DC_PT_properties(Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Controllers"
    bl_label = "Properties"
    bl_parent_id = "DC_PT_main"

    @classmethod
    def poll(cls, context):
        return active_controller(context) is not None

    def draw_header(self, context):
        self.layout.label(text="", icon="PROPERTIES")

    def draw(self, context):
        lay = self.layout
        ctrl = active_controller(context)
        s = context.scene.dc_settings

        usage = cached_usage(ctrl)

        names = user_props(ctrl)

        op = lay.operator(DC_OT_prop_add.bl_idname, text="Add Property", icon="ADD")
        op.ctrl_name = ctrl.name

        if not names:
            lay.label(text="No custom properties yet", icon="INFO")
            return

        col = lay.column()  # not aligned -> space between properties
        for name in names:
            t = detect_type(ctrl, name)
            row = col.box().row(align=True)
            # name + value preview
            split = row.split(factor=0.4, align=True)
            split.label(text=name, icon=TYPE_ICON[t])
            split.row(align=True).prop(ctrl, prop_path(name), text="")
            # drivers using it (click = show them in the Drivers panel)
            n = usage.get(name, 0)
            cnt = row.row(align=True)
            cnt.ui_units_x = 2.4
            op = cnt.operator(DC_OT_prop_filter.bl_idname, text=str(n), icon="DECORATE_DRIVER",
                              emboss=False, depress=(s.prop_filter == name))
            op.prop_name = name
            btns = row.row(align=True)
            # edit / copy ... then delete, kept apart so it is not hit by mistake
            op = btns.operator(DC_OT_prop_edit.bl_idname, text="", icon="GREASEPENCIL")
            op.ctrl_name, op.old_name = ctrl.name, name
            copied = _CLIPBOARD["ctrl"] == ctrl.name and _CLIPBOARD["prop"] == name
            op = btns.operator(DC_OT_driver_copy_prop.bl_idname, text="", icon="COPYDOWN", depress=copied)
            op.ctrl_name, op.prop_name = ctrl.name, name
            row.separator(factor=2.0)
            unlocked = (ctrl.name, name) in _UNLOCKED
            dele = row.row(align=True)
            op = dele.operator(DC_OT_prop_lock.bl_idname, text="",
                               icon="UNLOCKED" if unlocked else "LOCKED", depress=unlocked)
            op.ctrl_name, op.prop_name = ctrl.name, name
            bin_ = dele.row(align=True)
            bin_.enabled = unlocked
            bin_.alert = unlocked
            op = bin_.operator(DC_OT_prop_remove.bl_idname, text="", icon="TRASH")
            op.ctrl_name, op.prop_name = ctrl.name, name

        src, pname = clipboard_source()
        if src is not None:
            box = lay.box().column(align=True)
            box.label(text=f"Copied: {src.name} ▸ {pname}", icon="PASTEDOWN")
            box.label(text="Right-click a property > Paste Controller Driver")


class DC_PT_drivers(Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Controllers"
    bl_label = "Drivers"
    bl_parent_id = "DC_PT_main"

    @classmethod
    def poll(cls, context):
        return active_controller(context) is not None

    def draw_header(self, context):
        self.layout.label(text="", icon="DRIVER")

    def draw(self, context):
        lay = self.layout
        ctrl = active_controller(context)
        s = context.scene.dc_settings
        items = cached_controller_drivers(ctrl, s.prop_filter)

        row = lay.row(align=True)
        if s.prop_filter:
            row.label(text=f"Using '{s.prop_filter}': {len(items)}", icon="FILTER")
            op = row.operator(DC_OT_prop_filter.bl_idname, text="", icon="X")
            op.prop_name = s.prop_filter
        else:
            row.label(text=f"Using {ctrl.name}: {len(items)}")
        row.prop(s, "show_vars", text="", icon="VIEWZOOM")

        if s.prop_filter:
            op = lay.operator(DC_OT_driver_add.bl_idname, text=f"Add Driver from '{s.prop_filter}'", icon="ADD")
            op.ctrl_name, op.prop_name = ctrl.name, s.prop_filter

        if not items:
            lay.label(text="No drivers read this controller", icon="INFO")
            return

        row = lay.row(align=True)
        for idname, text, icon in (
            (DC_OT_driver_copy.bl_idname, "Copy to Sel.", "COPYDOWN"),
            (DC_OT_driver_retarget.bl_idname, "Retarget", "LINKED"),
            (DC_OT_driver_select_owner.bl_idname, "", "RESTRICT_SELECT_OFF"),
            (DC_OT_driver_remove.bl_idname, "", "TRASH"),
        ):
            op = row.operator(idname, text=text, icon=icon)
            op.ctrl_name, op.owner_ref = ctrl.name, ""

        for idb, ref, fc, props in items:
            drv = fc.driver
            box = lay.box()
            r = box.row(align=True)
            r.alert = not drv.is_valid
            idx = f"[{fc.array_index}]" if _is_array_path(idb, fc) else ""
            label = f"{idb.name} ▸ {fc.data_path}{idx}"
            r.label(text=label, icon="ERROR" if not drv.is_valid else ID_ICON.get(idb.id_type, "DOT"))
            for idname, icon in (
                (DC_OT_driver_select_owner.bl_idname, "RESTRICT_SELECT_OFF"),
                (DC_OT_driver_copy.bl_idname, "COPYDOWN"),
                (DC_OT_driver_retarget.bl_idname, "LINKED"),
                (DC_OT_driver_remove.bl_idname, "X"),
            ):
                op = r.operator(idname, text="", icon=icon, emboss=False)
                op.ctrl_name, op.owner_ref = ctrl.name, ref
                op.data_path, op.array_index = fc.data_path, fc.array_index
            r = box.row(align=True)
            r.prop(drv, "type", text="")
            if drv.type == "SCRIPTED":
                r.prop(drv, "expression", text="")
            else:
                r.label(text=", ".join(sorted(p for p in props if p)) or "transform")
            res = r.row(align=True)
            res.ui_units_x = 3.5
            res.alert = not drv.is_valid
            res.label(text="= " + driven_value_text(idb, fc))
            if s.show_vars:
                vcol = box.column(align=True)
                for var in drv.variables:
                    vr = vcol.row(align=True)
                    vr.prop(var, "name", text="")
                    vr.prop(var, "type", text="", icon_only=True)
                    if var.type == "SINGLE_PROP":
                        t = var.targets[0]
                        vr.prop(t, "id", text="")
                        vr.prop(t, "data_path", text="")
                    elif var.type == "TRANSFORMS":
                        t = var.targets[0]
                        vr.prop(t, "id", text="")
                        vr.prop(t, "transform_type", text="")
                    else:
                        for t in var.targets:
                            vr.prop(t, "id", text="")


def driven_value_text(idb, fc):
    """Current value of the driven property (the driver's result)."""
    try:
        v = idb.path_resolve(fc.data_path)
        if hasattr(v, "__len__") and not isinstance(v, str):
            v = v[fc.array_index]
    except Exception:
        return "?"
    if isinstance(v, bool):
        return "True" if v else "False"
    if isinstance(v, float):
        return "%.3f" % v
    return str(v)


def _is_array_path(idb, fc):
    try:
        v = idb.path_resolve(fc.data_path)
        return hasattr(v, "__len__") and not isinstance(v, str)
    except Exception:
        return fc.array_index > 0


# -----------------------------------------------------------------------------
# Registration
# -----------------------------------------------------------------------------

# --- Keep a ready-to-use expression ("var") on controller drivers -------------
# Blender keeps an old/empty expression on non-scripted drivers, so switching
# "Averaged Value" -> "Scripted Expression" would show something useless.

_MSGBUS_OWNER = object()
_LAST_TYPES = {}


def default_expression(drv):
    names = [v.name for v in drv.variables]
    if not names:
        return "0.0"
    if len(names) == 1:
        return names[0]
    if drv.type == "SUM":
        return " + ".join(names)
    return "(" + " + ".join(names) + f") / {len(names)}"


def expression_uses_vars(drv):
    expr = drv.expression or ""
    return any(re.search(r"\b%s\b" % re.escape(v.name), expr) for v in drv.variables)


def _reads_any(drv, ptrs):
    for var in drv.variables:
        for t in var.targets:
            tid = t.id
            if tid is not None and tid.as_pointer() in ptrs:
                return True
    return False


def sync_expressions(refresh_invalid=False):
    """One pass over the drivers that read a controller:
    pre-fill expressions of non-scripted ones, fix the ones just switched to
    Scripted without a usable expression, optionally re-enable invalid ones."""
    ptrs = {o.as_pointer() for o in get_controllers()}
    if not ptrs:
        return
    seen = set()
    for idb, _ref, fc in iter_drivers():
        drv = fc.driver
        if not _reads_any(drv, ptrs):
            continue
        if refresh_invalid and not drv.is_valid:
            refresh_driver(fc)
        key = (idb.as_pointer(), fc.data_path, fc.array_index)
        seen.add(key)
        prev = _LAST_TYPES.get(key)
        just_switched = drv.type == "SCRIPTED" and prev is not None and prev != "SCRIPTED"
        if (drv.type != "SCRIPTED" or just_switched) and not expression_uses_vars(drv):
            try:
                drv.expression = default_expression(drv)
            except Exception:
                pass
        _LAST_TYPES[key] = drv.type
    for k in list(_LAST_TYPES):
        if k not in seen:
            del _LAST_TYPES[k]


def _on_driver_type_changed(*_args):
    try:
        sync_expressions()
    except Exception as e:
        print("Driver Controllers:", e)


def subscribe_msgbus():
    bpy.msgbus.clear_by_owner(_MSGBUS_OWNER)
    bpy.msgbus.subscribe_rna(key=(bpy.types.Driver, "type"), owner=_MSGBUS_OWNER,
                             args=(), notify=_on_driver_type_changed)


@persistent
def _on_load(_dummy):
    prefs = addon_prefs()
    if prefs is None or prefs.auto_setup:
        try:
            ensure_setup(bpy.context.scene)
        except Exception as e:
            print("Driver Controllers: setup failed:", e)
    _LAST_TYPES.clear()
    invalidate_index()
    subscribe_msgbus()  # msgbus subscriptions are cleared when a file loads
    _on_driver_type_changed()


@persistent
def _on_undo_redo(*_args):
    # undo/redo rebuilds all data: memory addresses change
    _LAST_TYPES.clear()
    invalidate_index()


_HANDLERS = (
    ("load_post", _on_load),
    ("depsgraph_update_post", _on_depsgraph_update),
    ("undo_post", _on_undo_redo),
    ("redo_post", _on_undo_redo),
)


def _initial_setup():
    _on_load(None)
    return None


classes = (
    DC_Settings,
    DC_Preferences,
    DC_OT_setup,
    DC_OT_controller_add,
    DC_OT_controller_duplicate,
    DC_OT_controller_remove,
    DC_OT_controller_select,
    DC_OT_prop_add,
    DC_OT_prop_edit,
    DC_OT_prop_set_type,
    DC_OT_prop_remove,
    DC_OT_prop_lock,
    DC_OT_prop_select,
    DC_OT_prop_filter,
    DC_OT_driver_copy_prop,
    DC_OT_driver_paste,
    DC_OT_driver_add,
    DC_OT_driver_remove,
    DC_OT_driver_copy,
    DC_OT_driver_retarget,
    DC_OT_driver_select_owner,
    DC_UL_controllers,
    DC_PT_main,
    DC_PT_properties,
    DC_PT_drivers,
)


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.dc_settings = PointerProperty(type=DC_Settings)
    bpy.types.UI_MT_button_context_menu.append(draw_paste_menu)
    for name, fn in _HANDLERS:
        lst = getattr(bpy.app.handlers, name)
        if fn not in lst:
            lst.append(fn)
    bpy.app.timers.register(_initial_setup, first_interval=0.2)


def unregister():
    bpy.msgbus.clear_by_owner(_MSGBUS_OWNER)
    bpy.types.UI_MT_button_context_menu.remove(draw_paste_menu)
    for name, fn in _HANDLERS:
        lst = getattr(bpy.app.handlers, name)
        if fn in lst:
            lst.remove(fn)
    if bpy.app.timers.is_registered(_initial_setup):
        bpy.app.timers.unregister(_initial_setup)
    del bpy.types.Scene.dc_settings
    for c in reversed(classes):
        bpy.utils.unregister_class(c)


if __name__ == "__main__":
    register()
