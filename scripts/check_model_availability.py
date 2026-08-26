#!/usr/bin/env python3
"""Verifica en vivo, contra ESGF, que experimentos (historical, ssp245,
ssp585) tiene publicados cada modelo para la variable tos/Omon (paso de
diagnostico -- NO forma parte de la secuencia automatica de run.sh).

Se escribio porque data/interim/models_catalog_status.csv qued con
inconsistencias (modelos marcados sin ssp245 NI ssp585 que en realidad
si tienen uno de los dos) -- en vez de depurar ese CSV, este script
reconsulta el estado real directamente en ESGF con una sola peticion
por modelo (facetas de experiment_id), evitando heredar el error.

Uso:
    python3 check_model_availability.py [models.txt] [out_prefix]

Si no se pasa 'models.txt', toma la lista de modelos de
data/interim/models_catalog_status.csv (solo la columna 'model' --sus
nombres son confiables, el bug estaba en las columnas de experimento,
no en la lista de modelos-- union con config/models_missing_from_esgf.csv).

Escribe:
    <out_prefix>.csv  -- una fila por modelo, columnas historical/ssp245/ssp585 (True/False/ERROR)
    <out_prefix>.md   -- reporte legible, agrupado por categoria
"""
import csv
import sys
import time
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parent.parent
ESGF_SEARCH_URL = "https://esgf-node.llnl.gov/esg-search/search"
VARIABLE, TABLE = "tos", "Omon"
EXPERIMENTS = ("historical", "ssp245", "ssp585")
TIMEOUT = 30
MAX_RETRIES = 2


def default_model_list() -> list[str]:
    models = set()
    catalog = BASE_DIR / "data/interim/models_catalog_status.csv"
    if catalog.exists():
        with open(catalog, newline="") as f:
            models.update(r["model"] for r in csv.DictReader(f))
    missing = BASE_DIR / "config/models_missing_from_esgf.csv"
    if missing.exists():
        with open(missing, newline="") as f:
            models.update(r["model"] for r in csv.DictReader(f))
    return sorted(models)


def query_experiments(model: str) -> set[str] | None:
    """Devuelve el conjunto de experiment_id con tos/Omon publicado para
    este modelo (cualquier miembro/grilla), o None si la consulta fallo
    tras reintentar."""
    params = {
        "project": "CMIP6", "source_id": model,
        "variable_id": VARIABLE, "table_id": TABLE,
        "facets": "experiment_id", "limit": 0,
        "format": "application/solr+json",
    }
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.get(ESGF_SEARCH_URL, params=params, timeout=TIMEOUT)
            r.raise_for_status()
            facet = r.json()["facet_counts"]["facet_fields"].get("experiment_id", [])
            # formato solr: [nombre1, conteo1, nombre2, conteo2, ...]
            names, counts = facet[0::2], facet[1::2]
            return {n for n, c in zip(names, counts) if int(c) > 0}
        except (requests.RequestException, ValueError, KeyError) as e:
            print(f"  {model}: intento {attempt}/{MAX_RETRIES} fallo ({e})", file=sys.stderr)
            time.sleep(2)
    return None


def classify(status: dict[str, bool]) -> str:
    h, s2, s5 = status["historical"], status["ssp245"], status["ssp585"]
    if h and s2 and s5:
        return "completo"
    if not h and not s2 and not s5:
        return "sin_tos"
    if h and not s2 and not s5:
        return "solo_historical"
    if not h:
        return "sin_historical_pero_con_algun_ssp"
    if h and s2 and not s5:
        return "falta_ssp585"
    if h and not s2 and s5:
        return "falta_ssp245"
    return "otro"


CATEGORY_LABELS = {
    "completo": "Completos (historical + ssp245 + ssp585, con tos/Omon)",
    "falta_ssp585": "Tienen historical + ssp245, les falta ssp585",
    "falta_ssp245": "Tienen historical + ssp585, les falta ssp245",
    "solo_historical": "Solo tienen historical (les faltan ambos SSP)",
    "sin_historical_pero_con_algun_ssp": "Tienen algun SSP pero no historical",
    "sin_tos": "Sin tos/Omon publicado en ningun experimento (no encontrado)",
    "otro": "Otros casos",
}
CATEGORY_ORDER = ["completo", "falta_ssp585", "falta_ssp245", "solo_historical",
                  "sin_historical_pero_con_algun_ssp", "sin_tos", "otro"]


def main(models: list[str], out_prefix: Path) -> None:
    rows = []
    for i, model in enumerate(models, start=1):
        print(f"[{i}/{len(models)}] {model} ...", file=sys.stderr)
        found = query_experiments(model)
        if found is None:
            rows.append({"model": model, "historical": "ERROR", "ssp245": "ERROR",
                         "ssp585": "ERROR", "categoria": "error_consulta"})
            continue
        status = {exp: (exp in found) for exp in EXPERIMENTS}
        cat = classify(status)
        rows.append({
            "model": model,
            "historical": status["historical"], "ssp245": status["ssp245"],
            "ssp585": status["ssp585"], "categoria": cat,
        })

    out_prefix.parent.mkdir(parents=True, exist_ok=True)

    csv_path = out_prefix.with_suffix(".csv")
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["model", "historical", "ssp245", "ssp585", "categoria"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nCSV escrito en {csv_path}", file=sys.stderr)

    md_path = out_prefix.with_suffix(".md")
    by_cat: dict[str, list[dict]] = {}
    for r in rows:
        by_cat.setdefault(r["categoria"], []).append(r)

    lines = ["# Disponibilidad de tos/Omon por modelo CMIP6 (verificado en vivo contra ESGF)", ""]
    lines.append(f"Total de modelos verificados: {len(rows)}")
    lines.append("")
    for cat in CATEGORY_ORDER + sorted(set(by_cat) - set(CATEGORY_ORDER) - {"error_consulta"}):
        items = by_cat.get(cat)
        if not items:
            continue
        label = CATEGORY_LABELS.get(cat, cat)
        lines.append(f"## {label} ({len(items)})")
        lines.append("")
        for r in sorted(items, key=lambda x: x["model"]):
            lines.append(f"- {r['model']}")
        lines.append("")
    if by_cat.get("error_consulta"):
        lines.append(f"## Error de consulta -- reintentar manualmente ({len(by_cat['error_consulta'])})")
        lines.append("")
        for r in sorted(by_cat["error_consulta"], key=lambda x: x["model"]):
            lines.append(f"- {r['model']}")
        lines.append("")

    md_path.write_text("\n".join(lines))
    print(f"Reporte legible escrito en {md_path}", file=sys.stderr)


if __name__ == "__main__":
    models_file = sys.argv[1] if len(sys.argv) > 1 else None
    out_prefix = Path(sys.argv[2]) if len(sys.argv) > 2 else BASE_DIR / "informe/model_availability_report"

    if models_file:
        with open(models_file) as f:
            model_list = [line.strip() for line in f if line.strip()]
    else:
        model_list = default_model_list()

    print(f"Verificando {len(model_list)} modelos ...", file=sys.stderr)
    main(model_list, out_prefix)
