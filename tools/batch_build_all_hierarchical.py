#!/usr/bin/env python3
"""
tools/batch_build_all_hierarchical.py

High-performance multiprocessing runner to apply the Hierarchical Wall & Block (Parent/Child)
architecture to buildings across all UO maps:
- Map 0 (Felucca): 2,631 buildings
- Map 1 (Trammel): 2,605 buildings
- Map 2 (Ilshenar): 190 buildings
- Map 3 (Malas): 105 buildings
- Map 4 (Tokuno): 45 buildings
- Map 5 (Ter Mur): 188 buildings

Usage:
  python3 tools/batch_build_all_hierarchical.py --city map0_felucca/britain
  python3 tools/batch_build_all_hierarchical.py --map map0_felucca
  python3 tools/batch_build_all_hierarchical.py --all
"""

import os
import sys
import time
import shutil
import argparse
import subprocess
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed

ROOT_DIR = Path("/home/mnunes/uo3d-community-buildings").resolve()

WORKER_SCRIPT = """
import sys
import time
from pathlib import Path
sys.path.append("/home/mnunes/uo3d-community-buildings/tools")
import build_hierarchical_building as builder

def process_batch(file_list_path):
    with open(file_list_path, 'r', encoding='utf-8') as f:
        paths = [line.strip() for line in f if line.strip()]

    total = len(paths)
    success = 0
    failed = 0
    for idx, p in enumerate(paths, 1):
        try:
            ok = builder.build_hierarchical(p)
            if ok:
                success += 1
            else:
                failed += 1
            if idx % 10 == 0 or idx == total:
                print(f"[PROGRESS] {idx}/{total} ({idx/total*100:.1f}%) in worker {Path(file_list_path).stem} - Last: {Path(p).name}", flush=True)
        except Exception as e:
            failed += 1
            print(f"[ERROR] {p}: {e}", flush=True)

    print(f"[WORKER DONE] Success: {success}, Failed: {failed} out of {total}")

if __name__ == '__main__':
    args = sys.argv
    if '--' in args:
        idx = args.index('--')
        if idx + 1 < len(args):
            process_batch(args[idx + 1])
"""

def get_building_folders(target_type, target_val):
    if target_type == "all":
        return sorted([p.parent for p in ROOT_DIR.glob("map*/*/*/info.json")])
    elif target_type == "map":
        return sorted([p.parent for p in (ROOT_DIR / target_val).glob("*/*/info.json")])
    elif target_type == "city":
        city_dir = (ROOT_DIR / target_val).resolve()
        return sorted([p.parent for p in city_dir.glob("*/info.json")])
    return []

def run_worker_process(batch_file):
    worker_py = ROOT_DIR / "tools" / "_worker_runner.py"
    log_file = batch_file.with_suffix(".log")
    cmd = [
        "blender", "-b", "-noaudio",
        "--python", str(worker_py),
        "--", str(batch_file)
    ]
    with open(log_file, "w", encoding="utf-8") as out_f:
        res = subprocess.run(cmd, stdout=out_f, stderr=subprocess.STDOUT, text=True)
    return res.returncode, str(log_file)

def main():
    parser = argparse.ArgumentParser(description="Batch build hierarchical buildings across maps.")
    parser.add_argument("--all", action="store_true", help="Process all maps (5764 buildings)")
    parser.add_argument("--map", type=str, default=None, help="Process specific map (e.g. map0_felucca)")
    parser.add_argument("--city", type=str, default=None, help="Process specific city (e.g. map0_felucca/britain)")
    parser.add_argument("--workers", type=int, default=12, help="Number of parallel Blender workers (default: 12)")
    args = parser.parse_args()

    if args.all:
        target_type, target_val = "all", None
    elif args.map:
        target_type, target_val = "map", args.map
    elif args.city:
        target_type, target_val = "city", args.city
    else:
        # Default to Britain for immediate test verification
        target_type, target_val = "city", "map0_felucca/britain"

    buildings = get_building_folders(target_type, target_val)
    total_buildings = len(buildings)
    print(f"=== BATCH HIERARCHICAL PROCESSOR ===")
    print(f"Target: {target_type} ({target_val or 'all'}) | Total buildings: {total_buildings} | Workers: {args.workers}")

    if total_buildings == 0:
        print("[X] No buildings found.")
        return

    # Write worker script
    worker_py = ROOT_DIR / "tools" / "_worker_runner.py"
    with open(worker_py, "w", encoding="utf-8") as f:
        f.write(WORKER_SCRIPT)

    # Chunk buildings for workers
    tmp_dir = ROOT_DIR / "tools" / "_batches"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    num_workers = min(args.workers, total_buildings)
    chunks = [[] for _ in range(num_workers)]
    for idx, bpath in enumerate(buildings):
        chunks[idx % num_workers].append(str(bpath))

    batch_files = []
    for widx, chunk in enumerate(chunks):
        if not chunk: continue
        bf = tmp_dir / f"batch_{widx:02d}.txt"
        with open(bf, "w", encoding="utf-8") as f:
            for item in chunk:
                f.write(f"{item}\n")
        batch_files.append(bf)

    print(f"[+] Prepared {len(batch_files)} worker chunks. Starting parallel execution...")
    t0 = time.time()

    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        futures = {executor.submit(run_worker_process, bf): bf for bf in batch_files}
        completed = 0
        for fut in as_completed(futures):
            completed += 1
            bf = futures[fut]
            code, out = fut.result()
            print(f"[{completed}/{len(batch_files)}] Worker for {bf.name} finished (exit code {code})")

    elapsed = time.time() - t0
    print(f"\n=== COMPLETED IN {elapsed:.1f}s ({elapsed/60.0:.1f} minutes) ===")
    print(f"Processed {total_buildings} buildings.")

    # Clean temporary batches
    shutil.rmtree(tmp_dir, ignore_errors=True)
    if worker_py.exists():
        worker_py.unlink()

if __name__ == "__main__":
    main()
