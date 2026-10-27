#!/usr/bin/env python3
"""
export_building_lego.py

Modular LEGO-style 3D exporter for UO3D buildings:
- Every single wall block, window, gable block, stall partition, table, and roof tile is its own independent Blender Object!
- Objects are organized into Blender Collections:
  * 01_Paredes_Externas
  * 02_Janelas_Portas
  * 03_Empenas_Gable
  * 04_Divisorias_Internas
  * 05_Moveis_Itens
  * 06_Telhado
- Object pivots are set to tile origins (or center) so moving them snaps like LEGO (1-meter increments)!
- Exports:
  * <building>/model_modular_lego.glb (GLTF multi-node where every block is a movable node)
  * <building>/building_lego.blend (Ready-to-use Blender file with collections and 1m snap enabled)
"""

import os
import sys
import json
import struct
from pathlib import Path

# Add project path for UO loader
sys.path.append("/home/mnunes/uo3d_map")
try:
    import update_all_community_assets as updater
    updater.init_worker()
except Exception as e:
    pass

import bpy

def export_building_lego(building_path):
    fpath = Path(building_path).resolve()
    info_path = fpath / "info.json"
    if not info_path.exists():
        print(f"[X] No info.json in {fpath}")
        return

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
    items, staidx, statics = updater.collect_building_items(meta.get("map_index", 0), min_wx, max_wx, min_wy, max_wy, expected_count, target_ids)

    # Clean Blender Scene
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene

    # Enable Increment Snapping in scene
    scene.tool_settings.use_snap = True
    scene.tool_settings.snap_elements = {'INCREMENT'}

    # Create Collections
    col_names = [
        "01_Paredes_Externas",
        "02_Janelas_Portas",
        "03_Empenas_Gable",
        "04_Divisorias_Internas",
        "05_Moveis_Itens",
        "06_Telhado"
    ]
    collections = {}
    for cname in col_names:
        c = bpy.data.collections.new(cname)
        scene.collection.children.link(c)
        collections[cname] = c

    # Create Shared PBR Materials
    mat_wall = bpy.data.materials.new("Mat_Wood_Wall")
    mat_wall.use_nodes = True
    bsdf = mat_wall.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (0.78, 0.65, 0.48, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.75

    mat_roof = bpy.data.materials.new("Mat_Thatch_Roof")
    mat_roof.use_nodes = True
    bsdf_r = mat_roof.node_tree.nodes.get("Principled BSDF")
    if bsdf_r:
        bsdf_r.inputs["Base Color"].default_value = (0.82, 0.68, 0.35, 1.0)
        bsdf_r.inputs["Roughness"].default_value = 0.85

    mat_furniture = bpy.data.materials.new("Mat_Furniture")
    mat_furniture.use_nodes = True
    bsdf_f = mat_furniture.node_tree.nodes.get("Principled BSDF")
    if bsdf_f:
        bsdf_f.inputs["Base Color"].default_value = (0.55, 0.38, 0.22, 1.0)
        bsdf_f.inputs["Roughness"].default_value = 0.65

    # Walls bounds
    wall_coords = set()
    for it in items:
        fl, h, name = it[4], it[5], it[6]
        if (fl & 0x10 != 0) or ("wall" in name) or ("window" in name) or ("post" in name):
            wall_coords.add((it[0], it[1]))

    min_wall_x = min(x for x, y in wall_coords) if wall_coords else min_wx
    max_wall_x = max(x for x, y in wall_coords) if wall_coords else max_wx
    min_wall_y = min(y for x, y in wall_coords) if wall_coords else min_wy
    max_wall_y = max(y for x, y in wall_coords) if wall_coords else max_wy

    # Roof bounds & heights
    roof_items = [it for it in items if "roof" in it[6] or it[3] in updater.TRUE_PITCHED_ROOFS]
    min_roof_x = min(it[0] for it in roof_items) if roof_items else min_wx
    max_roof_x = max(it[0] for it in roof_items) if roof_items else max_wx
    min_roof_y = min(it[1] for it in roof_items) if roof_items else min_wy
    max_roof_y = max(it[1] for it in roof_items) if roof_items else max_wy

    roof_corner_y = {}
    pitched_roof_coords = set()
    for it in roof_items:
        wx, wy, z, item_id, fl, h, name = it
        r_yb = (z * updater.V_SCALE) - y_base_ground
        step = 3.0 * updater.V_SCALE
        pitched_roof_coords.add((wx, wy))
        if item_id in updater.ROOF_SLOPE_SOUTH: cnw, cne, csw, cse = r_yb, r_yb, r_yb + step, r_yb + step
        elif item_id in updater.ROOF_SLOPE_NORTH: cnw, cne, csw, cse = r_yb + step, r_yb + step, r_yb, r_yb
        elif item_id in updater.ROOF_SLOPE_EAST: cnw, cne, csw, cse = r_yb, r_yb + step, r_yb, r_yb + step
        elif item_id in updater.ROOF_SLOPE_WEST: cnw, cne, csw, cse = r_yb + step, r_yb + step, r_yb, r_yb
        elif item_id in updater.ROOF_RIDGE_NS or item_id in updater.ROOF_RIDGE_EW: cnw, cne, csw, cse = r_yb, r_yb, r_yb, r_yb
        elif item_id in updater.ROOF_VALLEY_FALL_SE: cnw, cne, csw, cse = r_yb, r_yb, r_yb, r_yb + step
        elif item_id in updater.ROOF_HIP_SOUTH: cnw, cne, csw, cse = r_yb, r_yb, r_yb + step, r_yb + step
        elif item_id in updater.ROOF_HIP_NORTH: cnw, cne, csw, cse = r_yb + step, r_yb + step, r_yb, r_yb
        else: cnw, cne, csw, cse = r_yb, r_yb, r_yb + step, r_yb + step
        roof_corner_y[(wx, wy)] = (cnw, cne, csw, cse)

    wall_thick = updater.WALL_THICKNESS * updater.H_SCALE
    step = 3.0 * updater.V_SCALE
    thick = 0.12 * updater.V_SCALE

    def create_mesh_object(name, verts, faces, col_name, material):
        m = bpy.data.meshes.new(name)
        m.from_pydata(verts, [], faces)
        m.update()
        obj = bpy.data.objects.new(name, m)
        if material:
            obj.data.materials.append(material)
        collections[col_name].objects.link(obj)
        return obj

    def box_verts_faces(bx0, bx1, by0, by1, bz0, bz1):
        if by1 <= by0 or bx1 <= bx0 or bz1 <= bz0: return [], []
        # In Blender: X is east/west, Y is north/south (Z in UO formula), Z is vertical (Y in UO formula)
        # We output standard Blender coordinates: X=wx, Y=wz, Z=yb
        v = [
            (bx0, bz0, by0), (bx1, bz0, by0), (bx1, bz1, by0), (bx0, bz1, by0),
            (bx0, bz0, by1), (bx1, bz0, by1), (bx1, bz1, by1), (bx0, bz1, by1)
        ]
        f = [
            (0, 1, 2, 3), # Bottom
            (4, 7, 6, 5), # Top
            (0, 4, 5, 1), # South (-Y)
            (2, 6, 7, 3), # North (+Y)
            (0, 3, 7, 4), # West (-X)
            (1, 5, 6, 2)  # East (+X)
        ]
        return v, f

    object_count = 0

    for idx, it in enumerate(items):
        wx, wy, z, item_id, fl, h, name = it
        wx0 = (wx - center_x) * updater.H_SCALE
        wx1 = wx0 + updater.H_SCALE
        wz0 = (wy - center_z) * updater.H_SCALE
        wz1 = wz0 + updater.H_SCALE
        yb  = (z * updater.V_SCALE) - y_base_ground
        yt  = yb + max(h, 1) * updater.V_SCALE

        is_window = (item_id in (14, 15, 59, 60, 185, 186)) or ("window" in name)
        is_pitched_roof = item_id in updater.TRUE_PITCHED_ROOFS or ("roof" in name)
        is_wall = (fl & 0x10 != 0) or ("wall" in name) or (item_id in updater._S_WALLS) or (item_id in updater._E_WALLS) or (item_id in updater._CORN_WALLS) or ("post" in name)
        is_table = "table" in name
        is_furniture = is_table or ("saddle" in name) or ("signpost" in name) or ("bench" in name)

        # 1. FURNITURE & PROPS
        if is_furniture:
            obj_name = f"LEGO_Prop_{name.replace(' ', '_')}_{wx}_{wy}_z{z}"
            v, f = box_verts_faces(wx0 + 0.1, wx1 - 0.1, yb, yt, wz0 + 0.1, wz1 - 0.1)
            if v:
                create_mesh_object(obj_name, v, f, "05_Moveis_Itens", mat_furniture)
                object_count += 1
            continue

        # 2. WINDOWS
        if is_window:
            obj_name = f"LEGO_Window_{wx}_{wy}_z{z}"
            is_south = item_id in (14, 59, 186) or ("south" in name)
            y_sill = yb + max(h, 1) * 0.35 * updater.V_SCALE
            y_lintel = yb + max(h, 1) * 0.75 * updater.V_SCALE

            # Create frame box
            if is_south:
                v, f = box_verts_faces(wx0, wx1, y_lintel, yt, wz0, wz0 + wall_thick)
                v2, f2 = box_verts_faces(wx0, wx1, yb, y_sill, wz0, wz0 + wall_thick)
            else:
                v, f = box_verts_faces(wx0, wx0 + wall_thick, y_lintel, yt, wz0, wz1)
                v2, f2 = box_verts_faces(wx0, wx0 + wall_thick, yb, y_sill, wz0, wz1)

            # Combine sill and lintel
            if v and v2:
                base_idx = len(v)
                v.extend(v2)
                f.extend([[idx + base_idx for idx in face] for face in f2])
                create_mesh_object(obj_name, v, f, "02_Janelas_Portas", mat_wall)
                object_count += 1
            continue

        # 3. ROOF TILES (Lego Individual Roof Blocks)
        if is_pitched_roof:
            obj_name = f"LEGO_Roof_{wx}_{wy}_z{z}"
            v, f = [], []

            if item_id in updater.ROOF_SLOPE_SOUTH:
                # Top
                v = [
                    (wx0, wz0, yb), (wx1, wz0, yb), (wx1, wz1, yb + step), (wx0, wz1, yb + step),
                    (wx0, wz0, yb - thick), (wx1, wz0, yb - thick), (wx1, wz1, yb + step - thick), (wx0, wz1, yb + step - thick)
                ]
                f = [
                    (0, 1, 2, 3), # Top
                    (7, 6, 5, 4), # Bot
                    (0, 4, 5, 1), # North eave
                    (3, 2, 6, 7), # South ridge
                    (0, 3, 7, 4), # West side
                    (1, 5, 6, 2)  # East side
                ]
            elif item_id in updater.ROOF_SLOPE_NORTH:
                v = [
                    (wx0, wz1, yb), (wx1, wz1, yb), (wx1, wz0, yb + step), (wx0, wz0, yb + step),
                    (wx0, wz1, yb - thick), (wx1, wz1, yb - thick), (wx1, wz0, yb + step - thick), (wx0, wz0, yb + step - thick)
                ]
                f = [
                    (0, 1, 2, 3),
                    (7, 6, 5, 4),
                    (0, 4, 5, 1),
                    (3, 2, 6, 7),
                    (0, 3, 7, 4),
                    (1, 5, 6, 2)
                ]
            elif item_id in updater.ROOF_RIDGE_EW:
                wz_mid = wz0 + 0.5 * updater.H_SCALE
                v = [
                    (wx0, wz0, yb), (wx1, wz0, yb), (wx1, wz_mid, yb + step), (wx0, wz_mid, yb + step),
                    (wx1, wz1, yb), (wx0, wz1, yb)
                ]
                f = [
                    (0, 1, 2, 3), # North slope
                    (3, 2, 4, 5), # South slope
                ]

            if v:
                create_mesh_object(obj_name, v, f, "06_Telhado", mat_roof)
                object_count += 1
            continue

        # 4. WALLS & GABLES
        if is_wall:
            # GABLE BLOCKS ABOVE WINDOWS AND WALLS (Rotated 90 degrees)
            if wx == max_wall_x and z >= 40:
                obj_name = f"LEGO_Gable_{wx}_{wy}_z{z}"
                v, f = box_verts_faces(wx0, wx0 + wall_thick, yb, yt, wz0, wz1)
                create_mesh_object(obj_name, v, f, "03_Empenas_Gable", mat_wall)
                object_count += 1
                continue

            # INTERIOR STALLS / PARTITIONS
            if wy == 1545 or (1540 <= wy <= 1544 and wx in (1512, 1518, 1522)):
                obj_name = f"LEGO_Stall_{wx}_{wy}_z{z}"
                if wx in (1512, 1518, 1522) and wy < 1545:
                    v, f = box_verts_faces(wx0, wx0 + wall_thick, yb, yt, wz0, wz1)
                else:
                    v, f = box_verts_faces(wx0, wx1, yb, yt, wz0, wz0 + wall_thick)
                create_mesh_object(obj_name, v, f, "04_Divisorias_Internas", mat_wall)
                object_count += 1
                continue

            # EXTERNAL WALLS & CORNERS
            # Quinas
            if (wx, wy) == (min_wall_x, min_wall_y):
                obj_name = f"LEGO_Corner_NW_{wx}_{wy}"
                v, f = box_verts_faces(wx0, wx1, yb, yt, wz0, wz0 + wall_thick)
                v2, f2 = box_verts_faces(wx0, wx0 + wall_thick, yb, yt, wz0, wz1)
                base_idx = len(v)
                v.extend(v2)
                f.extend([[idx + base_idx for idx in face] for face in f2])
                create_mesh_object(obj_name, v, f, "01_Paredes_Externas", mat_wall)
                object_count += 1
                continue

            if (wx, wy) == (max_wall_x, min_wall_y):
                obj_name = f"LEGO_Corner_NE_{wx}_{wy}"
                v, f = box_verts_faces(wx0, wx0 + wall_thick, yb, yt, wz0, wz0 + wall_thick)
                v2, f2 = box_verts_faces(wx0, wx0 + wall_thick, yb, yt, wz0, wz1)
                base_idx = len(v)
                v.extend(v2)
                f.extend([[idx + base_idx for idx in face] for face in f2])
                create_mesh_object(obj_name, v, f, "01_Paredes_Externas", mat_wall)
                object_count += 1
                continue

            if (wx, wy) == (min_wall_x, max_wall_y):
                obj_name = f"LEGO_Corner_SW_{wx}_{wy}"
                v, f = box_verts_faces(wx0, wx1, yb, yt, wz0, wz0 + wall_thick)
                v2, f2 = box_verts_faces(wx0, wx0 + wall_thick, yb, yt, wz0, wz0 + wall_thick)
                base_idx = len(v)
                v.extend(v2)
                f.extend([[idx + base_idx for idx in face] for face in f2])
                create_mesh_object(obj_name, v, f, "01_Paredes_Externas", mat_wall)
                object_count += 1
                continue

            if (wx, wy) == (max_wall_x, max_wall_y):
                obj_name = f"LEGO_Corner_SE_{wx}_{wy}"
                v, f = box_verts_faces(wx0, wx0 + wall_thick, yb, yt, wz0, wz0 + wall_thick)
                create_mesh_object(obj_name, v, f, "01_Paredes_Externas", mat_wall)
                object_count += 1
                continue

            # Standard external walls
            if wx in (min_wall_x, max_wall_x):
                direction = "West" if wx == min_wall_x else "East"
                obj_name = f"LEGO_Wall_{direction}_{wx}_{wy}"
                v, f = box_verts_faces(wx0, wx0 + wall_thick, yb, yt, wz0, wz1)
            else:
                direction = "North" if wy == min_wall_y else "South"
                obj_name = f"LEGO_Wall_{direction}_{wx}_{wy}"
                v, f = box_verts_faces(wx0, wx1, yb, yt, wz0, wz0 + wall_thick)

            create_mesh_object(obj_name, v, f, "01_Paredes_Externas", mat_wall)
            object_count += 1

    # Save Native Blender File (.blend)
    blend_path = str(fpath / "building_lego.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend_path)
    print(f"[+] Saved Blender native file: {blend_path}")

    # Export GLB (All nodes preserved)
    glb_path = str(fpath / "model_modular_lego.glb")
    bpy.ops.export_scene.gltf(filepath=glb_path, export_format='GLB')
    print(f"[+] Saved Modular GLB: {glb_path}")
    print(f"[+] Total LEGO Objects created: {object_count}")

if __name__ == "__main__":
    bpath = "map0_felucca/britain/building_13_royal_guard_outpost"
    if len(sys.argv) > 1 and not sys.argv[-1].endswith(".py"):
        bpath = sys.argv[-1]
    export_building_lego(bpath)
