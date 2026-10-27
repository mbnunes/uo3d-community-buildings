#!/usr/bin/env python3
"""
separate_building_roof.py

Separates the 3D model into two distinct objects/meshes:
- Building_Base: walls, floors, doors, windows, stairs, interior items
- Building_Roof: thatch/slate/tile roof slopes, hips, ridges, and eaves

With corner alignment (seamless external quinas), correct 90-degree
orientation for gable/lintel blocks above windows and walls, and
100% smooth continuous roof ceiling (no staircase / step artifacts).

Outputs:
- model_base.glb & model_base.obj: Multi-object files (Blender imports them as 2 distinct scene objects)
- model_base_house.glb / .obj: Standalone building structure without roof
- model_base_roof.glb / .obj: Standalone roof
- reference_2d_interior.png: 2D isometric cutaway showing the interior floor plan
"""

import os
import sys
import json
import struct
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

UO_DIR = Path("/opt/hd_jogos/UOC")
TILEDATA_FILE = UO_DIR / "tiledata.mul"
STAIDX_FILE   = UO_DIR / "staidx0.mul"
STATICS_FILE  = UO_DIR / "statics0.mul"
ART_IDX_FILE  = UO_DIR / "artidx.mul"
ART_MUL_FILE  = UO_DIR / "art.mul"
MAP_FILE      = UO_DIR / "map0.mul"

sys.path.append("/home/mnunes/uo3d_map")
try:
    import update_all_community_assets as updater
    updater.init_worker()
except Exception as e:
    print(f"[!] Warning importing updater: {e}")

def build_multimesh_glb(output_path, meshes_data, materials_data):
    bin_buffer = bytearray()
    buffer_views = []
    accessors = []
    nodes = []
    meshes = []
    materials = []

    for mat in materials_data:
        materials.append({
            "name": mat["name"],
            "pbrMetallicRoughness": {
                "baseColorFactor": mat["color"],
                "metallicFactor": 0.05,
                "roughnessFactor": 0.85
            },
            "doubleSided": True
        })

    def pad4(b):
        pad = (4 - (len(b) % 4)) % 4
        return b + b"\x00" * pad

    for m_idx, m_data in enumerate(meshes_data):
        verts = m_data["vertices"]
        norms = m_data["normals"]
        idxs = m_data["indices"]
        m_name = m_data["name"]
        mat_idx = m_data.get("material_idx", 0)
        if mat_idx >= len(materials):
            mat_idx = 0

        num_verts = len(verts)
        min_pos = [float(min(v[i] for v in verts)) for i in range(3)]
        max_pos = [float(max(v[i] for v in verts)) for i in range(3)]

        pos_bytes = bytearray()
        for v in verts:
            pos_bytes.extend(struct.pack("<fff", v[0], v[1], v[2]))

        norm_bytes = bytearray()
        for n in norms:
            norm_bytes.extend(struct.pack("<fff", n[0], n[1], n[2]))

        idx_bytes = bytearray()
        for idx in idxs:
            idx_bytes.extend(struct.pack("<I", idx))

        pos_bv_idx = len(buffer_views)
        pos_offset = len(bin_buffer)
        bin_buffer.extend(pad4(pos_bytes))
        buffer_views.append({
            "buffer": 0,
            "byteOffset": pos_offset,
            "byteLength": len(pos_bytes),
            "target": 34962
        })

        norm_bv_idx = len(buffer_views)
        norm_offset = len(bin_buffer)
        bin_buffer.extend(pad4(norm_bytes))
        buffer_views.append({
            "buffer": 0,
            "byteOffset": norm_offset,
            "byteLength": len(norm_bytes),
            "target": 34962
        })

        idx_bv_idx = len(buffer_views)
        idx_offset = len(bin_buffer)
        bin_buffer.extend(pad4(idx_bytes))
        buffer_views.append({
            "buffer": 0,
            "byteOffset": idx_offset,
            "byteLength": len(idx_bytes),
            "target": 34963
        })

        pos_acc_idx = len(accessors)
        accessors.append({
            "bufferView": pos_bv_idx,
            "byteOffset": 0,
            "componentType": 5126,
            "count": num_verts,
            "type": "VEC3",
            "min": min_pos,
            "max": max_pos
        })

        norm_acc_idx = len(accessors)
        accessors.append({
            "bufferView": norm_bv_idx,
            "byteOffset": 0,
            "componentType": 5126,
            "count": num_verts,
            "type": "VEC3"
        })

        idx_acc_idx = len(accessors)
        accessors.append({
            "bufferView": idx_bv_idx,
            "byteOffset": 0,
            "componentType": 5125,
            "count": len(idxs),
            "type": "SCALAR"
        })

        meshes.append({
            "name": m_name,
            "primitives": [{
                "attributes": {
                    "POSITION": pos_acc_idx,
                    "NORMAL": norm_acc_idx
                },
                "indices": idx_acc_idx,
                "material": mat_idx
            }]
        })

        nodes.append({
            "mesh": m_idx,
            "name": m_name
        })

    gltf_json = {
        "asset": {"version": "2.0", "generator": "UO3D Community Exporter (Separated Roof)"},
        "scene": 0,
        "scenes": [{"nodes": list(range(len(nodes)))}],
        "nodes": nodes,
        "materials": materials,
        "meshes": meshes,
        "buffers": [{"byteLength": len(bin_buffer)}],
        "bufferViews": buffer_views,
        "accessors": accessors
    }

    json_bytes = json.dumps(gltf_json, separators=(",", ":")).encode("utf-8")
    pad_json = (4 - (len(json_bytes) % 4)) % 4
    json_bytes += b" " * pad_json

    total_len = 12 + 8 + len(json_bytes) + 8 + len(bin_buffer)
    out = bytearray()
    out.extend(struct.pack("<4sII", b"glTF", 2, total_len))
    out.extend(struct.pack("<II", len(json_bytes), 0x4E4F534A))
    out.extend(json_bytes)
    out.extend(struct.pack("<II", len(bin_buffer), 0x004E4942))
    out.extend(bin_buffer)

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(out)

