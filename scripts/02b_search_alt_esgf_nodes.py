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
        config/models_missing_from_esgf.csv \
        data/interim/models_catalog_status.csv \
        data/interim/esgf_file_urls.json
"""
import csv
import json
import re
import sys
from pathlib import Path

import requests

import pipeline_config
from pipeline_config import ALT_ESGF_SEARCH_URLS

EXPERIMENTS = pipeline_config.experiments()
VARIABLE, TABLE = "tos", "Omon"
SEED_CSV = Path(__file__).resolve().parent.parent / "config" / "models_seed_cmip6.csv"
TIMEOUT = 30
# Menos reintentos que el default de esgf_get (6): acá hay 5 nodos para
# probar en cascada, asi que conviene fallar rapido en uno que esta
# realmente caido y pasar al siguiente, en vez de esperar minutos por
# cada experimento en un solo nodo problematico.
ALT_NODE_MAX_RETRIES = 2


def _realization_number(member: str) -> int:
    m = re.match(r"r(\d+)", member)
    return int(m.group(1)) if m else 10**9


def load_seed_grid_labels() -> dict[str, str]:
    """model -> grid_label ya decidido por 00b_build_model_list.py para
    los modelos que estan en la semilla. BUG real evitado: sin esto,
    esgf_file_search no filtraba por grilla, y un modelo publicado en
    mas de una grilla (ej. CESM2 historical: la misma ventana de fechas
    en 'gn' Y 'gr') traia AMBOS archivos como si fueran independientes
    -- 02_download_cmip6_chunks.sh los descargaba juntos y 04 los
    fusionaba con cdo mergetime como si fueran continuos, duplicando
    cada mes (verificado: CESM2 historical con 3960 meses en vez de los
    1980 esperados)."""
    if not SEED_CSV.exists():
        return {}
    with open(SEED_CSV, newline="") as f:
        return {row["model"]: row["grid_label"] for row in csv.DictReader(f) if row.get("grid_label")}


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
        r = pipeline_config.esgf_get(base_url, params, timeout=TIMEOUT, max_retries=ALT_NODE_MAX_RETRIES)
        facet_field = r.json()["facet_counts"]["facet_fields"].get("variant_label", [])
        members_per_exp[exp] = set(facet_field[0::2])

    common = set.intersection(*members_per_exp.values()) if members_per_exp else set()
    if not common:
        return None
    if "r1i1p1f1" in common:
        return "r1i1p1f1"
    return sorted(common, key=_realization_number)[0]


def esgf_file_search(base_url: str, model: str, experiment: str, member: str, grid_label: str | None) -> list[dict]:
    params = {
        "project": "CMIP6", "source_id": model, "experiment_id": experiment,
        "variable_id": VARIABLE, "table_id": TABLE, "type": "File",
        "variant_label": member,
        "format": "application/solr+json",
    }
    if grid_label:
        params["grid_label"] = grid_label
    docs = pipeline_config.esgf_get_all_docs(base_url, params, timeout=TIMEOUT, max_retries=ALT_NODE_MAX_RETRIES)
    year_start, year_end = pipeline_config.experiment_year_range(experiment)

    by_filename: dict[str, list[str]] = {}
    for d in docs:
        filename = d.get("title")
        if not filename:
            continue
        if not pipeline_config.file_overlaps_range(filename, year_start, year_end):
            continue
        for u in d.get("url", []):
            url, mime, service = (u.split("|") + ["", "", ""])[:3]
            if service == "HTTPServer":
                by_filename.setdefault(filename, [])
                if url not in by_filename[filename]:
                    by_filename[filename].append(url)

    # Igual que en 01_query_esgf_catalog.py: verifica un solo archivo por
    # experimento (el del empalme historical/SSP) en vez de uno por
    # chunk -- ver pipeline_config.verify_files_by_boundary_sample.
    verified = pipeline_config.verify_files_by_boundary_sample(by_filename, experiment, year_start, year_end)
    if by_filename and not verified:
        print(f"    {experiment}: el archivo de empalme no responde, se descarta todo el experimento",
              file=sys.stderr)

    return [{"filename": fn, "urls": urls} for fn, urls in sorted(verified.items())]


def search_model_all_nodes(model: str, grid_label: str | None) -> tuple[dict[str, list[dict]], str, str] | None:
    """Prueba TODOS los nodos alternativos (no se detiene en el primero
    que resuelve completo) y, de los que sí resuelven los 4 experimentos
    en la misma grilla, elige el de mejor miembro: prefiere r1i1p1f1: si
    ningun nodo lo tiene, el de menor numero de realizacion. Devuelve
    (archivos, member_id, nodo) o None si ningun nodo resuelve completo.

    BUG evitado: antes esto paraba en el PRIMER nodo que resolvia
    completo, sin importar que miembro trajera. Verificado con CESM2: el
    primer nodo de la lista (esgf.ceda.ac.uk) resuelve completo con
    r4i1p1f1, pero metagrid.esgf-west.org (mas atras en la lista) SI
    tiene r1i1p1f1 comun a los 4 experimentos -- con la logica de
    'primero que responda' nunca se llegaba a comparar y se elegia el
    miembro menos deseable aunque el mejor estuviera disponible."""
    if grid_label is None:
        print(f"  AVISO: {model} no esta en config/models_seed_cmip6.csv, no hay grid_label "
              f"conocido -- se busca sin filtrar por grilla (riesgo de mezclar grillas distintas "
              f"del mismo periodo, revisar a mano el resultado).", file=sys.stderr)

    candidates: list[tuple[dict[str, list[dict]], str, str]] = []
    for base_url in ALT_ESGF_SEARCH_URLS:
        try:
            member = find_common_member(base_url, model)
            if member is None:
                print(f"  {base_url}: sin variant_label comun a los 3 experimentos", file=sys.stderr)
                continue
            found = {exp: esgf_file_search(base_url, model, exp, member, grid_label) for exp in EXPERIMENTS}
        except (requests.RequestException, ValueError) as e:
            print(f"  {base_url}: fallo ({e})", file=sys.stderr)
            continue

        if all(found[exp] for exp in EXPERIMENTS):
            print(f"  {base_url}: completo (miembro {member})", file=sys.stderr)
            candidates.append((found, member, base_url))
        else:
            n_files = {exp: len(found[exp]) for exp in EXPERIMENTS}
            print(f"  {base_url}: incompleto {n_files}", file=sys.stderr)

    if not candidates:
        return None

    candidates.sort(key=lambda c: (c[1] != "r1i1p1f1", _realization_number(c[1])))
    found, member, base_url = candidates[0]
    print(f"  elegido: {base_url} (miembro {member}, de {len(candidates)} nodo(s) que resolvieron completo)",
          file=sys.stderr)
    return found, member, base_url


def main(missing_csv: str, catalog_csv: str, files_json: str) -> None:
    with open(missing_csv, newline="") as f:
        missing_models = [row["model"] for row in csv.DictReader(f)]

    # Cargar catalogo existente (si ya corrio 01 antes) para no perderlo.
    catalog_rows = []
    catalog_fieldnames = ["model", "grid_label", "complete", *EXPERIMENTS, "member_id", "fuente"]
    if Path(catalog_csv).exists():
        with open(catalog_csv, newline="") as f:
            reader = csv.DictReader(f)
            catalog_fieldnames = reader.fieldnames or catalog_fieldnames
            catalog_rows = list(reader)
    # 'no_encontrado' no cuenta como resuelto: son justamente los
    # candidatos a reintentar en nodos alternativos. Solo se omiten
    # modelos que ya tengan una fuente real (esgf_principal,
    # copernicus_parcial, esgf_alt_node de una corrida anterior).
    already = {r["model"] for r in catalog_rows if r.get("fuente") != "no_encontrado"}

    file_catalog: dict[str, dict] = {}
    if Path(files_json).exists():
        file_catalog = json.loads(Path(files_json).read_text())

    seed_grid_labels = load_seed_grid_labels()

    resolved, still_missing = [], []
    for model in missing_models:
        if model in already:
            print(f"{model}: ya esta en el catalogo, se omite", file=sys.stderr)
            continue

        print(f"Buscando {model} en nodos alternativos ...", file=sys.stderr)
        result = search_model_all_nodes(model, seed_grid_labels.get(model))
        if result is None:
            still_missing.append(model)
            continue
        found, member, node_url = result

        resolved.append(model)
        # reemplaza la fila 'no_encontrado' de este modelo (si existia),
        # no la duplica.
        catalog_rows = [r for r in catalog_rows if r["model"] != model]
        catalog_rows.append({
            "model": model, "grid_label": seed_grid_labels.get(model, ""), "complete": "True",
            **{exp: "True" for exp in EXPERIMENTS},
            "member_id": member, "fuente": "esgf_alt_node",
        })
        file_catalog[model] = found
        print(f"  nodo usado: {node_url}", file=sys.stderr)

    if resolved:
        with open(catalog_csv, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=catalog_fieldnames, extrasaction="ignore")
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
