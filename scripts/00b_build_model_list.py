#!/usr/bin/env python3
"""Construye la lista de modelos CMIP6 a usar (paso 00b).

A diferencia de la version anterior (que partia de una lista semilla
curada, la de Bruno Ramirez 2023), este script inspecciona TODOS los
modelos CMIP6 publicados en ESGF y los filtra segun el criterio
acordado con el proyecto:

  1. Deben tener la variable 'tos' (Omon) disponible.
  2. Deben tener datos en los tres experimentos requeridos:
     historical, ssp245, ssp585 (piControl ya no es requisito).
  3. De las variantes de grilla (grid_label) que publique cada modelo,
     se elige la MAS GRUESA disponible (mayor 'nominal_resolution' en
     km), ya que de todos modos el paso 06 regrilla todo a la
     resolucion del dato observado de referencia (ERSSTv5, ~2 grados)
     -- no hace falta descargar en alta resolucion.

Escribe config/models_seed_cmip6.csv, con una fila por modelo
seleccionado: model, institution, grid_label, nominal_resolution_km.

Este script reemplaza a config/models_seed_bruno2023.csv como fuente
de la lista de modelos; ese archivo se conserva sin usar, como
referencia historica (no se elimina).
"""
import csv
import re
import sys
from pathlib import Path

import requests

ESGF_SEARCH_URL = "https://esgf-node.llnl.gov/esg-search/search"
VARIABLE, TABLE = "tos", "Omon"
REQUIRED_EXPERIMENTS = {"historical", "ssp245", "ssp585"}


def _first(doc: dict, field: str):
    """Los documentos de ESGF devuelven casi todos los campos como listas."""
    val = doc.get(field)
    if isinstance(val, list):
        return val[0] if val else None
    return val


def list_all_models() -> list[str]:
    """Enumera, via facetas de ESGF, todos los source_id con tos/Omon publicado."""
    params = {
        "project": "CMIP6", "variable_id": VARIABLE, "table_id": TABLE,
        "facets": "source_id", "limit": 0,
        "format": "application/solr+json",
    }
    r = requests.get(ESGF_SEARCH_URL, params=params, timeout=60)
    r.raise_for_status()
    facet = r.json()["facet_counts"]["facet_fields"]["source_id"]
    # el formato solr de facetas es [nombre1, conteo1, nombre2, conteo2, ...]
    return facet[0::2]


def model_datasets(model: str) -> list[dict]:
    """Todos los datasets (cualquier experimento/grilla) de tos/Omon para un modelo."""
    params = {
        "project": "CMIP6", "source_id": model, "variable_id": VARIABLE, "table_id": TABLE,
        "type": "Dataset", "format": "application/solr+json", "limit": 500,
    }
    r = requests.get(ESGF_SEARCH_URL, params=params, timeout=60)
    r.raise_for_status()
    return r.json()["response"]["docs"]


def parse_resolution_km(res_str: str):
    """La 'nominal_resolution' de CMIP6 usa bins fijos en km (p.ej. '100 km');
    se extrae el primer numero como proxy de resolucion (mayor = mas grueso)."""
    if not res_str:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)", res_str)
    return float(m.group(1)) if m else None


def pick_coarsest_grid(docs: list[dict]) -> dict | None:
    """Agrupa los datasets por grid_label, se queda solo con las grillas que
    cubren los 3 experimentos requeridos, y elige la de mayor resolucion_km
    (la mas gruesa)."""
    by_grid: dict[str, dict] = {}
    institution = None

    for d in docs:
        grid = _first(d, "grid_label")
        exp = _first(d, "experiment_id")
        res = _first(d, "nominal_resolution")
        inst = _first(d, "institution_id")
        if inst:
            institution = inst
        if not grid or not exp:
            continue
        entry = by_grid.setdefault(grid, {"experiments": set(), "resolution_km": None})
        entry["experiments"].add(exp)
        res_km = parse_resolution_km(res)
        if res_km is not None:
            entry["resolution_km"] = res_km

    candidates = [
        (grid, info) for grid, info in by_grid.items()
        if REQUIRED_EXPERIMENTS.issubset(info["experiments"])
    ]
    if not candidates:
        return None

    # ordenar: primero las que SI tienen resolucion_km conocida (descendente,
    # mas grueso primero); las de resolucion desconocida quedan al final.
    candidates.sort(key=lambda gi: (gi[1]["resolution_km"] is None, -(gi[1]["resolution_km"] or 0)))
    grid_label, info = candidates[0]
    return {
        "grid_label": grid_label,
        "resolution_km": info["resolution_km"],
        "institution": institution,
    }


def main(out_csv: str) -> None:
    models = list_all_models()
    print(f"Modelos CMIP6 con tos/Omon publicado: {len(models)}", file=sys.stderr)

    rows = []
    for i, model in enumerate(sorted(models), start=1):
        docs = model_datasets(model)
        choice = pick_coarsest_grid(docs)
        status = "seleccionado" if choice else "descartado (falta historical/ssp245/ssp585)"
        print(f"[{i}/{len(models)}] {model}: {status}"
              + (f" -> grid={choice['grid_label']} ({choice['resolution_km']} km)" if choice else ""),
              file=sys.stderr)
        if not choice:
            continue
        rows.append({
            "model": model,
            "institution": choice["institution"] or "?",
            "grid_label": choice["grid_label"],
            "nominal_resolution_km": choice["resolution_km"] if choice["resolution_km"] is not None else "",
        })

    if not rows:
        sys.exit("00b_build_model_list.py: ningun modelo cumplio el criterio de seleccion")

    Path(out_csv).parent.mkdir(parents=True, exist_ok=True)
    with open(out_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["model", "institution", "grid_label", "nominal_resolution_km"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n{len(rows)}/{len(models)} modelos seleccionados. Lista escrita en {out_csv}", file=sys.stderr)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("uso: 00b_build_model_list.py <out_seed.csv>")
    main(sys.argv[1])