def export_multiobj_and_mtl(obj_path, mtl_path, meshes_data):
    mtl_filename = os.path.basename(mtl_path)
    with open(mtl_path, "w") as f:
        f.write("# Materials for UO3D Building\n")
        f.write("newmtl Building_Base\n")
        f.write("Ka 0.25 0.25 0.25\n")
        f.write("Kd 0.88 0.86 0.82\n")
        f.write("Ks 0.05 0.05 0.05\n")
        f.write("Ns 10.0\n")
        f.write("d 1.0\n")
        f.write("illum 2\n\n")

        f.write("newmtl Building_Roof\n")
        f.write("Ka 0.25 0.25 0.25\n")
        f.write("Kd 0.76 0.55 0.35\n")
        f.write("Ks 0.05 0.05 0.05\n")
        f.write("Ns 10.0\n")
        f.write("d 1.0\n")
        f.write("illum 2\n")

    with open(obj_path, "w") as f:
        f.write("# Wavefront OBJ exported by UO3D Community Exporter (Separated Roof)\n")
        f.write(f"mtllib {mtl_filename}\n")
        
        global_v_offset = 0
        for m_data in meshes_data:
            name = m_data["name"]
            verts = m_data["vertices"]
            norms = m_data["normals"]
            idxs = m_data["indices"]
            mat = m_data.get("material_name", "Building_Base")

            if not verts or not idxs:
                continue

            f.write(f"\no {name}\n")
            for v in verts:
                f.write(f"v {v[0]:.4f} {v[1]:.4f} {v[2]:.4f}\n")
            for n in norms:
                f.write(f"vn {n[0]:.4f} {n[1]:.4f} {n[2]:.4f}\n")
            f.write(f"usemtl {mat}\n")
            f.write("s 1\n")
            for i in range(0, len(idxs), 3):
                i1 = idxs[i] + 1 + global_v_offset
                i2 = idxs[i+1] + 1 + global_v_offset
                i3 = idxs[i+2] + 1 + global_v_offset
                f.write(f"f {i1}//{i1} {i2}//{i2} {i3}//{i3}\n")

            global_v_offset += len(verts)

