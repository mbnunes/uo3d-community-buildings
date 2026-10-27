#!/usr/bin/env python3
"""
tools/export_city_by_walls.py

Generalized modular 3D builder for UO3D buildings:
- Groups geometry by structural architectural components (Paredes, Pisos, Telhados, Móveis).
- Generates clean Blender Collections:
  * 01_Paredes_Externas (Parede_Externa_Norte, Parede_Externa_Sul, Parede_Externa_Leste, Parede_Externa_Oeste)
  * 02_Paredes_Internas (Paredes_Internas_Divisorias)
  * 03_Pisos_Escadas (Pisos_Lajes, Escadas_Corrimãos)
  * 04_Moveis_Decoracoes (Moveis_Props)
  * 05_Telhado (Telhado_Vertente_Norte, Telhado_Vertente_Sul, Telhado_Vertente_Leste, Telhado_Vertente_Oeste, Telhado_Cumeeira)
- Welds coincident vertices on each object (remove_doubles) so edges and loops can be cleanly selected.
- Smooth roof underside (no staircase bug).
- Exports:
  * building_by_walls.blend & building_lego.blend
  * model_by_walls.glb & model_modular_lego.glb
  * model_base.glb (consolidated Building_Base + Building_Roof)
  * model_base_house.glb & model_base_roof.glb
  * model_base.obj / .mtl
- Synchronizes with /home/mnunes/uo3d_map/community_assets/<city_path>
"""

import os
import sys
import json
import shutil
from pathlib import Path
from collections import defaultdict

sys.path.append("/home/mnunes/uo3d_map")
import update_all_community_assets as updater
updater.init_worker()

import bpy
import bmesh

