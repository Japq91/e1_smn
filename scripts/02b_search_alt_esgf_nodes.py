#!/usr/bin/env python3
"""Segunda opcion (1/2): busca los modelos faltantes en otros nodos
indice de la federacion ESGF, no solo el de LLNL usado por
01_query_esgf_catalog.py (paso 02b -- NO forma parte de
la secuencia automatica de run.sh; se corre a mano cuando
00c_check_paper_models.py reporta modelos citados en los papers que no
aparecieron en la busqueda principal).

ESGF es una federacion de nodos que replican (parcial o totalmente)
el mismo indice de datos; un modelo puede no aparecer en la busqueda
contra el nodo de LLNL por problemas de replicacion/conectividad
puntuales de ese nodo especifico, y sin embargo estar indexado en otro
nodo de la federacion. Este script repite la misma busqueda a nivel de
archivo que 01, pero contra una lista de nodos alternativos, y agrega
los modelos que SI encuentra a los mismos archivos que ya usa el resto
del pipeline (data/interim/models_catalog_status.csv y
esgf_file_urls.json), para que 02_download_cmip6_chunks.sh los
descargue en su proxima corrida sin necesidad de cambiar nada mas.

AVISO: la federacion ESGF tuvo reorganizaciones/caidas de nodos
importantes en 2023-2024; no todos los nodos de esta lista estaran
necesariamente activos al momento de correr esto -- el script continua
con el siguiente nodo si uno falla o da timeout.

NOTA (correccion): igual que en 01_query_esgf_catalog.py, la busqueda
no filtraba por 'variant_label' (miembro del ensamble), lo que permitia
traer varias realizaciones (r1i1p1f1, r2i1p1f1, ...) del mismo modelo
como si fueran un solo archivo continuo. Ahora se determina, por nodo y
modelo, el variant_label comun a los tres experimentos (prefiriendo
r1i1p1f1) antes de buscar los archivos.

Uso:
    python3 02b_search_alt_esgf_nodes.py \
        ../config/models_missing_from_esgf.csv \
        data/interim/models_catalog_status.csv \
        data/interim/esgf_file_urls.json
"""
import csv
import json
import re
import sys
from pathlib import Path

import requests

# Nodos indice de busqueda de la federacion ESGF (ademas del de LLNL,
# ya intentado por 01_query_esgf_catalog.py). Verificar cuales estan
# activos al momento de usar este script -- la federacion cambia con
# el tiempo.
ALT_ESGF_SEARCH_URLS = [
    "https://esgf.ceda.ac.uk/esg-search/search",
    "https://esgf-data.dkrz.de/esg-search/search",
    "https://esgf-node.ipsl.upmc.fr/esg-search/search",
    "https://esg-dn1.nsc.liu.se/esg-search/search",
    "https://esgf.nci.org.au/esg-search/search",
]
EXPERIMENTS = ["historical", "ssp245", "ssp585"]
VARIABLE, TABLE = "tos", "Omon"
TIMEOUT = 30


def _realization_number(member: str) -> int:
    m = re.match(r"r(\d+)", member)
    return int(m.group(1)) if m else 10**9


def find_common_member(base_url: str, model: str) -> str | None:
    """Devuelve el variant_label disponible en los tres experimentos
    para este modelo en este nodo especifico (prefiere 'r1i1p1f1')."""
    members_per_exp: dict[str, set[str]] = {}
    for exp in EXPERIMENTS:
        params = {
            "project": "CMIP6", "source_id": model, "experiment_id": exp,
            "variable_id": VARIABLE, "table_id": TABLE, "type": "File",
            "format": "application/solr+json", "limit": 0,
            "facets": "variant_label",
        }
        r = requests.get(base_url, params=params, timeout=TIMEOUT)
        r.raise_for_status()
        facet_field = r.json()["facet_counts"]["facet_fields"].get("variant_label", [])
        members_per_exp[exp] = set(facet_field[0::2])

    common = set.intersection(*members_per_exp.values()) if members_per_exp else set()
    if not common:
        return None
    if "r1i1p1f1" in common:
        return "r1i1p1f1"
    return sorted(common, key=_realization_number)[0]