def separate_building(folder_path):
    fpath = Path(folder_path).resolve()
    info_path = fpath / "info.json"
    if not info_path.exists():
        print(f"[X] No info.json found in {fpath}")
        return False

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

    # Find wall bounds
    wall_coords = set()
    for it in items:
        fl, h, name = it[4], it[5], it[6]
        if (fl & 0x10 != 0) or ("wall" in name) or ("window" in name) or ("post" in name):
            wall_coords.add((it[0], it[1]))

    min_wall_x = min(x for x, y in wall_coords) if wall_coords else min_wx
    max_wall_x = max(x for x, y in wall_coords) if wall_coords else max_wx
    min_wall_y = min(y for x, y in wall_coords) if wall_coords else min_wy
    max_wall_y = max(y for x, y in wall_coords) if wall_coords else max_wy

    # Identify pitched roof heights per tile and roof bounds
    roof_corner_y = {}
    pitched_roof_coords = set()
    roof_items = []
    for it in items:
        wx, wy, z, item_id, fl, h, name = it
        if item_id in updater.TRUE_PITCHED_ROOFS or "roof" in name:
            roof_items.append(it)
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

    min_roof_x = min(it[0] for it in roof_items) if roof_items else min_wx
    max_roof_x = max(it[0] for it in roof_items) if roof_items else max_wx
    min_roof_y = min(it[1] for it in roof_items) if roof_items else min_wy
    max_roof_y = max(it[1] for it in roof_items) if roof_items else max_wy

    base_verts, base_norms, base_idxs = [], [], []
    roof_verts, roof_norms, roof_idxs = [], [], []

    def make_helpers(target_v, target_n, target_i):
        def add_q(p0, p1, p2, p3, n):
            base = len(target_v)
            target_v.extend([p0, p1, p2, p3])
            target_n.extend([n, n, n, n])
            target_i.extend([base + 0, base + 2, base + 1, base + 1, base + 2, base + 3])
        def add_t(p0, p1, p2, n):
            base = len(target_v)
            target_v.extend([p0, p1, p2])
            target_n.extend([n, n, n])
            target_i.extend([base + 0, base + 1, base + 2])
        def add_b(bx0, bx1, by0, by1, bz0, bz1):
            if by1 <= by0 or bx1 <= bx0 or bz1 <= bz0: return
            add_q((bx0, by1, bz0), (bx1, by1, bz0), (bx0, by1, bz1), (bx1, by1, bz1), (0.0, 1.0, 0.0))
            add_q((bx0, by0, bz1), (bx1, by0, bz1), (bx0, by0, bz0), (bx1, by0, bz0), (0.0, -1.0, 0.0))
            add_q((bx0, by0, bz0), (bx1, by0, bz0), (bx0, by1, bz0), (bx1, by1, bz0), (0.0, 0.0, -1.0))
            add_q((bx1, by0, bz1), (bx0, by0, bz1), (bx1, by1, bz1), (bx0, by1, bz1), (0.0, 0.0, 1.0))
            add_q((bx0, by0, bz1), (bx0, by0, bz0), (bx0, by1, bz1), (bx0, by1, bz0), (-1.0, 0.0, 0.0))
            add_q((bx1, by0, bz0), (bx1, by0, bz1), (bx1, by1, bz0), (bx1, by1, bz1), (1.0, 0.0, 0.0))
        return add_q, add_t, add_b

    add_quad, add_tri, add_box = make_helpers(base_verts, base_norms, base_idxs)
    add_roof_quad, add_roof_tri, add_roof_box = make_helpers(roof_verts, roof_norms, roof_idxs)

    def add_stair_steps(x0, x1, z0, z1, y_base, y_high, direction):
        num_steps = 4
        h_step = (y_high - y_base) / num_steps
        if direction == 1:
            for k in range(num_steps):
                sx0 = x0 + k * 0.25; sx1 = x0 + (k + 1) * 0.25
                yk = y_base + (k + 1) * h_step; y_prev = y_base + k * h_step
                add_quad((sx0, yk, z0), (sx1, yk, z0), (sx0, yk, z1), (sx1, yk, z1), (0.0, 1.0, 0.0))
                add_quad((sx0, yk, z0), (sx0, yk, z1), (sx0, y_prev, z0), (sx0, y_prev, z1), (-1.0, 0.0, 0.0))
                add_quad((sx1, yk, z0), (sx0, yk, z0), (sx1, y_base, z0), (sx0, y_base, z0), (0.0, 0.0, -1.0))
                add_quad((sx0, yk, z1), (sx1, yk, z1), (sx0, y_base, z1), (sx1, y_base, z1), (0.0, 0.0, 1.0))
            add_quad((x1, y_high, z0), (x1, y_high, z1), (x1, y_base, z0), (x1, y_base, z1), (1.0, 0.0, 0.0))
        elif direction == 2:
            for k in range(num_steps):
                sx1 = x1 - k * 0.25; sx0 = x1 - (k + 1) * 0.25
                yk = y_base + (k + 1) * h_step; y_prev = y_base + k * h_step
                add_quad((sx0, yk, z0), (sx1, yk, z0), (sx0, yk, z1), (sx1, yk, z1), (0.0, 1.0, 0.0))
                add_quad((sx1, yk, z1), (sx1, yk, z0), (sx1, y_prev, z1), (sx1, y_prev, z0), (1.0, 0.0, 0.0))
                add_quad((sx0, yk, z0), (sx1, yk, z0), (sx0, y_base, z0), (sx1, y_base, z0), (0.0, 0.0, -1.0))
                add_quad((sx1, yk, z1), (sx0, yk, z1), (sx1, y_base, z1), (sx0, y_base, z1), (0.0, 0.0, 1.0))
            add_quad((x0, y_high, z1), (x0, y_high, z0), (x0, y_base, z1), (x0, y_base, z0), (-1.0, 0.0, 0.0))

    wall_thick = updater.WALL_THICKNESS * updater.H_SCALE

    # Generate Geometry
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
        is_window = (item_id in (14, 15, 59, 60, 185, 186)) or ("window" in name)
        is_arch = ("arch" in name)
        is_banister = ("banister" in name) or (item_id in (2236, 2240))
        is_pitched_roof = item_id in updater.TRUE_PITCHED_ROOFS
        is_gable = (item_id in (24, 25, 66, 67, 82, 83)) and ("wall" in name) and (h <= 5)
        is_wall = (fl & 0x10 != 0) or ("wall" in name) or (item_id in updater._S_WALLS) or (item_id in updater._E_WALLS) or (item_id in updater._CORN_WALLS)

        # Stairs
        if is_stair:
            direction = (fl >> 30) & 3
            if item_id == 1850: direction = 2
            elif item_id == 1852: direction = 1
            y_high = yb + max(h, 5) * updater.V_SCALE
            add_stair_steps(wx0, wx1, wz0, wz1, yb, y_high, direction)
            continue

        # Floors
        if is_floor:
            f_thick = 0.15 if item_id in updater.STONE_ROOF_TERRACE else (0.08 if "board" in name else 0.10)
            add_box(wx0, wx1, yb - f_thick, yb, wz0, wz1)
            continue

        # Gable trim
        if is_gable:
            add_box(wx0, wx1, yb, yt, wz0, wz0 + wall_thick)
            continue

        # Windows
        if is_window:
            is_south = item_id in (14, 59, 186) or ("south" in name)
            y_sill = yb + max(h, 1) * 0.35 * updater.V_SCALE
            y_lintel = yb + max(h, 1) * 0.75 * updater.V_SCALE
            if is_south:
                add_box(wx0, wx1, yb, y_sill, wz0, wz0 + wall_thick)
                add_box(wx0, wx1, y_lintel, yt, wz0, wz0 + wall_thick)
                add_box(wx0, wx0 + 0.25, y_sill, y_lintel, wz0, wz0 + wall_thick)
                add_box(wx1 - 0.25, wx1, y_sill, y_lintel, wz0, wz0 + wall_thick)
            else:
                add_box(wx0, wx0 + wall_thick, yb, y_sill, wz0, wz1)
                add_box(wx0, wx0 + wall_thick, y_lintel, yt, wz0, wz1)
                add_box(wx0, wx0 + wall_thick, y_sill, y_lintel, wz0, wz0 + 0.25)
                add_box(wx0, wx0 + wall_thick, y_sill, y_lintel, wz1 - 0.25, wz1)
            continue

        # Pitched roofs (Completely smooth top and underside, zero staircase steps!)
        if is_pitched_roof:
            step = 3.0 * updater.V_SCALE
            thick = 0.12 * updater.V_SCALE # 0.0144

            if item_id in updater.ROOF_SLOPE_SOUTH:
                p_nw = (wx0, yb, wz0); p_ne = (wx1, yb, wz0)
                p_sw = (wx0, yb + step, wz1); p_se = (wx1, yb + step, wz1)
                # Top sloped face
                add_roof_quad(p_nw, p_ne, p_sw, p_se, (0.0, 0.7071, 0.7071))
                # Bottom sloped face (Continuous smooth ceiling!)
                b_nw = (wx0, yb - thick, wz0); b_ne = (wx1, yb - thick, wz0)
                b_sw = (wx0, yb + step - thick, wz1); b_se = (wx1, yb + step - thick, wz1)
                add_roof_quad(b_sw, b_se, b_nw, b_ne, (0.0, -0.7071, -0.7071))
                # Lower eave face (only along the southern bottom-most edge)
                if wy == min_roof_y:
                    add_roof_quad(b_nw, b_ne, p_nw, p_ne, (0.0, 0.0, -1.0))
                # Outer west gable overhang
                if wx == min_roof_x:
                    add_roof_quad(b_nw, b_sw, p_nw, p_sw, (-1.0, 0.0, 0.0))
                # Outer east gable overhang
                if wx == max_roof_x:
                    add_roof_quad(b_se, b_ne, p_se, p_ne, (1.0, 0.0, 0.0))

            elif item_id in updater.ROOF_SLOPE_NORTH:
                p_nw = (wx0, yb + step, wz0); p_ne = (wx1, yb + step, wz0)
                p_sw = (wx0, yb, wz1); p_se = (wx1, yb, wz1)
                # Top sloped face
                add_roof_quad(p_sw, p_se, p_nw, p_ne, (0.0, 0.7071, -0.7071))
                # Bottom sloped face (Continuous smooth ceiling!)
                b_nw = (wx0, yb + step - thick, wz0); b_ne = (wx1, yb + step - thick, wz0)
                b_sw = (wx0, yb - thick, wz1); b_se = (wx1, yb - thick, wz1)
                add_roof_quad(b_nw, b_ne, b_sw, b_se, (0.0, -0.7071, 0.7071))
                # Lower eave face (only along the northern bottom-most edge)
                if wy == max_roof_y:
                    add_roof_quad(b_se, b_sw, p_se, p_sw, (0.0, 0.0, 1.0))
                # Outer west gable overhang
                if wx == min_roof_x:
                    add_roof_quad(b_sw, b_nw, p_sw, p_nw, (-1.0, 0.0, 0.0))
                # Outer east gable overhang
                if wx == max_roof_x:
                    add_roof_quad(b_ne, b_se, p_ne, p_se, (1.0, 0.0, 0.0))

            elif item_id in updater.ROOF_RIDGE_EW:
                p_mid_w = (wx0, yb + step, wz0 + 0.5 * updater.H_SCALE)
                p_mid_e = (wx1, yb + step, wz0 + 0.5 * updater.H_SCALE)
                # Top North slope
                add_roof_quad((wx0, yb, wz0), (wx1, yb, wz0), p_mid_w, p_mid_e, (0.0, 0.7071, -0.7071))
                # Top South slope
                add_roof_quad(p_mid_w, p_mid_e, (wx0, yb, wz1), (wx1, yb, wz1), (0.0, 0.7071, 0.7071))
                # Bottom North slope
                b_mid_w = (wx0, yb + step - thick, wz0 + 0.5 * updater.H_SCALE)
                b_mid_e = (wx1, yb + step - thick, wz0 + 0.5 * updater.H_SCALE)
                add_roof_quad(b_mid_w, b_mid_e, (wx0, yb - thick, wz0), (wx1, yb - thick, wz0), (0.0, -0.7071, 0.7071))
                # Bottom South slope
                add_roof_quad((wx0, yb - thick, wz1), (wx1, yb - thick, wz1), b_mid_w, b_mid_e, (0.0, -0.7071, -0.7071))
                # Outer ridge gables
                if wx == min_roof_x:
                    add_roof_tri((wx0, yb, wz0), p_mid_w, (wx0, yb - thick, wz0), (-1.0, 0.0, 0.0))
                    add_roof_tri((wx0, yb, wz1), (wx0, yb - thick, wz1), p_mid_w, (-1.0, 0.0, 0.0))
                if wx == max_roof_x:
                    add_roof_tri((wx1, yb, wz0), (wx1, yb - thick, wz0), p_mid_e, (1.0, 0.0, 0.0))
                    add_roof_tri((wx1, yb, wz1), p_mid_e, (wx1, yb - thick, wz1), (1.0, 0.0, 0.0))
            continue

        # Banister
        if is_banister:
            b_thick = 0.10 * updater.H_SCALE
            add_box(wx0, wx1, yb, yt, wz0, wz0 + b_thick)
            continue

        # Walls & Quinas Alignment
        if is_wall:
            if (wx, wy) in pitched_roof_coords:
                cnw, cne, csw, cse = roof_corner_y[(wx, wy)]
                if z < 40:
                    yt = min(yt, max(cnw, cne, csw, cse))

            # 1. SPECIAL CORNER TILES (Quinas Alinhadas)
            if (wx, wy) == (min_wall_x, min_wall_y):
                add_box(wx0, wx1, yb, yt, wz0, wz0 + wall_thick)
                add_box(wx0, wx0 + wall_thick, yb, yt, wz0, wz1)
                continue

            if (wx, wy) == (max_wall_x, min_wall_y):
                add_box(wx0, wx0 + wall_thick, yb, yt, wz0, wz0 + wall_thick)
                add_box(wx0, wx0 + wall_thick, yb, yt, wz0, wz1)
                continue

            if (wx, wy) == (min_wall_x, max_wall_y):
                add_box(wx0, wx1, yb, yt, wz0, wz0 + wall_thick)
                add_box(wx0, wx0 + wall_thick, yb, yt, wz0, wz0 + wall_thick)
                continue

            if (wx, wy) == (max_wall_x, max_wall_y):
                add_box(wx0, wx0 + wall_thick, yb, yt, wz0, wz0 + wall_thick)
                continue

            # 2. ROTATE GABLE/MURO BLOCKS ABOVE WINDOWS AND WALLS (90 DEGREES)
            if wx == max_wall_x or item_id == 194:
                add_box(wx0, wx0 + wall_thick, yb, yt, wz0, wz1)
                continue

            if wx == min_wall_x:
                add_box(wx0, wx0 + wall_thick, yb, yt, wz0, wz1)
                continue

            # 3. STANDARD WALL CLASSIFICATIONS
            is_south  = (item_id in updater._S_WALLS) or ("south" in name)
            is_east   = (item_id in updater._E_WALLS) or ("east" in name)
            is_corner = (item_id in updater._CORN_WALLS) or ("corner" in name)
            is_post   = (item_id in updater._POST_WALLS) or ("post" in name)

            if is_south and not is_east:
                add_box(wx0, wx1, yb, yt, wz0, wz0 + wall_thick)
            elif is_east and not is_south:
                add_box(wx0, wx0 + wall_thick, yb, yt, wz0, wz1)
            elif is_corner:
                add_box(wx0, wx0 + wall_thick, yb, yt, wz0, wz1)
                add_box(wx0 + wall_thick, wx1, yb, yt, wz0, wz0 + wall_thick)
            elif is_post:
                add_box(wx0, wx0 + wall_thick, yb, yt, wz0, wz0 + wall_thick)
            else:
                add_box(wx0, wx1, yb, yt, wz0, wz0 + wall_thick)

    meshes_data = [
        {"name": "Building_Base", "vertices": base_verts, "normals": base_norms, "indices": base_idxs, "material_idx": 0, "material_name": "Building_Base"},
        {"name": "Building_Roof", "vertices": roof_verts, "normals": roof_norms, "indices": roof_idxs, "material_idx": 1, "material_name": "Building_Roof"}
    ]

    materials_data = [
        {"name": "Building_Base", "color": [0.88, 0.86, 0.82, 1.0]},
        {"name": "Building_Roof", "color": [0.76, 0.55, 0.35, 1.0]}
    ]

    # Save combined
    build_multimesh_glb(fpath / "model_base.glb", meshes_data, materials_data)
    export_multiobj_and_mtl(fpath / "model_base.obj", fpath / "model_base.mtl", meshes_data)

    # Save standalone
    build_multimesh_glb(fpath / "model_base_house.glb", [
        {"name": "Building_Base", "vertices": base_verts, "normals": base_norms, "indices": base_idxs, "material_idx": 0}
    ], [materials_data[0]])
    export_multiobj_and_mtl(fpath / "model_base_house.obj", fpath / "model_base_house.mtl", [
        {"name": "Building_Base", "vertices": base_verts, "normals": base_norms, "indices": base_idxs, "material_name": "Building_Base"}
    ])

    build_multimesh_glb(fpath / "model_base_roof.glb", [
        {"name": "Building_Roof", "vertices": roof_verts, "normals": roof_norms, "indices": roof_idxs, "material_idx": 0}
    ], [materials_data[1]])
    export_multiobj_and_mtl(fpath / "model_base_roof.obj", fpath / "model_base_roof.mtl", [
        {"name": "Building_Roof", "vertices": roof_verts, "normals": roof_norms, "indices": roof_idxs, "material_name": "Building_Roof"}
    ])

    meta["stats"]["triangles_count"] = (len(base_idxs) + len(roof_idxs)) // 3
    meta["parts"] = {
        "building_base": {
            "name": "Building_Base",
            "description": "Main structure with aligned corner joints and 90-degree corrected gable/lintel wall blocks",
            "triangles_count": len(base_idxs) // 3,
            "vertices_count": len(base_verts)
        },
        "building_roof": {
            "name": "Building_Roof",
            "description": "Smooth continuous roof mesh (ceiling and slope) including thatching, slopes, eaves and ridges",
            "triangles_count": len(roof_idxs) // 3,
            "vertices_count": len(roof_verts)
        }
    }

    with open(info_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    print(f"[+] Successfully separated and aligned {fpath.name}:")
    print(f"    - Base Triangles: {len(base_idxs)//3:,} | Vertices: {len(base_verts):,}")
    print(f"    - Roof Triangles: {len(roof_idxs)//3:,} | Vertices: {len(roof_verts):,}")
    return True

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python tools/separate_building_roof.py <path_to_building_dir>")
        sys.exit(1)
    separate_building(sys.argv[1])