def process_single_building(folder_path):
    fpath = Path(folder_path).resolve()
    info_path = fpath / "info.json"
    if not info_path.exists():
        return False, "No info.json"

    with open(info_path, "r", encoding="utf-8") as f:
        meta = json.load(f)

    b = meta.get("world_bounds")
    if not b:
        return False, "No world_bounds"

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

    if not items:
        return False, "No items collected"

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
    def get_or_create_mat(mat_name, color, roughness=0.8):
        m = bpy.data.materials.new(mat_name)
        bsdf = m.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Base Color"].default_value = color
            bsdf.inputs["Roughness"].default_value = roughness
        return m

    mat_ext = get_or_create_mat("Mat_Parede_Externa", (0.78, 0.65, 0.48, 1.0), 0.75)
    mat_int = get_or_create_mat("Mat_Parede_Interna", (0.72, 0.58, 0.42, 1.0), 0.80)
    mat_floor = get_or_create_mat("Mat_Pisos", (0.60, 0.55, 0.50, 1.0), 0.85)
    mat_props = get_or_create_mat("Mat_Moveis", (0.55, 0.38, 0.22, 1.0), 0.65)
    mat_roof = get_or_create_mat("Mat_Telhado", (0.82, 0.68, 0.35, 1.0), 0.85)

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
            elif item_id in updater.ROOF_VALLEY_FALL_SE: cnw, cne, csw, cse = r_yb, r_yb, r_yb, r_yb + step
            elif item_id in updater.ROOF_HIP_SOUTH: cnw, cne, csw, cse = r_yb, r_yb, r_yb + step, r_yb + step
            elif item_id in updater.ROOF_HIP_NORTH: cnw, cne, csw, cse = r_yb + step, r_yb + step, r_yb, r_yb
            else: cnw, cne, csw, cse = r_yb, r_yb, r_yb + step, r_yb + step
            roof_corner_y[(wx, wy)] = (cnw, cne, csw, cse)

    # Actual wall boundary coordinates
    actual_walls = [it for it in items if (it[4] & 0x10 != 0) or ("wall" in it[6]) or ("window" in it[6])]
    if actual_walls:
        min_wall_x = min(it[0] for it in actual_walls)
        max_wall_x = max(it[0] for it in actual_walls)
        min_wall_y = min(it[1] for it in actual_walls)
        max_wall_y = max(it[1] for it in actual_walls)
    else:
        min_wall_x, max_wall_x = min_wx, max_wx
        min_wall_y, max_wall_y = min_wy, max_wy

    # Object geometry buffers: name -> (verts, faces, col_name, material)
    buffers = defaultdict(lambda: ([], [], None, None))

    def set_buffer_meta(name, col_name, mat):
        v, f, _, _ = buffers[name]
        buffers[name] = (v, f, col_name, mat)

    set_buffer_meta("Parede_Externa_Norte", "01_Paredes_Externas", mat_ext)
    set_buffer_meta("Parede_Externa_Sul", "01_Paredes_Externas", mat_ext)
    set_buffer_meta("Parede_Externa_Leste", "01_Paredes_Externas", mat_ext)
    set_buffer_meta("Parede_Externa_Oeste", "01_Paredes_Externas", mat_ext)
    set_buffer_meta("Paredes_Internas_Divisorias", "02_Paredes_Internas", mat_int)
    set_buffer_meta("Pisos_Lajes", "03_Pisos_Escadas", mat_floor)
    set_buffer_meta("Escadas_Corrimãos", "03_Pisos_Escadas", mat_floor)
    set_buffer_meta("Moveis_Decoracoes", "04_Moveis_Decoracoes", mat_props)
    set_buffer_meta("Telhado_Vertente_Norte", "05_Telhado", mat_roof)
    set_buffer_meta("Telhado_Vertente_Sul", "05_Telhado", mat_roof)
    set_buffer_meta("Telhado_Vertente_Leste", "05_Telhado", mat_roof)
    set_buffer_meta("Telhado_Vertente_Oeste", "05_Telhado", mat_roof)
    set_buffer_meta("Telhado_Cumeeira", "05_Telhado", mat_roof)
    set_buffer_meta("Telhado_Outros", "05_Telhado", mat_roof)

    def add_box(target_name, bx0, bx1, by0, by1, bz0, bz1):
        if by1 <= by0 or bx1 <= bx0 or bz1 <= bz0: return
        verts, faces, c, m = buffers[target_name]
        idx = len(verts)
        # Blender coordinates: X=x, Y=z (depth), Z=y (height)
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

    def add_custom(target_name, v, f):
        verts, faces, c, m = buffers[target_name]
        idx = len(verts)
        verts.extend(v)
        faces.extend([[p + idx for p in face] for face in f])

    # Stairs helper
    def add_stair_steps(target_name, x0, x1, z0, z1, y_base, y_high, direction):
        num_steps = 4
        h_step = (y_high - y_base) / num_steps
        for k in range(num_steps):
            if direction == 1: # East
                sx0, sx1 = x0 + k * 0.25, x0 + (k + 1) * 0.25
            elif direction == 2: # West
                sx1, sx0 = x1 - k * 0.25, x1 - (k + 1) * 0.25
            else:
                sx0, sx1 = x0, x1
            yk = y_base + (k + 1) * h_step
            add_box(target_name, sx0, sx1, y_base, yk, z0, z1)

    # Synthetic walls on open facades
    existing_walls = set(it[:2] for it in items if (it[4] & 0x10 != 0) or ("wall" in it[6]) or ("window" in it[6]))
    covered_coords = set(it[:2] for it in items if (it[4] & 0x200 != 0) or ("roof" in it[6]) or ("floor" in it[6]))

    west_pts = sorted([wy for wy in range(min_wy, max_wy + 1) if (min_wall_x, wy) in existing_walls])
    if len(west_pts) >= 2:
        for idx in range(len(west_pts) - 1):
            y1, y2 = west_pts[idx], west_pts[idx + 1]
            if 1 < y2 - y1 <= 32:
                gap_cov = any((min_wall_x, y) in covered_coords or (min_wall_x + 1, y) in covered_coords for y in range(y1 + 1, y2))
                if gap_cov:
                    wx0_w = (min_wall_x - center_x) * updater.H_SCALE
                    for y in range(y1 + 1, y2):
                        if (min_wall_x, y) not in existing_walls:
                            wz0 = (y - center_z) * updater.H_SCALE
                            wz1 = wz0 + updater.H_SCALE
                            yt_w = 2.40
                            if (min_wall_x, y) in pitched_roof_coords:
                                cnw, cne, csw, cse = roof_corner_y[(min_wall_x, y)]
                                yt_w = min(yt_w, max(cnw, cne, csw, cse))
                            add_box("Parede_Externa_Oeste", wx0_w, wx0_w + wall_thick, 0.0, yt_w, wz0, wz1)

    east_pts = sorted([wy for wy in range(min_wy, max_wy + 1) if (max_wall_x, wy) in existing_walls])
    if len(east_pts) >= 2:
        for idx in range(len(east_pts) - 1):
            y1, y2 = east_pts[idx], east_pts[idx + 1]
            if 1 < y2 - y1 <= 32:
                gap_cov = any((max_wall_x, y) in covered_coords or (max_wall_x - 1, y) in covered_coords for y in range(y1 + 1, y2))
                if gap_cov:
                    wx0_e = (max_wall_x - center_x) * updater.H_SCALE
                    for y in range(y1 + 1, y2):
                        if (max_wall_x, y) not in existing_walls:
                            wz0 = (y - center_z) * updater.H_SCALE
                            wz1 = wz0 + updater.H_SCALE
                            yt_e = 2.40
                            if (max_wall_x, y) in pitched_roof_coords:
                                cnw, cne, csw, cse = roof_corner_y[(max_wall_x, y)]
                                yt_e = min(yt_e, max(cnw, cne, csw, cse))
                            add_box("Parede_Externa_Leste", wx0_e, wx0_e + wall_thick, 0.0, yt_e, wz0, wz1)

    # Process all items
    for it in items:
        wx, wy, z, item_id, fl, h, name = it
        wx0 = (wx - center_x) * updater.H_SCALE
        wx1 = wx0 + updater.H_SCALE
        wz0 = (wy - center_z) * updater.H_SCALE
        wz1 = wz0 + updater.H_SCALE
        yb  = (z * updater.V_SCALE) - y_base_ground
        yt  = yb + max(h, 1) * updater.V_SCALE

        is_stair = ("stair" in name) or (item_id in (1850, 1852))
        is_floor = (fl & 0x200 != 0) or ("board" in name) or ("floor" in name) or (item_id in updater.STONE_ROOF_TERRACE) or (item_id in (1981, 1986, 1989)) or (item_id in range(2778, 2787))
        is_window = (item_id in (14, 15, 59, 60)) or ("window" in name)
        is_arch = ("arch" in name)
        is_banister = ("banister" in name) or (item_id in (2236, 2240))
        is_pitched_roof = item_id in updater.TRUE_PITCHED_ROOFS
        is_gable = (item_id in (24, 25, 66, 67, 82, 83)) and ("wall" in name) and (h <= 5)
        is_wall = (fl & 0x10 != 0) or ("wall" in name) or (item_id in updater._S_WALLS) or (item_id in updater._E_WALLS) or (item_id in updater._CORN_WALLS) or ("post" in name)

        # 1. Pitched Roof (Smooth underside, no staircase)
        if is_pitched_roof:
            if item_id in updater.ROOF_SLOPE_SOUTH:
                v = [
                    (wx0, wz0, yb), (wx1, wz0, yb), (wx1, wz1, yb + step), (wx0, wz1, yb + step),
                    (wx0, wz0, yb - thick), (wx1, wz0, yb - thick), (wx1, wz1, yb + step - thick), (wx0, wz1, yb + step - thick)
                ]
                f = [(0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1), (3, 2, 6, 7), (0, 3, 7, 4), (1, 5, 6, 2)]
                add_custom("Telhado_Vertente_Sul", v, f)
            elif item_id in updater.ROOF_SLOPE_NORTH:
                v = [
                    (wx0, wz1, yb), (wx1, wz1, yb), (wx1, wz0, yb + step), (wx0, wz0, yb + step),
                    (wx0, wz1, yb - thick), (wx1, wz1, yb - thick), (wx1, wz0, yb + step - thick), (wx0, wz0, yb + step - thick)
                ]
                f = [(0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1), (3, 2, 6, 7), (0, 3, 7, 4), (1, 5, 6, 2)]
                add_custom("Telhado_Vertente_Norte", v, f)
            elif item_id in updater.ROOF_SLOPE_EAST:
                v = [
                    (wx0, wz0, yb), (wx0, wz1, yb), (wx1, wz1, yb + step), (wx1, wz0, yb + step),
                    (wx0, wz0, yb - thick), (wx0, wz1, yb - thick), (wx1, wz1, yb + step - thick), (wx1, wz0, yb + step - thick)
                ]
                f = [(0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1), (3, 2, 6, 7), (0, 3, 7, 4), (1, 5, 6, 2)]
                add_custom("Telhado_Vertente_Leste", v, f)
            elif item_id in updater.ROOF_SLOPE_WEST:
                v = [
                    (wx1, wz0, yb), (wx1, wz1, yb), (wx0, wz1, yb + step), (wx0, wz0, yb + step),
                    (wx1, wz0, yb - thick), (wx1, wz1, yb - thick), (wx0, wz1, yb + step - thick), (wx0, wz0, yb + step - thick)
                ]
                f = [(0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1), (3, 2, 6, 7), (0, 3, 7, 4), (1, 5, 6, 2)]
                add_custom("Telhado_Vertente_Oeste", v, f)
            elif item_id in updater.ROOF_RIDGE_EW:
                wz_mid = wz0 + 0.5 * updater.H_SCALE
                v = [
                    (wx0, wz0, yb), (wx1, wz0, yb), (wx1, wz_mid, yb + step), (wx0, wz_mid, yb + step),
                    (wx1, wz1, yb), (wx0, wz1, yb),
                    (wx0, wz0, yb - thick), (wx1, wz0, yb - thick), (wx1, wz_mid, yb + step - thick), (wx0, wz_mid, yb + step - thick),
                    (wx1, wz1, yb - thick), (wx0, wz1, yb - thick)
                ]
                f = [(0, 1, 2, 3), (3, 2, 4, 5), (9, 8, 7, 6), (11, 10, 8, 9), (0, 6, 7, 1), (4, 10, 11, 5)]
                add_custom("Telhado_Cumeeira", v, f)
            elif item_id in updater.ROOF_RIDGE_NS:
                wx_mid = wx0 + 0.5 * updater.H_SCALE
                v = [
                    (wx0, wz0, yb), (wx_mid, wz0, yb + step), (wx_mid, wz1, yb + step), (wx0, wz1, yb),
                    (wx1, wz0, yb), (wx1, wz1, yb),
                    (wx0, wz0, yb - thick), (wx_mid, wz0, yb + step - thick), (wx_mid, wz1, yb + step - thick), (wx0, wz1, yb - thick),
                    (wx1, wz0, yb - thick), (wx1, wz1, yb - thick)
                ]
                f = [(0, 1, 2, 3), (1, 4, 5, 2), (9, 8, 7, 6), (11, 10, 7, 8), (0, 6, 7, 1), (3, 9, 10, 2)]
                add_custom("Telhado_Cumeeira", v, f)
            else:
                v = [
                    (wx0, wz0, yb), (wx1, wz0, yb), (wx1, wz1, yb + step), (wx0, wz1, yb + step),
                    (wx0, wz0, yb - thick), (wx1, wz0, yb - thick), (wx1, wz1, yb + step - thick), (wx0, wz1, yb + step - thick)
                ]
                f = [(0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1), (3, 2, 6, 7), (0, 3, 7, 4), (1, 5, 6, 2)]
                add_custom("Telhado_Outros", v, f)
            continue

        # 2. Stairs & Banisters
        if is_stair:
            direction = (fl >> 30) & 3
            if item_id == 1850: direction = 2
            elif item_id == 1852: direction = 1
            y_high = yb + max(h, 5) * updater.V_SCALE
            add_stair_steps("Escadas_Corrimãos", wx0, wx1, wz0, wz1, yb, y_high, direction)
            continue

        if is_banister:
            b_thick = 0.10 * updater.H_SCALE
            add_box("Escadas_Corrimãos", wx0, wx1, yb, yt, wz0, wz0 + b_thick)
            continue

        # 3. Floors & Terraces
        if is_floor:
            f_thick = 0.15 if item_id in updater.STONE_ROOF_TERRACE else 0.10
            add_box("Pisos_Lajes", wx0, wx1, yb - f_thick, yb, wz0, wz1)
            continue

        # 4. Walls
        if is_wall or is_window or is_gable:
            # Determine target wall object
            if wy == min_wall_y: wall_group = "Parede_Externa_Norte"
            elif wy == max_wall_y: wall_group = "Parede_Externa_Sul"
            elif wx == min_wall_x: wall_group = "Parede_Externa_Oeste"
            elif wx == max_wall_x: wall_group = "Parede_Externa_Leste"
            else: wall_group = "Paredes_Internas_Divisorias"

            if (wx, wy) in pitched_roof_coords:
                cnw, cne, csw, cse = roof_corner_y[(wx, wy)]
                yt = min(yt, max(cnw, cne, csw, cse))

            if is_gable:
                add_box(wall_group, wx0, wx1, yb, yt, wz0, wz0 + wall_thick)
                continue

            if is_window:
                is_south = item_id in (14, 59) or item_id in updater._S_WALLS or "south" in name
                y_sill = yb + max(h, 1) * 0.35 * updater.V_SCALE
                y_lintel = yb + max(h, 1) * 0.75 * updater.V_SCALE
                if is_south or wall_group in ("Parede_Externa_Norte", "Parede_Externa_Sul"):
                    add_box(wall_group, wx0, wx1, yb, y_sill, wz0, wz0 + wall_thick)
                    add_box(wall_group, wx0, wx1, y_lintel, yt, wz0, wz0 + wall_thick)
                    add_box(wall_group, wx0, wx0 + 0.25, y_sill, y_lintel, wz0, wz0 + wall_thick)
                    add_box(wall_group, wx1 - 0.25, wx1, y_sill, y_lintel, wz0, wz0 + wall_thick)
                else:
                    add_box(wall_group, wx0, wx0 + wall_thick, yb, y_sill, wz0, wz1)
                    add_box(wall_group, wx0, wx0 + wall_thick, y_lintel, yt, wz0, wz1)
                    add_box(wall_group, wx0, wx0 + wall_thick, y_sill, y_lintel, wz0, wz0 + 0.25)
                    add_box(wall_group, wx0, wx0 + wall_thick, y_sill, y_lintel, wz1 - 0.25, wz1)
                continue

            # Standard walls
            is_south  = (item_id in updater._S_WALLS) or ("south" in name)
            is_east   = (item_id in updater._E_WALLS) or ("east" in name)
            is_corner = (item_id in updater._CORN_WALLS) or ("corner" in name)
            is_post   = (item_id in updater._POST_WALLS) or ("post" in name)

            if is_south and not is_east:
                add_box(wall_group, wx0, wx1, yb, yt, wz0, wz0 + wall_thick)
            elif is_east and not is_south:
                add_box(wall_group, wx0, wx0 + wall_thick, yb, yt, wz0, wz1)
            elif is_corner:
                add_box(wall_group, wx0, wx0 + wall_thick, yb, yt, wz0, wz1)
                add_box(wall_group, wx0 + wall_thick, wx1, yb, yt, wz0, wz0 + wall_thick)
            elif is_post:
                add_box(wall_group, wx0, wx0 + wall_thick, yb, yt, wz0, wz0 + wall_thick)
            else:
                if wall_group in ("Parede_Externa_Norte", "Parede_Externa_Sul"):
                    add_box(wall_group, wx0, wx1, yb, yt, wz0, wz0 + wall_thick)
                else:
                    add_box(wall_group, wx0, wx0 + wall_thick, yb, yt, wz0, wz1)
            continue

        # 5. Props & Furniture
        add_box("Moveis_Decoracoes", wx0 + 0.1, wx1 - 0.1, yb, yt, wz0 + 0.1, wz1 - 0.1)

    # Create Blender Objects & weld vertices
    created_objs = []
    house_objs = []
    roof_objs = []

    for name, (verts, faces, cname, mat) in list(buffers.items()):
        if not verts or not faces:
            continue
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(verts, [], faces)
        mesh.update()

        # Remove doubles for clean edges and loops
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.001)
        bm.to_mesh(mesh)
        bm.free()
        mesh.update()

        obj = bpy.data.objects.new(name, mesh)
        if mat:
            obj.data.materials.append(mat)
        cols[cname].objects.link(obj)
        created_objs.append(obj)
        if cname == "05_Telhado":
            roof_objs.append(obj)
        else:
            house_objs.append(obj)

    # Remove empty collections
    for cname, c in list(cols.items()):
        if len(c.objects) == 0:
            scene.collection.children.unlink(c)
            bpy.data.collections.remove(c)

    # Save Native Blender (.blend) files
    blend_by_walls = str(fpath / "building_by_walls.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend_by_walls)
    blend_lego = str(fpath / "building_lego.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend_lego)

    # Export Modular GLB (all walls as nodes)
    glb_by_walls = str(fpath / "model_by_walls.glb")
    bpy.ops.export_scene.gltf(filepath=glb_by_walls, export_format='GLB')
    glb_lego = str(fpath / "model_modular_lego.glb")
    bpy.ops.export_scene.gltf(filepath=glb_lego, export_format='GLB')

    # Export Standalone House
    for ro in roof_objs: ro.hide_set(True)
    for ho in house_objs: ho.hide_set(False)
    glb_house = str(fpath / "model_base_house.glb")
    bpy.ops.export_scene.gltf(filepath=glb_house, export_format='GLB', use_visible=True)
    bpy.ops.wm.obj_export(filepath=str(fpath / "model_base_house.obj"), export_selected_objects=False)

    # Export Standalone Roof
    for ho in house_objs: ho.hide_set(True)
    for ro in roof_objs: ro.hide_set(False)
    glb_roof = str(fpath / "model_base_roof.glb")
    bpy.ops.export_scene.gltf(filepath=glb_roof, export_format='GLB', use_visible=True)
    bpy.ops.wm.obj_export(filepath=str(fpath / "model_base_roof.obj"), export_selected_objects=False)

    # Export Consolidated model_base.glb (House + Roof visible)
    for ro in roof_objs: ro.hide_set(False)
    for ho in house_objs: ho.hide_set(False)
    glb_base = str(fpath / "model_base.glb")
    bpy.ops.export_scene.gltf(filepath=glb_base, export_format='GLB', use_visible=True)
    bpy.ops.wm.obj_export(filepath=str(fpath / "model_base.obj"), export_selected_objects=False)

    # Sync to community_assets
    rel_folder = fpath.relative_to("/home/mnunes/uo3d-community-buildings")
    comm_target = Path("/home/mnunes/uo3d_map/community_assets") / rel_folder
    if comm_target.exists():
        for fname in [
            "building_by_walls.blend", "building_lego.blend",
            "model_by_walls.glb", "model_modular_lego.glb",
            "model_base.glb", "model_base_house.glb", "model_base_roof.glb",
            "model_base.obj", "model_base.mtl",
            "model_base_house.obj", "model_base_house.mtl",
            "model_base_roof.obj", "model_base_roof.mtl"
        ]:
            src = fpath / fname
            dst = comm_target / fname
            if src.exists():
                shutil.copy2(src, dst)

    return True, f"{len(created_objs)} objects created across {len(scene.collection.children)} collections"

def main():
    target_city = "map0_felucca/britain"
    if len(sys.argv) > 1 and not sys.argv[-1].endswith(".py"):
        target_city = sys.argv[-1]

    city_path = Path(target_city).resolve()
    building_dirs = sorted([d for d in city_path.iterdir() if d.is_dir() and (d / "info.json").exists()])

    total = len(building_dirs)
    print(f"=== PROCESSING CITY: {city_path.name} ({total} buildings) ===")

    success_count = 0
    fail_count = 0

    for idx, bdir in enumerate(building_dirs, 1):
        print(f"[{idx:02d}/{total}] Processing {bdir.name}...", end=" ", flush=True)
        try:
            ok, msg = process_single_building(bdir)
            if ok:
                success_count += 1
                print(f"OK ({msg})")
            else:
                fail_count += 1
                print(f"FAILED ({msg})")
        except Exception as e:
            fail_count += 1
            print(f"ERROR: {e}")

    print(f"\n=== COMPLETED: {success_count} succeeded, {fail_count} failed out of {total} buildings ===")

if __name__ == "__main__":
    main()
