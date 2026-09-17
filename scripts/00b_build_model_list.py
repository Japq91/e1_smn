#!/usr/bin/env python3
"""Construye la lista de modelos CMIP6 a usar (paso 00b).

A diferencia de la version anterior (que partia de una lista semilla
curada, la de Bruno Ramirez 2023), este script inspecciona TODOS los
modelos CMIP6 publicados en ESGF y los filtra segun el criterio
acordado con el proyecto:

  1. Deben tener la variable 'tos' (Omon) disponible.
  2. Deben tener 'historical' publicado -- requisito duro, es la base
     para el calculo de TOE. Se busca primero en el nodo principal de
     ESGF (LLNL); si no aparece ahi, se prueba en los nodos
     alternativos de la federacion (mismo fallback que
     02b_search_alt_esgf_nodes.py) antes de descartar el modelo --
     asi no se pierde un modelo solo porque LLNL tiene ese indice
     incompleto.
  3. Deben tener ademas TODOS los escenarios SSP configurados en
     config/periods.yaml (sin fallback a nodos alternativos para
     estos -- ver Convenciones del README) para quedar SELECCIONADO
     en config/models_seed_cmip6.csv, que es lo que alimenta la
     descarga real (01/02).
  4. De las variantes de grilla (grid_label) que publique cada modelo,
     se elige la MAS GRUESA disponible (mayor 'nominal_resolution' en
     km), ya que de todos modos el paso 04 regrilla todo a la
     resolucion del dato observado de referencia (ERSSTv5, ~2 grados)
     -- no hace falta descargar en alta resolucion.

Ademas de config/models_seed_cmip6.csv (solo los modelos seleccionados:
model, institution, grid_label, nominal_resolution_km), escribe
informe/model_availability_report.csv/.md -- disponibilidad real por
experimento de TODOS los modelos inspeccionados (no solo los
seleccionados), reutilizando classify()/category_label()/write_report()
de check_model_availability.py. No hace falta correr ese script aparte
para tener ese reporte; queda como herramienta manual de segunda
opinion (ver su docstring).

Este script reemplaza a config/models_seed_bruno2023.csv como fuente
de la lista de modelos; ese archivo se conserva sin usar, como
referencia historica (no se elimina).
"""
import csv
import re
import sys
from pathlib import Path

import requests

import pipeline_config
from check_model_availability import classify, write_report

BASE_DIR = Path(__file__).resolve().parent.parent
ESGF_SEARCH_URL = "https://esgf-node.llnl.gov/esg-search/search"
VARIABLE, TABLE = "tos", "Omon"
REQUIRED_EXPERIMENTS = set(pipeline_config.experiments())
DEFAULT_REPORT_PREFIX = BASE_DIR / "informe/model_availability_report"


def _first(doc: dict, field: str):
    """Los documentos de ESGF devuelven casi todos los campos como listas."""
    val = doc.get(field)
    if isinstance(val, list):
        return val[0] if val else None
    return val


def list_all_models() -> list[str]:
    """Enumera, via facetas de ESGF, todos los source_id con tos/Omon publicado
    (solo nodo principal -- es el universo base de modelos a inspeccionar)."""
    params = {
        "project": "CMIP6", "variable_id": VARIABLE, "table_id": TABLE,
        "facets": "source_id", "limit": 0,
        "format": "application/solr+json",
    }
    r = pipeline_config.esgf_get(ESGF_SEARCH_URL, params, timeout=60)
    facet = r.json()["facet_counts"]["facet_fields"]["source_id"]
    # el formato solr de facetas es [nombre1, conteo1, nombre2, conteo2, ...]
    return facet[0::2]


def model_datasets(model: str, base_url: str = ESGF_SEARCH_URL) -> list[dict]:
    """Todos los datasets (cualquier experimento/grilla) de tos/Omon para un
    modelo, contra el nodo indicado (por defecto, el principal)."""
    params = {
        "project": "CMIP6", "source_id": model, "variable_id": VARIABLE, "table_id": TABLE,
        "type": "Dataset", "format": "application/solr+json", "limit": 500,
    }
    r = pipeline_config.esgf_get(base_url, params, timeout=60)
    return r.json()["response"]["docs"]


