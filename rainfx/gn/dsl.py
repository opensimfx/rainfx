"""A small builder DSL over ``bpy`` node trees.

Design rules:
* Sockets are looked up by *name among enabled sockets*, never by identifier.
  Identifiers of Compare / Random Value changed in Blender 5.2 and are
  type-suffixed (``A_VEC3``), so name lookup is the stable contract.
* Any argument may be a socket (linked) or a constant (assigned).
"""
from __future__ import annotations

import bpy

NodeSocket = bpy.types.NodeSocket


class B:
    def __init__(self, tree: bpy.types.NodeTree):
        self.tree = tree
        self.nodes = tree.nodes
        self.links = tree.links
        self._i = 0

    # ------------------------------------------------------------------ plumbing
    def node(self, idname: str, **props):
        n = self.nodes.new(idname)
        for k, v in props.items():
            setattr(n, k, v)
        n.location = ((self._i % 14) * 190, -(self._i // 14) * 220)
        self._i += 1
        return n

    @staticmethod
    def sin(node, name: str):
        for s in node.inputs:
            if s.name == name and s.enabled:
                return s
        raise KeyError(f"{node.bl_idname} has no enabled input '{name}'")

    @staticmethod
    def sout(node, name: str):
        for s in node.outputs:
            if s.name == name and s.enabled:
                return s
        raise KeyError(f"{node.bl_idname} has no enabled output '{name}'")

    def put(self, sock: NodeSocket, v):
        if isinstance(v, NodeSocket):
            self.links.new(v, sock)
        elif v is not None:
            try:
                sock.default_value = v
            except TypeError:
                sock.default_value = tuple(v)
        return sock

    # ---------------------------------------------------------------- scalar math
    def fm(self, op, a, b=None, c=None, clamp=False):
        n = self.node("ShaderNodeMath", operation=op)
        n.use_clamp = clamp
        self.put(n.inputs[0], a)
        if b is not None:
            self.put(n.inputs[1], b)
        if c is not None:
            self.put(n.inputs[2], c)
        return n.outputs[0]

    def cmp(self, op, a, b, dtype="FLOAT"):
        n = self.node("FunctionNodeCompare", data_type=dtype, operation=op)
        self.put(self.sin(n, "A"), a)
        self.put(self.sin(n, "B"), b)
        return self.sout(n, "Result")

    def bool(self, op, a, b=None):
        n = self.node("FunctionNodeBooleanMath", operation=op)
        self.put(n.inputs[0], a)
        if b is not None:
            self.put(n.inputs[1], b)
        return n.outputs[0]

    # --------------------------------------------------------------- vector math
    def vm(self, op, a, b=None, c=None):
        n = self.node("ShaderNodeVectorMath", operation=op)
        self.put(n.inputs[0], a)
        if b is not None:
            self.put(n.inputs[1], b)
        if c is not None:
            self.put(n.inputs[2], c)
        return n.outputs[0]

    def vscale(self, a, s):
        n = self.node("ShaderNodeVectorMath", operation="SCALE")
        self.put(n.inputs[0], a)
        self.put(n.inputs[3], s)
        return n.outputs[0]

    def vdot(self, a, b):
        n = self.node("ShaderNodeVectorMath", operation="DOT_PRODUCT")
        self.put(n.inputs[0], a)
        self.put(n.inputs[1], b)
        return n.outputs[1]

    def vlen(self, a):
        n = self.node("ShaderNodeVectorMath", operation="LENGTH")
        self.put(n.inputs[0], a)
        return n.outputs[1]

    def xyz(self, x, y, z):
        n = self.node("ShaderNodeCombineXYZ")
        self.put(n.inputs[0], x)
        self.put(n.inputs[1], y)
        self.put(n.inputs[2], z)
        return n.outputs[0]

    def sep(self, v):
        n = self.node("ShaderNodeSeparateXYZ")
        self.put(n.inputs[0], v)
        return n.outputs[0], n.outputs[1], n.outputs[2]

    def mix(self, fac, a, b, dtype="VECTOR"):
        n = self.node("ShaderNodeMix", data_type=dtype)
        self.put(self.sin(n, "Factor"), fac)
        self.put(self.sin(n, "A"), a)
        self.put(self.sin(n, "B"), b)
        return self.sout(n, "Result")

    # -------------------------------------------------------------------- random
    def rand(self, lo, hi, seed, dtype="FLOAT"):
        n = self.node("FunctionNodeRandomValue", data_type=dtype)
        self.put(self.sin(n, "Min"), lo)
        self.put(self.sin(n, "Max"), hi)
        self.put(self.sin(n, "Seed"), seed)
        return self.sout(n, "Value")

    # ---------------------------------------------------------------- attributes
    def attr(self, name: str, dtype="FLOAT"):
        n = self.node("GeometryNodeInputNamedAttribute", data_type=dtype)
        self.put(n.inputs["Name"], name)
        return self.sout(n, "Attribute")

    def store(self, geo, name: str, value, dtype="FLOAT", domain="POINT", sel=None):
        n = self.node("GeometryNodeStoreNamedAttribute", data_type=dtype, domain=domain)
        self.put(n.inputs["Geometry"], geo)
        if sel is not None:
            self.put(n.inputs["Selection"], sel)
        self.put(n.inputs["Name"], name)
        self.put(self.sin(n, "Value"), value)
        return n.outputs["Geometry"]

    # ------------------------------------------------------------- geometry ops
    def switch_geo(self, cond, false_geo, true_geo):
        n = self.node("GeometryNodeSwitch", input_type="GEOMETRY")
        self.put(n.inputs["Switch"], cond)
        self.put(n.inputs["False"], false_geo)
        self.put(n.inputs["True"], true_geo)
        return n.outputs["Output"]

    def join(self, *geos):
        n = self.node("GeometryNodeJoinGeometry")
        for g in geos:
            self.links.new(g, n.inputs[0])
        return n.outputs["Geometry"]

    def set_position(self, geo, position=None, offset=None, sel=None):
        n = self.node("GeometryNodeSetPosition")
        self.put(n.inputs["Geometry"], geo)
        if sel is not None:
            self.put(n.inputs["Selection"], sel)
        if position is not None:
            self.put(n.inputs["Position"], position)
        if offset is not None:
            self.put(n.inputs["Offset"], offset)
        return n.outputs["Geometry"]

    def separate(self, geo, selection, domain="POINT"):
        n = self.node("GeometryNodeSeparateGeometry", domain=domain)
        self.put(n.inputs["Geometry"], geo)
        self.put(n.inputs["Selection"], selection)
        return n.outputs["Selection"], n.outputs["Inverted"]

    def delete(self, geo, selection, domain="POINT"):
        n = self.node("GeometryNodeDeleteGeometry", domain=domain)
        self.put(n.inputs["Geometry"], geo)
        self.put(n.inputs["Selection"], selection)
        return n.outputs["Geometry"]

    # ------------------------------------------------------------- interface
    def panel(self, name: str, closed=False):
        return self.tree.interface.new_panel(name, default_closed=closed)

    def add_input(self, name, stype, default=None, lo=None, hi=None, parent=None, desc=""):
        s = self.tree.interface.new_socket(name=name, in_out="INPUT", socket_type=stype,
                                           parent=parent)
        if default is not None:
            s.default_value = default
        if lo is not None:
            s.min_value = lo
        if hi is not None:
            s.max_value = hi
        if desc:
            s.description = desc
        return s