def esgf_file_search(base_url: str, model: str, experiment: str, member: str) -> list[dict]:
    params = {
        "project": "CMIP6", "source_id": model, "experiment_id": experiment,
        "variable_id": VARIABLE, "table_id": TABLE, "type": "File",
        "variant_label": member,
        "format": "application/solr+json", "limit": 200,
    }
    r = requests.get(base_url, params=params, timeout=TIMEOUT)
    r.raise_for_status()
    docs = r.json()["response"]["docs"]

    by_filename: dict[str, list[str]] = {}
    for d in docs:
        filename = d.get("title")
        if not filename:
            continue
        for u in d.get("url", []):
            url, mime, service = (u.split("|") + ["", "", ""])[:3]
            if service == "HTTPServer":
                by_filename.setdefault(filename, [])
                if url not in by_filename[filename]:
                    by_filename[filename].append(url)

    return [{"filename": fn, "urls": urls} for fn, urls in sorted(by_filename.items())]


def search_model_all_nodes(model: str) -> dict[str, list[dict]] | None:
    """Prueba cada nodo alternativo hasta encontrar los 3 experimentos
    completos para el modelo. Devuelve None si ninguno lo logra."""
    for base_url in ALT_ESGF_SEARCH_URLS:
        try:
            member = find_common_member(base_url, model)
            if member is None:
                print(f"  {base_url}: sin variant_label comun a los 3 experimentos", file=sys.stderr)
                continue
            found = {exp: esgf_file_search(base_url, model, exp, member) for exp in EXPERIMENTS}
        except (requests.RequestException, ValueError) as e:
            print(f"  {base_url}: fallo ({e})", file=sys.stderr)
            continue

        if all(found[exp] for exp in EXPERIMENTS):
            print(f"  encontrado completo en {base_url} (miembro {member})", file=sys.stderr)
            return found
        else:
            n_files = {exp: len(found[exp]) for exp in EXPERIMENTS}
            print(f"  {base_url}: incompleto {n_files}", file=sys.stderr)
    return None


def main(missing_csv: str, catalog_csv: str, files_json: str) -> None:
    with open(missing_csv, newline="") as f:
        missing_models = [row["model"] for row in csv.DictReader(f)]

    # Cargar catalogo existente (si ya corrio 01 antes) para no perderlo.
    catalog_rows = []
    if Path(catalog_csv).exists():
        with open(catalog_csv, newline="") as f:
            catalog_rows = list(csv.DictReader(f))
    already = {r["model"] for r in catalog_rows}

    file_catalog: dict[str, dict] = {}
    if Path(files_json).exists():
        file_catalog = json.loads(Path(files_json).read_text())

    resolved, still_missing = [], []
    for model in missing_models:
        if model in already:
            print(f"{model}: ya esta en el catalogo, se omite", file=sys.stderr)
            continue

        print(f"Buscando {model} en nodos alternativos ...", file=sys.stderr)
        found = search_model_all_nodes(model)
        if found is None:
            still_missing.append(model)
            continue

        resolved.append(model)
        catalog_rows.append({
            "model": model, "grid_label": "", "complete": "True",
            "historical": "True", "ssp245": "True", "ssp585": "True",
        })
        file_catalog[model] = found

    if resolved:
        with open(catalog_csv, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["model", "grid_label", "complete", *EXPERIMENTS])
            writer.writeheader()
            writer.writerows(catalog_rows)

        with open(files_json, "w") as f:
            json.dump(file_catalog, f, indent=2)

    print(f"\nResueltos via nodo alternativo: {len(resolved)} -> {resolved}", file=sys.stderr)
    print(f"Siguen sin encontrarse: {len(still_missing)} -> {still_missing}", file=sys.stderr)
    print("(intentar con 02c_download_copernicus_cds.py para los que siguen sin encontrarse)", file=sys.stderr)


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit("uso: 02b_search_alt_esgf_nodes.py <missing.csv> <models_catalog_status.csv> <esgf_file_urls.json>")
    main(sys.argv[1], sys.argv[2], sys.argv[3])
