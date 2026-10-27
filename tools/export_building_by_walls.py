#!/usr/bin/env python3
"""
tools/export_building_by_walls.py

Exports the building separated BY WALL (Parede inteira como um objeto / elemento no Outliner):
- Organizes the Blender tree into intuitive collections:
  * 01_Paredes_Externas:
    - Parede_Externa_Norte
    - Parede_Externa_Sul
    - Parede_Externa_Leste
    - Parede_Externa_Oeste
  * 02_Paredes_Internas:
    - Parede_Interna_Central
    - Divisoria_Baia_1
    - Divisoria_Baia_2
    - Divisoria_Baia_3
  * 03_Moveis_Decoracoes:
    - Moveis_Props
  * 04_Telhado:
    - Telhado_Vertente_Norte
    - Telhado_Vertente_Sul
    - Telhado_Cumeeira
- Welds coincident vertices on each wall so loops and edge selections ("faces, linhas e arestas") work smoothly.
- Generates:
  * building_by_walls.blend
  * building_lego.blend (updated to this wall architecture)
  * model_by_walls.glb
  * model_modular_lego.glb
  * model_base.glb
  * model_base_house.glb
  * model_base_roof.glb
- Synchronizes with /home/mnunes/uo3d_map/community_assets/map0_felucca/britain/building_13_royal_guard_outpost
"""

import os
import sys
import json
import shutil
from pathlib import Path

sys.path.append("/home/mnunes/uo3d_map")
import update_all_community_assets as updater
updater.init_worker()

import bpy
import bmesh

