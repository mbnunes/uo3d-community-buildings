#!/usr/bin/env python3
"""
download_building.py

Helper utility for 3D modelers to download or extract a single building package
without needing to clone the entire multi-gigabyte repository.

Usage:
  python download_building.py <building_path_or_keyword>
  
Example:
  python download_building.py britain/building_017_the_hammer_and_anvil_blacksmith
  python download_building.py west_bank
"""

import os
import sys
import shutil
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

def find_building(query):
    query = query.lower().strip()
    matches = []
    for info_file in ROOT_DIR.glob("**/info.json"):
        bdir = info_file.parent
        rel_path = str(bdir.relative_to(ROOT_DIR)).lower()
        if query in rel_path or query in bdir.name.lower():
            matches.append(bdir)
    return matches

def main():
    if len(sys.argv) < 2:
        print("Usage: python download_building.py <building_query>")
        print("Example: python download_building.py britain/blacksmith")
        sys.exit(1)

    query = sys.argv[1]
    matches = find_building(query)

    if not matches:
        print(f"[X] No building matching '{query}' found.")
        sys.exit(1)
    elif len(matches) > 1:
        print(f"[!] Multiple buildings match '{query}':")
        for m in matches[:10]:
            print(f"    - {m.relative_to(ROOT_DIR)}")
        if len(matches) > 10:
            print(f"    ... and {len(matches) - 10} more.")
        print("[!] Please provide a more specific name or path.")
        sys.exit(1)

    target = matches[0]
    out_dir = Path.cwd() / target.name
    if out_dir.exists():
        print(f"[!] Destination folder already exists: {out_dir}")
    else:
        shutil.copytree(target, out_dir)
        print(f"[+] Successfully extracted {target.name} to {out_dir}!")
        print(f"    You can now open 'model_base.glb' in Blender, inspect 'reference_2d.png', and start modeling!")

if __name__ == "__main__":
    main()
