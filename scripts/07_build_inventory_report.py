#!/usr/bin/env python3
"""Inventario final de modelos (paso 07).

Combina el resultado del catalogo (01, via el CSV de control de
calidad de 08) y metadatos de grilla obtenidos directamente con CDO,
en la tabla resumen final de modelos seleccionados.
"""
import csv
import subprocess
import sys
from pathlib import Path


def griddes_resolution(path: str) -> str:
    out = subprocess.run(["cdo", "-s", "griddes", path], capture_output=True, text=True).stdout
    xsize = next((l.split()[-1] for l in out.splitlines() if "xsize" in l), "?")
    ysize = next((l.split()[-1] for l in out.splitlines() if "ysize" in l), "?")
    return f"{xsize}x{ysize}"


def main(qc_csv: str, data_dir: str, out_csv: str) -> None:
    with open(qc_csv, newline="") as f:
        qc_rows = list(csv.DictReader(f))

    if not qc_rows:
        sys.exit(f"09_build_inventory_report.py: {qc_csv} esta vacio")

    by_model: dict[str, dict] = {}
    for row in qc_rows:
        m = row.get("model", "?")
        agg = by_model.setdefault(m, {"experiments_pass": 0, "experiments_total": 0})
        agg["experiments_total"] += 1
        if row.get("status") == "PASS":
            agg["experiments_pass"] += 1

    final_rows = []
    for model, agg in sorted(by_model.items()):
        sample = next(Path(data_dir).glob(f"tos_{model}_historical.nc"), None)
        resolution = griddes_resolution(str(sample)) if sample else "?"
        final_rows.append({
            "model": model,
            "resolution": resolution,
            "experiments_pass": agg["experiments_pass"],
            "experiments_total": agg["experiments_total"],
            "selected": agg["experiments_pass"] == agg["experiments_total"],
        })

    Path(out_csv).parent.mkdir(parents=True, exist_ok=True)
    with open(out_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(final_rows[0].keys()))
        writer.writeheader()
        writer.writerows(final_rows)

    n_selected = sum(1 for r in final_rows if r["selected"])
    print(f"Inventario final escrito en {out_csv} ({n_selected}/{len(final_rows)} modelos seleccionados)", file=sys.stderr)


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit("uso: 09_build_inventory_report.py <qc.csv> <data_dir> <out_final.csv>")
    main(sys.argv[1], sys.argv[2], sys.argv[3])
