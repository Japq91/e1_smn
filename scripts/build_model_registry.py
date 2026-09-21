#!/usr/bin/env python3
"""Arma informe/model_registry.csv: un identificador numerico estable
(M001..M102, orden alfabetico) para cada uno de los 102 modelos que
'00b' inspecciona, mas la informacion de referencia que pidio el
usuario en un solo lugar -- institucion, realizacion (member_id),
resolucion horizontal, y un vector de 4 columnas (tiene_hist,
tiene_ssp245, tiene_ssp370, tiene_ssp585) con 1 solo cuando ese
experimento existe en ESGF en absoluto (no cuando ya se descargo).

Junta 3 fuentes que se generan en pasos distintos del pipeline:
  - informe/model_availability_priority.csv (00b): los 102 modelos y
    su disponibilidad real por experimento.
  - config/models_seed_cmip6.csv (00b): institucion y grilla elegida,
    pero SOLO para los modelos seleccionados como seed (los que tienen
    historical/hist-1950 + los 3 SSP bajo una misma grilla).
  - data/interim/models_catalog_status.csv (01/02b): el member_id
    (realizacion) que efectivamente se uso para buscar archivos, solo
    para los modelos que 01 llego a procesar.

Los modelos que no llegaron a ser seed (no calificaron con el criterio
actual) quedan con institucion/member_id/resolucion en blanco -- es
honesto: nunca se les asigno una grilla o miembro especifico, no hay
un valor "correcto" que inventar ahi.

Uso:
    python3 scripts/build_model_registry.py
"""
import csv
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
PRIORITY_CSV = BASE_DIR / "informe/model_availability_priority.csv"
SEED_CSV = BASE_DIR / "config/models_seed_cmip6.csv"
CATALOG_CSV = BASE_DIR / "data/interim/models_catalog_status.csv"
OUT_CSV = BASE_DIR / "informe/model_registry.csv"


def main() -> None:
    if not PRIORITY_CSV.exists():
        sys.exit(f"Falta {PRIORITY_CSV}. Se genera con run.sh (paso 00b).")

    with open(PRIORITY_CSV, newline="") as f:
        priority_rows = list(csv.DictReader(f))

    seed_info: dict[str, dict] = {}
    if SEED_CSV.exists():
        with open(SEED_CSV, newline="") as f:
            for row in csv.DictReader(f):
                seed_info[row["model"]] = row

    member_by_model: dict[str, str] = {}
    if CATALOG_CSV.exists():
        with open(CATALOG_CSV, newline="") as f:
            for row in csv.DictReader(f):
                member_by_model[row["model"]] = row.get("member_id", "")

    models_sorted = sorted(priority_rows, key=lambda r: r["model"])
    n = len(models_sorted)
    width = max(3, len(str(n)))

    registry_rows = []
    for i, row in enumerate(models_sorted, start=1):
        model = row["model"]
        seed = seed_info.get(model, {})
        registry_rows.append({
            "numero_modelo": f"M{i:0{width}d}",
            "model": model,
            "institution": seed.get("institution", ""),
            "member_id": member_by_model.get(model, ""),
            "resolution_km": seed.get("nominal_resolution_km", ""),
            "tiene_hist": row.get("tiene_hist", "0"),
            "tiene_ssp245": row.get("tiene_ssp245", "0"),
            "tiene_ssp370": row.get("tiene_ssp370", "0"),
            "tiene_ssp585": row.get("tiene_ssp585", "0"),
        })

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(registry_rows[0].keys()))
        w.writeheader()
        w.writerows(registry_rows)

    n_con_metadata = sum(1 for r in registry_rows if r["institution"])
    print(f"{OUT_CSV}: {n} modelos ({n_con_metadata} con institucion/grilla, "
          f"los que llegaron a ser seed -- ver config/models_seed_cmip6.csv)", file=sys.stderr)


if __name__ == "__main__":
    main()