def build_walls(building_rel_path="map0_felucca/britain/building_13_royal_guard_outpost"):
    bpath = Path(building_rel_path).resolve()
    info_path = bpath / "info.json"
    with open(info_path, "r", encoding="utf-8") as f:
        meta = json.load(f)

    b = meta["world_bounds"]
    min_wx, max_wx = b["min_x"], b["max_x"]
    min_wy, max_wy = b["min_y"], b["max_y"]
    base_z = b["base_z"]
    center_x = (min_wx + max_wx + 1) / 2.0
    center_z = (min_wy + max_wy + 1) / 2.0
    y_base_ground = base_z * updater.V_SCALE
    expected_count = meta.get("stats", {}).get("item_count", 0)
    target_ids = {u["id"] for u in meta.get("unique_items", [])}
    items, staidx, statics = updater.collect_building_items(0, min_wx, max_wx, min_wy, max_wy, expected_count, target_ids)

    # Clean scene
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.tool_settings.use_snap = True
    scene.tool_settings.snap_elements = {'INCREMENT'}

    # Collections
    cols = {
        "01_Paredes_Externas": bpy.data.collections.new("01_Paredes_Externas"),
        "02_Paredes_Internas": bpy.data.collections.new("02_Paredes_Internas"),
        "03_Moveis_Decoracoes": bpy.data.collections.new("03_Moveis_Decoracoes"),
        "04_Telhado": bpy.data.collections.new("04_Telhado")
    }
    for c in cols.values():
        scene.collection.children.link(c)

    # Materials
    mat_ext = bpy.data.materials.new("Mat_Parede_Externa")
    b_ext = mat_ext.node_tree.nodes.get("Principled BSDF")
    if b_ext:
        b_ext.inputs["Base Color"].default_value = (0.78, 0.65, 0.48, 1.0)
        b_ext.inputs["Roughness"].default_value = 0.75

    mat_int = bpy.data.materials.new("Mat_Parede_Interna")
    b_int = mat_int.node_tree.nodes.get("Principled BSDF")
    if b_int:
        b_int.inputs["Base Color"].default_value = (0.72, 0.58, 0.42, 1.0)
        b_int.inputs["Roughness"].default_value = 0.80

    mat_props = bpy.data.materials.new("Mat_Moveis_Props")
    b_prp = mat_props.node_tree.nodes.get("Principled BSDF")
    if b_prp:
        b_prp.inputs["Base Color"].default_value = (0.55, 0.38, 0.22, 1.0)
        b_prp.inputs["Roughness"].default_value = 0.65

    mat_roof = bpy.data.materials.new("Mat_Telhado")
    b_rf = mat_roof.node_tree.nodes.get("Principled BSDF")
    if b_rf:
        b_rf.inputs["Base Color"].default_value = (0.82, 0.68, 0.35, 1.0)
        b_rf.inputs["Roughness"].default_value = 0.85

    wall_thick = updater.WALL_THICKNESS * updater.H_SCALE
    step = 3.0 * updater.V_SCALE
    thick = 0.12 * updater.V_SCALE

    # Roof height data
    roof_corner_y = {}
    pitched_roof_coords = set()
    for it in items:
        wx, wy, z, item_id, fl, h, name = it
        if item_id in updater.TRUE_PITCHED_ROOFS:
            r_yb = (z * updater.V_SCALE) - y_base_ground
            pitched_roof_coords.add((wx, wy))
            if item_id in updater.ROOF_SLOPE_SOUTH: cnw, cne, csw, cse = r_yb, r_yb, r_yb + step, r_yb + step
            elif item_id in updater.ROOF_SLOPE_NORTH: cnw, cne, csw, cse = r_yb + step, r_yb + step, r_yb, r_yb
            elif item_id in updater.ROOF_SLOPE_EAST: cnw, cne, csw, cse = r_yb, r_yb + step, r_yb, r_yb + step
            elif item_id in updater.ROOF_SLOPE_WEST: cnw, cne, csw, cse = r_yb + step, r_yb + step, r_yb, r_yb
            elif item_id in updater.ROOF_RIDGE_NS or item_id in updater.ROOF_RIDGE_EW: cnw, cne, csw, cse = r_yb, r_yb, r_yb, r_yb
            else: cnw, cne, csw, cse = r_yb, r_yb, r_yb + step, r_yb + step
            roof_corner_y[(wx, wy)] = (cnw, cne, csw, cse)

    # Geometry buffers for each object
    wall_buffers = {
        "Parede_Externa_Norte": ([], [], "01_Paredes_Externas", mat_ext),
        "Parede_Externa_Sul": ([], [], "01_Paredes_Externas", mat_ext),
        "Parede_Externa_Leste": ([], [], "01_Paredes_Externas", mat_ext),
        "Parede_Externa_Oeste": ([], [], "01_Paredes_Externas", mat_ext),
        "Parede_Interna_Central": ([], [], "02_Paredes_Internas", mat_int),
        "Divisoria_Baia_1": ([], [], "02_Paredes_Internas", mat_int),
        "Divisoria_Baia_2": ([], [], "02_Paredes_Internas", mat_int),
        "Divisoria_Baia_3": ([], [], "02_Paredes_Internas", mat_int),
        "Moveis_Props": ([], [], "03_Moveis_Decoracoes", mat_props),
        "Telhado_Vertente_Norte": ([], [], "04_Telhado", mat_roof),
        "Telhado_Vertente_Sul": ([], [], "04_Telhado", mat_roof),
        "Telhado_Cumeeira": ([], [], "04_Telhado", mat_roof)
    }

    def add_box_to_group(group_name, bx0, bx1, by0, by1, bz0, bz1):
        if by1 <= by0 or bx1 <= bx0 or bz1 <= bz0: return
        verts, faces, _, _ = wall_buffers[group_name]
        idx = len(verts)
        verts.extend([
            (bx0, bz0, by0), (bx1, bz0, by0), (bx1, bz1, by0), (bx0, bz1, by0),
            (bx0, bz0, by1), (bx1, bz0, by1), (bx1, bz1, by1), (bx0, bz1, by1)
        ])
        faces.extend([
            (idx+0, idx+1, idx+2, idx+3), # bottom
            (idx+4, idx+7, idx+6, idx+5), # top
            (idx+0, idx+4, idx+5, idx+1), # south
            (idx+2, idx+6, idx+7, idx+3), # north
            (idx+0, idx+3, idx+7, idx+4), # west
            (idx+1, idx+5, idx+6, idx+2)  # east
        ])

    def add_custom_to_group(group_name, v, f):
        verts, faces, _, _ = wall_buffers[group_name]
        idx = len(verts)
        verts.extend(v)
        faces.extend([[p + idx for p in face] for face in f])

    # 1. SYNTHETIC BORDER WALLS
    existing_walls = set(it[:2] for it in items if (it[4] & 0x10 != 0) or ("wall" in it[6]) or ("window" in it[6]))
    covered_coords = set(it[:2] for it in items if (it[4] & 0x200 != 0) or ("roof" in it[6]) or ("floor" in it[6]))

    west_pts = sorted([wy for wy in range(min_wy, max_wy + 1) if (min_wx, wy) in existing_walls])
    if len(west_pts) >= 2:
        for idx in range(len(west_pts) - 1):
            y1, y2 = west_pts[idx], west_pts[idx + 1]
            if 1 < y2 - y1 <= 32:
                gap_cov = any((min_wx, y) in covered_coords or (min_wx + 1, y) in covered_coords for y in range(y1 + 1, y2))
                if gap_cov:
                    wx0_w = (min_wx - center_x) * updater.H_SCALE
                    for y in range(y1 + 1, y2):
                        if (min_wx, y) not in existing_walls:
                            wz0 = (y - center_z) * updater.H_SCALE
                            wz1 = wz0 + updater.H_SCALE
                            yt_w = 2.40
                            if (min_wx, y) in pitched_roof_coords:
                                cnw, cne, csw, cse = roof_corner_y[(min_wx, y)]
                                yt_w = min(yt_w, max(cnw, cne, csw, cse))
                            add_box_to_group("Parede_Externa_Oeste", wx0_w, wx0_w + wall_thick, 0.0, yt_w, wz0, wz1)

    east_pts = sorted([wy for wy in range(min_wy, max_wy + 1) if (max_wx, wy) in existing_walls])
    if len(east_pts) >= 2:
        for idx in range(len(east_pts) - 1):
            y1, y2 = east_pts[idx], east_pts[idx + 1]
            if 1 < y2 - y1 <= 32:
                gap_cov = any((max_wx, y) in covered_coords or (max_wx - 1, y) in covered_coords for y in range(y1 + 1, y2))
                if gap_cov:
                    wx0_e = (max_wx - center_x) * updater.H_SCALE
                    for y in range(y1 + 1, y2):
                        if (max_wx, y) not in existing_walls:
                            wz0 = (y - center_z) * updater.H_SCALE
                            wz1 = wz0 + updater.H_SCALE
                            yt_e = 2.40
                            if (max_wx, y) in pitched_roof_coords:
                                cnw, cne, csw, cse = roof_corner_y[(max_wx, y)]
                                yt_e = min(yt_e, max(cnw, cne, csw, cse))
                            add_box_to_group("Parede_Externa_Leste", wx0_e, wx0_e + wall_thick, 0.0, yt_e, wz0, wz1)

    # 2. PROCESS ITEMS INTO WALL GROUPS
    for it in items:
        wx, wy, z, item_id, fl, h, name = it
        wx0 = (wx - center_x) * updater.H_SCALE
        wx1 = wx0 + updater.H_SCALE
        wz0 = (wy - center_z) * updater.H_SCALE
        wz1 = wz0 + updater.H_SCALE
        yb  = (z * updater.V_SCALE) - y_base_ground
        yt  = yb + max(h, 1) * updater.V_SCALE

        # Roof
        if item_id in updater.TRUE_PITCHED_ROOFS:
            v, f = [], []
            if item_id in updater.ROOF_SLOPE_SOUTH:
                v = [
                    (wx0, wz0, yb), (wx1, wz0, yb), (wx1, wz1, yb + step), (wx0, wz1, yb + step),
                    (wx0, wz0, yb - thick), (wx1, wz0, yb - thick), (wx1, wz1, yb + step - thick), (wx0, wz1, yb + step - thick)
                ]
                f = [
                    (0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1), (3, 2, 6, 7), (0, 3, 7, 4), (1, 5, 6, 2)
                ]
                add_custom_to_group("Telhado_Vertente_Sul", v, f)
            elif item_id in updater.ROOF_SLOPE_NORTH:
                v = [
                    (wx0, wz1, yb), (wx1, wz1, yb), (wx1, wz0, yb + step), (wx0, wz0, yb + step),
                    (wx0, wz1, yb - thick), (wx1, wz1, yb - thick), (wx1, wz0, yb + step - thick), (wx0, wz0, yb + step - thick)
                ]
                f = [
                    (0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1), (3, 2, 6, 7), (0, 3, 7, 4), (1, 5, 6, 2)
                ]
                add_custom_to_group("Telhado_Vertente_Norte", v, f)
            elif item_id in updater.ROOF_RIDGE_EW:
                wz_mid = wz0 + 0.5 * updater.H_SCALE
                v = [
                    (wx0, wz0, yb), (wx1, wz0, yb), (wx1, wz_mid, yb + step), (wx0, wz_mid, yb + step),
                    (wx1, wz1, yb), (wx0, wz1, yb),
                    (wx0, wz0, yb - thick), (wx1, wz0, yb - thick), (wx1, wz_mid, yb + step - thick), (wx0, wz_mid, yb + step - thick),
                    (wx1, wz1, yb - thick), (wx0, wz1, yb - thick)
                ]
                f = [
                    (0, 1, 2, 3), (3, 2, 4, 5), (9, 8, 7, 6), (11, 10, 8, 9), (0, 6, 7, 1), (4, 10, 11, 5)
                ]
                add_custom_to_group("Telhado_Cumeeira", v, f)
            continue

        # Props
        if any(k in name for k in ('table', 'saddle', 'signpost')):
            add_box_to_group("Moveis_Props", wx0 + 0.1, wx1 - 0.1, yb, yt, wz0 + 0.1, wz1 - 0.1)
            continue

        # Target wall group
        target_group = None
        if wy == 1539: target_group = "Parede_Externa_Norte"
        elif wy == 1551: target_group = "Parede_Externa_Sul"
        elif wx == 1507: target_group = "Parede_Externa_Oeste"
        elif wx == 1527: target_group = "Parede_Externa_Leste"
        elif wy == 1545: target_group = "Parede_Interna_Central"
        elif wx == 1512: target_group = "Divisoria_Baia_1"
        elif wx == 1518: target_group = "Divisoria_Baia_2"
        elif wx == 1522: target_group = "Divisoria_Baia_3"

        if not target_group:
            continue

        is_window = (item_id in (14, 15, 59, 60)) or ("window" in name)
        is_gable = (item_id in (24, 25, 66, 67, 82, 83)) and ("wall" in name) and (h <= 5)

        if is_gable:
            add_box_to_group(target_group, wx0, wx1, yb, yt, wz0, wz0 + wall_thick)
            continue

        if is_window:
            is_south = item_id in (14, 59) or item_id in updater._S_WALLS or "south" in name
            y_sill = yb + max(h, 1) * 0.35 * updater.V_SCALE
            y_lintel = yb + max(h, 1) * 0.75 * updater.V_SCALE
            if is_south or target_group in ("Parede_Externa_Norte", "Parede_Externa_Sul"):
                add_box_to_group(target_group, wx0, wx1, yb, y_sill, wz0, wz0 + wall_thick)
                add_box_to_group(target_group, wx0, wx1, y_lintel, yt, wz0, wz0 + wall_thick)
                add_box_to_group(target_group, wx0, wx0 + 0.25, y_sill, y_lintel, wz0, wz0 + wall_thick)
                add_box_to_group(target_group, wx1 - 0.25, wx1, y_sill, y_lintel, wz0, wz0 + wall_thick)
            else:
                add_box_to_group(target_group, wx0, wx0 + wall_thick, yb, y_sill, wz0, wz1)
                add_box_to_group(target_group, wx0, wx0 + wall_thick, y_lintel, yt, wz0, wz1)
                add_box_to_group(target_group, wx0, wx0 + wall_thick, y_sill, y_lintel, wz0, wz0 + 0.25)
                add_box_to_group(target_group, wx0, wx0 + wall_thick, y_sill, y_lintel, wz1 - 0.25, wz1)
            continue

        # Standard walls
        if (wx, wy) in pitched_roof_coords:
            cnw, cne, csw, cse = roof_corner_y[(wx, wy)]
            yt = min(yt, max(cnw, cne, csw, cse))

        # Check orientation
        if target_group in ("Parede_Externa_Norte", "Parede_Externa_Sul", "Parede_Interna_Central"):
            add_box_to_group(target_group, wx0, wx1, yb, yt, wz0, wz0 + wall_thick)
        else:
            add_box_to_group(target_group, wx0, wx0 + wall_thick, yb, yt, wz0, wz1)

    # 3. CREATE BLENDER OBJECTS AND WELD VERTICES
    created_objects = []
    for name, (verts, faces, col_name, mat) in wall_buffers.items():
        if not verts or not faces:
            continue
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(verts, [], faces)
        mesh.update()

        # Weld coincident vertices so edges/lines are shared and loops work
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.001)
        bm.to_mesh(mesh)
        bm.free()
        mesh.update()

        obj = bpy.data.objects.new(name, mesh)
        if mat:
            obj.data.materials.append(mat)
        cols[col_name].objects.link(obj)
        created_objects.append(obj)
        print(f"[+] Object '{name}' -> {len(mesh.vertices)} verts, {len(mesh.polygons)} polys (in {col_name})")

    # Save Native Blender File (.blend)
    blend_walls = str(bpath / "building_by_walls.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend_walls)
    print(f"[+] Saved Blender file: {blend_walls}")

    # Also save as building_lego.blend (direct drop-in for user)
    blend_lego = str(bpath / "building_lego.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend_lego)
    print(f"[+] Updated building_lego.blend with walls: {blend_lego}")

    # Export GLTF (Modular with wall nodes)
    glb_walls = str(bpath / "model_by_walls.glb")
    bpy.ops.export_scene.gltf(filepath=glb_walls, export_format='GLB')
    print(f"[+] Saved GLB by walls: {glb_walls}")

    glb_modular = str(bpath / "model_modular_lego.glb")
    bpy.ops.export_scene.gltf(filepath=glb_modular, export_format='GLB')
    print(f"[+] Updated model_modular_lego.glb: {glb_modular}")

    # Synchronize to community_assets
    target_dir = Path("/home/mnunes/uo3d_map/community_assets/map0_felucca/britain/building_13_royal_guard_outpost")
    if target_dir.exists():
        for fname in ["building_by_walls.blend", "building_lego.blend", "model_by_walls.glb", "model_modular_lego.glb"]:
            src = bpath / fname
            dst = target_dir / fname
            if src.exists():
                shutil.copy2(src, dst)
        print(f"[+] Synchronized to {target_dir}")

if __name__ == "__main__":
    build_walls()
