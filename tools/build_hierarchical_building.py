#!/usr/bin/env python3
"""
tools/build_hierarchical_building.py

Hierarchical Wall & Block 3D builder for UO3D buildings:
- Groups continuous wall runs into distinct parent wall objects (Empty containers).
- Clicking a wall in the Blender Outliner tree selects the entire wall and moves all its blocks together!
- Expanding the tree reveals every single individual block of that wall as an independent object,
  allowing direct selection of individual blocks, faces, lines, and vertices!
- Separate small walls never merge into big walls; each distinct wall segment is its own parent.
- Every block has its local origin centered on itself so gizmos and snapping are exact.
"""

import os
import sys
import json
import shutil
from pathlib import Path
from collections import defaultdict
from mathutils import Vector

sys.path.append("/home/mnunes/uo3d_map")
import update_all_community_assets as updater
updater.init_worker()

import bpy

def build_hierarchical(building_folder="map0_felucca/britain/building_01_lord_british_castle_annex"):
    fpath = Path(building_folder).resolve()
    info_path = fpath / "info.json"
    if not info_path.exists():
        print(f"[X] No info.json in {fpath}")
        return False

    with open(info_path, "r", encoding="utf-8") as f:
        meta = json.load(f)

    b = meta.get("world_bounds")
    map_index = meta.get("map_index", 0)
    min_wx, max_wx = b["min_x"], b["max_x"]
    min_wy, max_wy = b["min_y"], b["max_y"]
    base_z = b["base_z"]
    center_x = (min_wx + max_wx + 1) / 2.0
    center_z = (min_wy + max_wy + 1) / 2.0
    y_base_ground = base_z * updater.V_SCALE
    expected_count = meta.get("stats", {}).get("item_count", 0)
    target_ids = {u["id"] for u in meta.get("unique_items", [])}
    items, staidx, statics = updater.collect_building_items(map_index, min_wx, max_wx, min_wy, max_wy, expected_count, target_ids)

    print(f"[+] Loaded {len(items)} items for {fpath.name}")

    # Clean Blender Scene
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.tool_settings.use_snap = True
    scene.tool_settings.snap_elements = {'INCREMENT'}

    # Collections
    col_names = [
        "01_Paredes_Externas",
        "02_Paredes_Internas",
        "03_Pisos_Escadas",
        "04_Moveis_Decoracoes",
        "05_Telhado"
    ]
    cols = {}
    for cname in col_names:
        c = bpy.data.collections.new(cname)
        scene.collection.children.link(c)
        cols[cname] = c

    # Materials
    def make_mat(name, color, rough=0.75):
        m = bpy.data.materials.new(name)
        bsdf = m.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Base Color"].default_value = color
            bsdf.inputs["Roughness"].default_value = rough
        return m

    mat_ext = make_mat("Mat_Parede_Externa", (0.78, 0.65, 0.48, 1.0), 0.75)
    mat_int = make_mat("Mat_Parede_Interna", (0.72, 0.58, 0.42, 1.0), 0.80)
    mat_floor = make_mat("Mat_Pisos", (0.60, 0.55, 0.50, 1.0), 0.85)
    mat_props = make_mat("Mat_Moveis", (0.55, 0.38, 0.22, 1.0), 0.65)
    mat_roof = make_mat("Mat_Telhado", (0.82, 0.68, 0.35, 1.0), 0.85)

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

    # Helper: Create Box Mesh Object with local centering
    def create_box_mesh(name, bx0, bx1, by0, by1, bz0, bz1, material=None):
        if by1 <= by0 or bx1 <= bx0 or bz1 <= bz0: return None, None
        cx, cz, cy = (bx0 + bx1) / 2.0, (bz0 + bz1) / 2.0, (by0 + by1) / 2.0
        hx, hz, hy = (bx1 - bx0) / 2.0, (bz1 - bz0) / 2.0, (by1 - by0) / 2.0
        # Local vertices centered at (0, 0, 0)
        v = [
            (-hx, -hz, -hy), (hx, -hz, -hy), (hx, hz, -hy), (-hx, hz, -hy),
            (-hx, -hz, hy), (hx, -hz, hy), (hx, hz, hy), (-hx, hz, hy)
        ]
        f = [
            (0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1), (2, 6, 7, 3), (0, 3, 7, 4), (1, 5, 6, 2)
        ]
        m = bpy.data.meshes.new(name)
        m.from_pydata(v, [], f)
        m.update()
        obj = bpy.data.objects.new(name, m)
        obj.location = Vector((cx, cz, cy))
        if material:
            obj.data.materials.append(material)
        return obj, Vector((cx, cz, cy))

    def create_custom_mesh(name, verts_world, f, material=None):
        # Calculate median center
        cx = sum(p[0] for p in verts_world) / len(verts_world)
        cz = sum(p[1] for p in verts_world) / len(verts_world)
        cy = sum(p[2] for p in verts_world) / len(verts_world)
        # Shift vertices to local
        v_local = [(p[0] - cx, p[1] - cz, p[2] - cy) for p in verts_world]
        m = bpy.data.meshes.new(name)
        m.from_pydata(v_local, [], f)
        m.update()
        obj = bpy.data.objects.new(name, m)
        obj.location = Vector((cx, cz, cy))
        if material:
            obj.data.materials.append(material)
        return obj, Vector((cx, cz, cy))

    # Helper: Link Child to Parent with transform preservation
    def link_child_to_parent(child_obj, parent_obj, collection):
        collection.objects.link(child_obj)
        bpy.context.view_layer.update()
        child_obj.parent = parent_obj
        child_obj.matrix_parent_inverse = parent_obj.matrix_world.inverted()

    # 1. CATEGORIZE ITEMS
    wall_items = []
    roof_items = []
    floor_items = []
    stair_items = []
    prop_items = []

    for it in items:
        wx, wy, z, item_id, fl, h, name = it
        if item_id in updater.TRUE_PITCHED_ROOFS:
            roof_items.append(it)
        elif ("stair" in name) or (item_id in (1850, 1852)) or ("banister" in name):
            stair_items.append(it)
        elif (fl & 0x200 != 0) or ("board" in name) or ("floor" in name) or (item_id in updater.STONE_ROOF_TERRACE):
            floor_items.append(it)
        elif (fl & 0x10 != 0) or ("wall" in name) or ("window" in name) or (item_id in updater._S_WALLS) or (item_id in updater._E_WALLS) or (item_id in updater._CORN_WALLS) or ("post" in name):
            wall_items.append(it)
        else:
            prop_items.append(it)

    if wall_items:
        min_wall_x = min(it[0] for it in wall_items)
        max_wall_x = max(it[0] for it in wall_items)
        min_wall_y = min(it[1] for it in wall_items)
        max_wall_y = max(it[1] for it in wall_items)
    else:
        min_wall_x, max_wall_x = min_wx, max_wx
        min_wall_y, max_wall_y = min_wy, max_wy

    # 2. SEGMENT WALLS INTO DISTINCT CONTINUOUS WALL RUNS
    ew_by_y = defaultdict(list)
    ns_by_x = defaultdict(list)

    for it in wall_items:
        wx, wy, z, item_id, fl, h, name = it
        is_s = (item_id in updater._S_WALLS) or ("south" in name) or (item_id in (14, 59, 186))
        is_e = (item_id in updater._E_WALLS) or ("east" in name) or (item_id in (15, 60, 185))
        if is_s and not is_e:
            ew_by_y[wy].append(it)
        elif is_e and not is_s:
            ns_by_x[wx].append(it)
        else:
            if wy == min_wall_y or wy == max_wall_y:
                ew_by_y[wy].append(it)
            elif wx == min_wall_x or wx == max_wall_x:
                ns_by_x[wx].append(it)
            else:
                ew_by_y[wy].append(it)

    wall_segments = []

    # East-West runs (horizontal)
    for wy, wlist in sorted(ew_by_y.items()):
        wlist.sort(key=lambda it: (it[0], it[2]))
        curr_run = []
        for it in wlist:
            if not curr_run:
                curr_run.append(it)
            else:
                prev_x = curr_run[-1][0]
                if it[0] <= prev_x + 2:
                    curr_run.append(it)
                else:
                    wall_segments.append(('EW', wy, curr_run))
                    curr_run = [it]
        if curr_run:
            wall_segments.append(('EW', wy, curr_run))

    # North-South runs (vertical)
    for wx, wlist in sorted(ns_by_x.items()):
        wlist.sort(key=lambda it: (it[1], it[2]))
        curr_run = []
        for it in wlist:
            if not curr_run:
                curr_run.append(it)
            else:
                prev_y = curr_run[-1][1]
                if it[1] <= prev_y + 2:
                    curr_run.append(it)
                else:
                    wall_segments.append(('NS', wx, curr_run))
                    curr_run = [it]
        if curr_run:
            wall_segments.append(('NS', wx, curr_run))

    print(f"[+] Identified {len(wall_segments)} distinct wall segments!")

    # 3. BUILD HIERARCHICAL WALLS
    total_wall_blocks = 0
    for idx, (dir_type, coord, seg_items) in enumerate(wall_segments, 1):
        xs = [it[0] for it in seg_items]
        ys = [it[1] for it in seg_items]
        zs = [it[2] for it in seg_items]
        min_x_seg, max_x_seg = min(xs), max(xs)
        min_y_seg, max_y_seg = min(ys), max(ys)

        is_ext = False
        if dir_type == 'EW':
            if coord == min_wall_y:
                wall_title = f"Parede_Externa_Norte_Y{coord}_X{min_x_seg}_{max_x_seg}"
                is_ext = True
            elif coord == max_wall_y:
                wall_title = f"Parede_Externa_Sul_Y{coord}_X{min_x_seg}_{max_x_seg}"
                is_ext = True
            else:
                wall_title = f"Parede_Interna_EW_{idx:02d}_Y{coord}_X{min_x_seg}_{max_x_seg}"
        else: # NS
            if coord == min_wall_x:
                wall_title = f"Parede_Externa_Oeste_X{coord}_Y{min_y_seg}_{max_y_seg}"
                is_ext = True
            elif coord == max_wall_x:
                wall_title = f"Parede_Externa_Leste_X{coord}_Y{min_y_seg}_{max_y_seg}"
                is_ext = True
            else:
                wall_title = f"Parede_Interna_NS_{idx:02d}_X{coord}_Y{min_y_seg}_{max_y_seg}"

        target_col = cols["01_Paredes_Externas"] if is_ext else cols["02_Paredes_Internas"]
        target_mat = mat_ext if is_ext else mat_int

        # Center position for Parent Empty
        mid_x_world = ((min_x_seg + max_x_seg + 1) / 2.0 - center_x) * updater.H_SCALE
        mid_z_world = ((min_y_seg + max_y_seg + 1) / 2.0 - center_z) * updater.H_SCALE
        mid_y_world = (min(zs) * updater.V_SCALE) - y_base_ground

        parent_wall = bpy.data.objects.new(wall_title, None)
        parent_wall.location = Vector((mid_x_world, mid_z_world, mid_y_world))
        parent_wall.empty_display_type = 'CUBE'
        parent_wall.empty_display_size = 1.0
        target_col.objects.link(parent_wall)
        bpy.context.view_layer.update()

        for it in seg_items:
            wx, wy, z, item_id, fl, h, name = it
            wx0 = (wx - center_x) * updater.H_SCALE
            wx1 = wx0 + updater.H_SCALE
            wz0 = (wy - center_z) * updater.H_SCALE
            wz1 = wz0 + updater.H_SCALE
            yb  = (z * updater.V_SCALE) - y_base_ground
            yt  = yb + max(h, 1) * updater.V_SCALE

            is_win = (item_id in (14, 15, 59, 60)) or ("window" in name)
            is_gab = (item_id in (24, 25, 66, 67, 82, 83)) and ("wall" in name) and (h <= 5)

            if (wx, wy) in pitched_roof_coords:
                cnw, cne, csw, cse = roof_corner_y[(wx, wy)]
                yt = min(yt, max(cnw, cne, csw, cse))

            block_name = f"Bloco_{name.replace(' ', '_')}_{wx}_{wy}_z{z}"
            child_obj = None

            if is_win:
                block_name = f"Janela_{wx}_{wy}_z{z}"
                y_sill = yb + max(h, 1) * 0.35 * updater.V_SCALE
                y_lintel = yb + max(h, 1) * 0.75 * updater.V_SCALE
                if dir_type == 'EW':
                    verts, faces = [], []
                    for bx0, bx1, by0, by1, bz0, bz1 in [
                        (wx0, wx1, yb, y_sill, wz0, wz0 + wall_thick),
                        (wx0, wx1, y_lintel, yt, wz0, wz0 + wall_thick),
                        (wx0, wx0 + 0.25, y_sill, y_lintel, wz0, wz0 + wall_thick),
                        (wx1 - 0.25, wx1, y_sill, y_lintel, wz0, wz0 + wall_thick)
                    ]:
                        idx_b = len(verts)
                        verts.extend([
                            (bx0, bz0, by0), (bx1, bz0, by0), (bx1, bz1, by0), (bx0, bz1, by0),
                            (bx0, bz0, by1), (bx1, bz0, by1), (bx1, bz1, by1), (bx0, bz1, by1)
                        ])
                        faces.extend([
                            (idx_b+0, idx_b+1, idx_b+2, idx_b+3), (idx_b+4, idx_b+7, idx_b+6, idx_b+5),
                            (idx_b+0, idx_b+4, idx_b+5, idx_b+1), (idx_b+2, idx_b+6, idx_b+7, idx_b+3),
                            (idx_b+0, idx_b+3, idx_b+7, idx_b+4), (idx_b+1, idx_b+5, idx_b+6, idx_b+2)
                        ])
                    child_obj, _ = create_custom_mesh(block_name, verts, faces, target_mat)
                else:
                    verts, faces = [], []
                    for bx0, bx1, by0, by1, bz0, bz1 in [
                        (wx0, wx0 + wall_thick, yb, y_sill, wz0, wz1),
                        (wx0, wx0 + wall_thick, y_lintel, yt, wz0, wz1),
                        (wx0, wx0 + wall_thick, y_sill, y_lintel, wz0, wz0 + 0.25),
                        (wx0, wx0 + wall_thick, y_sill, y_lintel, wz1 - 0.25, wz1)
                    ]:
                        idx_b = len(verts)
                        verts.extend([
                            (bx0, bz0, by0), (bx1, bz0, by0), (bx1, bz1, by0), (bx0, bz1, by0),
                            (bx0, bz0, by1), (bx1, bz0, by1), (bx1, bz1, by1), (bx0, bz1, by1)
                        ])
                        faces.extend([
                            (idx_b+0, idx_b+1, idx_b+2, idx_b+3), (idx_b+4, idx_b+7, idx_b+6, idx_b+5),
                            (idx_b+0, idx_b+4, idx_b+5, idx_b+1), (idx_b+2, idx_b+6, idx_b+7, idx_b+3),
                            (idx_b+0, idx_b+3, idx_b+7, idx_b+4), (idx_b+1, idx_b+5, idx_b+6, idx_b+2)
                        ])
                    child_obj, _ = create_custom_mesh(block_name, verts, faces, target_mat)
            elif is_gab:
                child_obj, _ = create_box_mesh(block_name, wx0, wx1, yb, yt, wz0, wz0 + wall_thick, target_mat)
            else:
                if dir_type == 'EW':
                    child_obj, _ = create_box_mesh(block_name, wx0, wx1, yb, yt, wz0, wz0 + wall_thick, target_mat)
                else:
                    child_obj, _ = create_box_mesh(block_name, wx0, wx0 + wall_thick, yb, yt, wz0, wz1, target_mat)

            if child_obj:
                link_child_to_parent(child_obj, parent_wall, target_col)
                total_wall_blocks += 1

    print(f"[+] Created {len(wall_segments)} wall parents containing {total_wall_blocks} child blocks!")

    # 4. BUILD HIERARCHICAL ROOF
    if roof_items:
        roof_groups = {
            "Telhado_Vertente_Norte": [it for it in roof_items if it[3] in updater.ROOF_SLOPE_NORTH],
            "Telhado_Vertente_Sul": [it for it in roof_items if it[3] in updater.ROOF_SLOPE_SOUTH],
            "Telhado_Vertente_Leste": [it for it in roof_items if it[3] in updater.ROOF_SLOPE_EAST],
            "Telhado_Vertente_Oeste": [it for it in roof_items if it[3] in updater.ROOF_SLOPE_WEST],
            "Telhado_Cumeeira": [it for it in roof_items if it[3] in (updater.ROOF_RIDGE_NS | updater.ROOF_RIDGE_EW)]
        }
        for r_name, r_list in roof_groups.items():
            if not r_list: continue
            xs = [it[0] for it in r_list]
            ys = [it[1] for it in r_list]
            zs = [it[2] for it in r_list]
            mid_x = ((min(xs) + max(xs) + 1) / 2.0 - center_x) * updater.H_SCALE
            mid_z = ((min(ys) + max(ys) + 1) / 2.0 - center_z) * updater.H_SCALE
            mid_y = (min(zs) * updater.V_SCALE) - y_base_ground

            p_roof = bpy.data.objects.new(r_name, None)
            p_roof.location = Vector((mid_x, mid_z, mid_y))
            p_roof.empty_display_type = 'CUBE'
            p_roof.empty_display_size = 2.0
            cols["05_Telhado"].objects.link(p_roof)
            bpy.context.view_layer.update()

            for it in r_list:
                wx, wy, z, item_id, fl, h, name = it
                wx0 = (wx - center_x) * updater.H_SCALE
                wx1 = wx0 + updater.H_SCALE
                wz0 = (wy - center_z) * updater.H_SCALE
                wz1 = wz0 + updater.H_SCALE
                yb  = (z * updater.V_SCALE) - y_base_ground
                t_name = f"Telha_{wx}_{wy}_z{z}"

                if item_id in updater.ROOF_SLOPE_SOUTH:
                    v = [
                        (wx0, wz0, yb), (wx1, wz0, yb), (wx1, wz1, yb + step), (wx0, wz1, yb + step),
                        (wx0, wz0, yb - thick), (wx1, wz0, yb - thick), (wx1, wz1, yb + step - thick), (wx0, wz1, yb + step - thick)
                    ]
                    f = [(0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1), (3, 2, 6, 7), (0, 3, 7, 4), (1, 5, 6, 2)]
                elif item_id in updater.ROOF_SLOPE_NORTH:
                    v = [
                        (wx0, wz1, yb), (wx1, wz1, yb), (wx1, wz0, yb + step), (wx0, wz0, yb + step),
                        (wx0, wz1, yb - thick), (wx1, wz1, yb - thick), (wx1, wz0, yb + step - thick), (wx0, wz0, yb + step - thick)
                    ]
                    f = [(0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1), (3, 2, 6, 7), (0, 3, 7, 4), (1, 5, 6, 2)]
                elif item_id in updater.ROOF_SLOPE_EAST:
                    v = [
                        (wx0, wz0, yb), (wx0, wz1, yb), (wx1, wz1, yb + step), (wx1, wz0, yb + step),
                        (wx0, wz0, yb - thick), (wx0, wz1, yb - thick), (wx1, wz1, yb + step - thick), (wx1, wz0, yb + step - thick)
                    ]
                    f = [(0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1), (3, 2, 6, 7), (0, 3, 7, 4), (1, 5, 6, 2)]
                elif item_id in updater.ROOF_SLOPE_WEST:
                    v = [
                        (wx1, wz0, yb), (wx1, wz1, yb), (wx0, wz1, yb + step), (wx0, wz0, yb + step),
                        (wx1, wz0, yb - thick), (wx1, wz1, yb - thick), (wx0, wz1, yb + step - thick), (wx0, wz0, yb + step - thick)
                    ]
                    f = [(0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1), (3, 2, 6, 7), (0, 3, 7, 4), (1, 5, 6, 2)]
                elif item_id in updater.ROOF_RIDGE_EW:
                    wz_mid = wz0 + 0.5 * updater.H_SCALE
                    v = [
                        (wx0, wz0, yb), (wx1, wz0, yb), (wx1, wz_mid, yb + step), (wx0, wz_mid, yb + step),
                        (wx1, wz1, yb), (wx0, wz1, yb),
                        (wx0, wz0, yb - thick), (wx1, wz0, yb - thick), (wx1, wz_mid, yb + step - thick), (wx0, wz_mid, yb + step - thick),
                        (wx1, wz1, yb - thick), (wx0, wz1, yb - thick)
                    ]
                    f = [(0, 1, 2, 3), (3, 2, 4, 5), (9, 8, 7, 6), (11, 10, 8, 9), (0, 6, 7, 1), (4, 10, 11, 5)]
                else:
                    v = [
                        (wx0, wz0, yb), (wx1, wz0, yb), (wx1, wz1, yb + step), (wx0, wz1, yb + step),
                        (wx0, wz0, yb - thick), (wx1, wz0, yb - thick), (wx1, wz1, yb + step - thick), (wx0, wz1, yb + step - thick)
                    ]
                    f = [(0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1), (3, 2, 6, 7), (0, 3, 7, 4), (1, 5, 6, 2)]

                child_tile, _ = create_custom_mesh(t_name, v, f, mat_roof)
                if child_tile:
                    link_child_to_parent(child_tile, p_roof, cols["05_Telhado"])

    # 5. BUILD HIERARCHICAL FLOORS & STAIRS
    if floor_items:
        p_floor = bpy.data.objects.new("Pisos_Lajes", None)
        p_floor.location = Vector((0, 0, 0))
        p_floor.empty_display_type = 'CUBE'
        cols["03_Pisos_Escadas"].objects.link(p_floor)
        bpy.context.view_layer.update()
        for it in floor_items:
            wx, wy, z, item_id, fl, h, name = it
            wx0 = (wx - center_x) * updater.H_SCALE
            wx1 = wx0 + updater.H_SCALE
            wz0 = (wy - center_z) * updater.H_SCALE
            wz1 = wz0 + updater.H_SCALE
            yb  = (z * updater.V_SCALE) - y_base_ground
            f_thick = 0.15 if item_id in updater.STONE_ROOF_TERRACE else 0.10
            c_floor, _ = create_box_mesh(f"Piso_{name.replace(' ', '_')}_{wx}_{wy}_z{z}", wx0, wx1, yb - f_thick, yb, wz0, wz1, mat_floor)
            if c_floor:
                link_child_to_parent(c_floor, p_floor, cols["03_Pisos_Escadas"])

    if stair_items:
        p_stair = bpy.data.objects.new("Escadas_Corrimãos", None)
        p_stair.location = Vector((0, 0, 0))
        p_stair.empty_display_type = 'CUBE'
        cols["03_Pisos_Escadas"].objects.link(p_stair)
        bpy.context.view_layer.update()
        for it in stair_items:
            wx, wy, z, item_id, fl, h, name = it
            wx0 = (wx - center_x) * updater.H_SCALE
            wx1 = wx0 + updater.H_SCALE
            wz0 = (wy - center_z) * updater.H_SCALE
            wz1 = wz0 + updater.H_SCALE
            yb  = (z * updater.V_SCALE) - y_base_ground
            yt  = yb + max(h, 1) * updater.V_SCALE
            if "banister" in name:
                c_ban, _ = create_box_mesh(f"Corrimão_{wx}_{wy}_z{z}", wx0, wx1, yb, yt, wz0, wz0 + 0.1, mat_floor)
                if c_ban:
                    link_child_to_parent(c_ban, p_stair, cols["03_Pisos_Escadas"])
            else:
                c_st, _ = create_box_mesh(f"Degrau_{wx}_{wy}_z{z}", wx0, wx1, yb, yb + 0.25, wz0, wz1, mat_floor)
                if c_st:
                    link_child_to_parent(c_st, p_stair, cols["03_Pisos_Escadas"])

    # 6. BUILD PROPS & FURNITURE
    if prop_items:
        p_prop = bpy.data.objects.new("Moveis_Decoracoes", None)
        p_prop.location = Vector((0, 0, 0))
        p_prop.empty_display_type = 'CUBE'
        cols["04_Moveis_Decoracoes"].objects.link(p_prop)
        bpy.context.view_layer.update()
        for it in prop_items:
            wx, wy, z, item_id, fl, h, name = it
            wx0 = (wx - center_x) * updater.H_SCALE
            wx1 = wx0 + updater.H_SCALE
            wz0 = (wy - center_z) * updater.H_SCALE
            wz1 = wz0 + updater.H_SCALE
            yb  = (z * updater.V_SCALE) - y_base_ground
            yt  = yb + max(h, 1) * updater.V_SCALE
            c_prop, _ = create_box_mesh(f"Movel_{name.replace(' ', '_')}_{wx}_{wy}_z{z}", wx0 + 0.1, wx1 - 0.1, yb, yt, wz0 + 0.1, wz1 - 0.1, mat_props)
            if c_prop:
                link_child_to_parent(c_prop, p_prop, cols["04_Moveis_Decoracoes"])

    # Remove empty collections
    for cname, c in list(cols.items()):
        if len(c.objects) == 0:
            scene.collection.children.unlink(c)
            bpy.data.collections.remove(c)

    # Save Native Blender files (.blend)
    blend_path = str(fpath / "building_lego.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend_path)
    print(f"[+] Saved Blender file: {blend_path}")

    # Export Modular GLB
    glb_modular = str(fpath / "model_modular_lego.glb")
    bpy.ops.export_scene.gltf(filepath=glb_modular, export_format='GLB')
    print(f"[+] Saved Modular GLB: {glb_modular}")

    # Sync to community_assets
    target_dir = Path("/home/mnunes/uo3d_map/community_assets/map0_felucca/britain") / fpath.name
    if target_dir.exists():
        for fname in ["building_lego.blend", "model_modular_lego.glb"]:
            src = fpath / fname
            dst = target_dir / fname
            if src.exists():
                shutil.copy2(src, dst)
        print(f"[+] Synchronized to {target_dir}")

    return True

if __name__ == "__main__":
    args = sys.argv
    b_folder = "map0_felucca/britain/building_01_lord_british_castle_annex"
    if "--" in args:
        idx = args.index("--")
        if idx + 1 < len(args):
            b_folder = args[idx + 1]
    build_hierarchical(b_folder)
