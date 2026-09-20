#!/usr/bin/env python3
"""Verifica en vivo, contra ESGF, que experimentos (historical + los
escenarios SSP de config/periods.yaml) tiene publicados cada modelo
para la variable tos/Omon.

NO forma parte de la secuencia automatica de run.sh: 00b_build_model_list.py
ya genera informe/model_availability_report.csv/.md automaticamente en
cada corrida (reutilizando classify()/category_label()/write_report()
de este archivo, ver mas abajo), a partir de los mismos datos que
consulta para armar la lista de modelos -- sin peticiones adicionales.
Este script sirve como segunda opinion manual e independiente (consulta
ESGF por una via distinta, facetas de experiment_id en vez de listado
de datasets), util para verificar un modelo puntual o si se sospecha
que 00b esta mal.

Idempotente: si informe/model_availability_report.csv ya existe (por
ejemplo, el que genera 00b), no se vuelve a consultar ESGF. Para forzar
una nueva verificacion, borrar ese CSV a mano.

Uso:
    python3 check_model_availability.py [models.txt] [out_prefix]

Si no se pasa 'models.txt', toma la lista de modelos de
data/interim/models_catalog_status.csv (solo la columna 'model' --sus
nombres son confiables, el bug estaba en las columnas de experimento,
no en la lista de modelos-- union con config/models_missing_from_esgf.csv).

Escribe:
    <out_prefix>.csv  -- una fila por modelo, columnas historical + un SSP
                          por columna (True/False/ERROR)
    <out_prefix>.md   -- reporte legible, agrupado por categoria
"""
import csv
import sys
from pathlib import Path

import requests

import pipeline_config

BASE_DIR = Path(__file__).resolve().parent.parent
ESGF_SEARCH_URL = "https://esgf-node.llnl.gov/esg-search/search"
VARIABLE, TABLE = "tos", "Omon"
EXPERIMENTS = tuple(pipeline_config.experiments())
SCENARIOS = tuple(pipeline_config.scenarios())
TIMEOUT = 30


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
    (pipeline_config.esgf_get ya reintenta ante 429/5xx/fallos de red)."""
    params = {
        "project": "CMIP6", "source_id": model,
        "variable_id": VARIABLE, "table_id": TABLE,
        "facets": "experiment_id", "limit": 0,
        "format": "application/solr+json",
    }
    try:
        r = pipeline_config.esgf_get(ESGF_SEARCH_URL, params, timeout=TIMEOUT)
        facet = r.json()["facet_counts"]["facet_fields"].get("experiment_id", [])
        # formato solr: [nombre1, conteo1, nombre2, conteo2, ...]
        names, counts = facet[0::2], facet[1::2]
        return {n for n, c in zip(names, counts) if int(c) > 0}
    except (requests.RequestException, ValueError, KeyError) as e:
        print(f"  {model}: fallo tras reintentar ({e})", file=sys.stderr)
        return None


def classify(status: dict[str, bool]) -> str:
    h = status["historical"]
    missing = [s for s in SCENARIOS if not status[s]]
    any_ssp = any(status[s] for s in SCENARIOS)

    if h and not missing:
        return "completo"
    if not h and not any_ssp:
        return "sin_tos"
    if h and not any_ssp:
        return "solo_historical"
    if not h:
        return "sin_historical_pero_con_algun_ssp"
    return "falta_" + "_".join(missing)


def category_label(cat: str) -> str:
    if cat == "completo":
        return f"Completos (historical + {' + '.join(SCENARIOS)}, con tos/Omon)"
    if cat == "sin_tos":
        return ("Sin historical (ni hist-1950) ni ningun SSP -- pueden tener tos/Omon "
                "publicado igual, pero bajo otros experimentos (omip, PMIP, HighResMIP "
                "sin hist-1950, DCPP, etc.) que este pipeline no usa; ver columna de "
                "experimentos encontrados")
    if cat == "solo_historical":
        return "Solo tienen historical (o hist-1950) -- les faltan todos los SSP"
    if cat == "sin_historical_pero_con_algun_ssp":
        return "Tienen algun SSP pero no historical"
    if cat.startswith("falta_"):
        faltantes = cat[len("falta_"):].replace("_", ", ")
        return f"Tienen historical y el resto de los SSP, les falta: {faltantes}"
    if cat == "error_consulta":
        return "Error de consulta -- reintentar manualmente"
    return "Otros casos"


CATEGORY_ORDER = ["completo", "solo_historical",
                  "sin_historical_pero_con_algun_ssp", "sin_tos"]


def main(models: list[str], out_prefix: Path) -> None:
    rows = []
    for i, model in enumerate(models, start=1):
        print(f"[{i}/{len(models)}] {model} ...", file=sys.stderr)
        found = query_experiments(model)
        if found is None:
            rows.append({"model": model, **{exp: "ERROR" for exp in EXPERIMENTS},
                         "categoria": "error_consulta"})
            continue
        status = {exp: (exp in found) for exp in EXPERIMENTS}
        status["historical"] = bool(pipeline_config.has_historical(found))
        cat = classify(status)
        rows.append({"model": model, **status, "categoria": cat})
    write_report(rows, out_prefix, titulo="Disponibilidad de tos/Omon por modelo CMIP6 (verificado en vivo contra ESGF)")


def write_report(rows: list[dict], out_prefix: Path, titulo: str = "Disponibilidad de tos/Omon por modelo CMIP6") -> None:
    """Escribe <out_prefix>.csv/.md a partir de filas ya armadas
    (model + una columna bool por experimento + categoria). Separado de
    main() para que otros scripts (00b_build_model_list.py) puedan
    generar el mismo reporte reutilizando classify()/category_label()
    sin volver a consultar ESGF -- 00b ya tiene la info necesaria de su
    propio barrido."""
    out_prefix.parent.mkdir(parents=True, exist_ok=True)

    csv_path = out_prefix.with_suffix(".csv")
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["model", *EXPERIMENTS, "categoria"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nCSV escrito en {csv_path}", file=sys.stderr)

    md_path = out_prefix.with_suffix(".md")
    by_cat: dict[str, list[dict]] = {}
    for r in rows:
        by_cat.setdefault(r["categoria"], []).append(r)

    lines = [f"# {titulo}", ""]
    lines.append(f"Total de modelos verificados: {len(rows)}")
    lines.append("")
    for cat in CATEGORY_ORDER + sorted(set(by_cat) - set(CATEGORY_ORDER) - {"error_consulta"}):
        items = by_cat.get(cat)
        if not items:
            continue
        label = category_label(cat)
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

    # Idempotente, igual que el resto del pipeline (ver Convenciones del
    # README): si el reporte ya existe, no se vuelve a consultar ESGF
    # (son cientos de peticiones, una por modelo). Para regenerarlo hay
    # que borrar el CSV a mano -- asi la decision de recorrer todo el
    # universo de modelos de nuevo es explicita de quien ejecuta, no
    # algo que run.sh haga sin avisar en cada corrida.
    existing_csv = out_prefix.with_suffix(".csv")
    if existing_csv.exists():
        print(
            f"{existing_csv} ya existe, no se vuelve a consultar ESGF.\n"
            f"Para regenerarlo: borra ese archivo (y opcionalmente {out_prefix.with_suffix('.md')}) "
            "y volve a correr este script.",
            file=sys.stderr,
        )
        sys.exit(0)

    if models_file:
        with open(models_file) as f:
            model_list = [line.strip() for line in f if line.strip()]
    else:
        model_list = default_model_list()

    print(f"Verificando {len(model_list)} modelos ...", file=sys.stderr)
    main(model_list, out_prefix)