def experiments_present(docs: list[dict]) -> set[str]:
    """experiment_id de cualquier dataset de la lista, sin importar la
    grilla -- para el reporte de disponibilidad (a diferencia de
    pick_coarsest_grid, que exige que TODOS esten bajo una misma grilla)."""
    return {_first(d, "experiment_id") for d in docs if _first(d, "experiment_id")}


def fetch_model_docs(model: str) -> tuple[list[dict], str]:
    """Devuelve (docs, fuente) para un modelo. 'historical' es requisito
    duro: se busca primero en LLNL; si no aparece ahi, se prueba en los
    nodos alternativos de la federacion (uno por uno, el primero que lo
    tenga) y se agregan esos docs a los de LLNL. Si ningun nodo tiene
    'historical', se devuelven los docs de LLNL tal cual (pueden tener
    igual algun SSP, para el reporte de disponibilidad) con
    fuente='sin_historical'."""
    docs = model_datasets(model)
    if "historical" in experiments_present(docs):
        return docs, "esgf_principal"

    for alt_url in pipeline_config.ALT_ESGF_SEARCH_URLS:
        try:
            alt_docs = model_datasets(model, base_url=alt_url)
        except requests.RequestException:
            continue
        if "historical" in experiments_present(alt_docs):
            return docs + alt_docs, "esgf_alt_node"

    return docs, "sin_historical"


def parse_resolution_km(res_str: str):
    """La 'nominal_resolution' de CMIP6 usa bins fijos en km (p.ej. '100 km');
    se extrae el primer numero como proxy de resolucion (mayor = mas grueso)."""
    if not res_str:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)", res_str)
    return float(m.group(1)) if m else None


def pick_coarsest_grid(docs: list[dict]) -> dict | None:
    """Agrupa los datasets por grid_label, se queda solo con las grillas que
    cubren TODOS los experimentos requeridos (historical + escenarios SSP
    de config/periods.yaml) bajo una misma grilla, y elige la de mayor
    resolucion_km (la mas gruesa)."""
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


def main(out_csv: str, report_prefix: Path = DEFAULT_REPORT_PREFIX) -> None:
    models = list_all_models()
    print(f"Modelos CMIP6 con tos/Omon publicado: {len(models)}", file=sys.stderr)

    seed_rows = []
    avail_rows = []
    for i, model in enumerate(sorted(models), start=1):
        docs, fuente_hist = fetch_model_docs(model)
        present = experiments_present(docs)
        status = {exp: (exp in present) for exp in REQUIRED_EXPERIMENTS}
        cat = classify(status)
        avail_rows.append({"model": model, **status, "categoria": cat})

        choice = pick_coarsest_grid(docs) if status["historical"] else None
        detalle = f" (categoria={cat}" + (f", historical via {fuente_hist}" if fuente_hist == "esgf_alt_node" else "") + ")"
        print(f"[{i}/{len(models)}] {model}: {'seleccionado' if choice else 'descartado'}{detalle}"
              + (f" -> grid={choice['grid_label']} ({choice['resolution_km']} km)" if choice else ""),
              file=sys.stderr)
        if not choice:
            continue
        seed_rows.append({
            "model": model,
            "institution": choice["institution"] or "?",
            "grid_label": choice["grid_label"],
            "nominal_resolution_km": choice["resolution_km"] if choice["resolution_km"] is not None else "",
        })

    if not seed_rows:
        sys.exit("00b_build_model_list.py: ningun modelo cumplio el criterio de seleccion")

    Path(out_csv).parent.mkdir(parents=True, exist_ok=True)
    with open(out_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["model", "institution", "grid_label", "nominal_resolution_km"])
        writer.writeheader()
        writer.writerows(seed_rows)
    print(f"\n{len(seed_rows)}/{len(models)} modelos seleccionados. Lista escrita en {out_csv}", file=sys.stderr)

    write_report(
        avail_rows, report_prefix,
        titulo="Disponibilidad de tos/Omon por modelo CMIP6 (paso 00b: LLNL, "
               "con nodos alternativos como respaldo solo para 'historical')",
    )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("uso: 00b_build_model_list.py <out_seed.csv>")
    main(sys.argv[1])
