#!/usr/bin/env python3
"""Consolida el catalogo de archivos a descargar (paso 01).
url: https://esgf-metagrid.cloud.dkrz.de/search
Lee config/models_seed_cmip6.csv (generado por 00b_build_model_list.py,
que ya inspecciono TODOS los modelos CMIP6 y eligio, por modelo, la
variante de grilla (grid_label) mas gruesa disponible que cubre los
experimentos requeridos (historical + escenarios SSP de config/periods.yaml). Para cada
modelo, busca en ESGF a nivel de
ARCHIVO los .nc de esa grilla especifica y escribe:

  1) un CSV de estado por modelo/experimento (models_catalog_status.csv)
  2) un JSON con, para cada archivo NetCDF necesario, su nombre y la
     lista de URLs HTTP (fileServer) de todos los nodos ESGF que lo
     replican -- para poder reintentar en otro mirror si el primero
     esta caido o es lento (situacion observada en la practica).

Idempotente: si models_catalog_status.csv ya existe, no se vuelve a
consultar ESGF (8+ peticiones por modelo). Para forzar un refresco hay
que borrar ese CSV y el JSON juntos a mano -- ver el mensaje que
imprime este script cuando eso pasa.

NOTA: el bucket AWS Open Data de CMIP6 (s3://cmip6-pds/) almacena los
datos en formato Zarr, no NetCDF, por lo que CDO no puede leerlo
directamente ("Unsupported file type", verificado). Por eso se
consulta ESGF a nivel de archivo y se guardan URLs HTTP de descarga
directa (NetCDF real, verificado), en vez de prefijos S3.

NOTA: ya no se busca ni descarga 'sftlf' (fraccion de tierra) por
modelo. El paso 05 aplica en su lugar la mascara oceano-tierra propia
de ERSSTv5 (el dato observado de referencia) sobre los campos ya
regrillados a esa misma grilla en el paso 04 -- evita depender de una
variable fx que a veces se publica en un grid_label distinto al de tos
(se observo empiricamente, p.ej. GFDL-ESM4: tos en 'gr', sftlf en
'gr1') y garantiza que modelo y observado compartan exactamente la
misma huella valida/faltante.

Solo se descarga 'tos' mensual (Omon). No descarga ningun dato: eso lo
hace 02_download_cmip6_chunks.sh.

NOTA (correccion): la busqueda no filtraba por 'variant_label' (el
miembro del ensamble, p.ej. r1i1p1f1). CMIP6 publica rutinariamente
varias realizaciones del mismo modelo/experimento (r1i1p1f1, r2i1p1f1,
..., r10i1p1f1); sin fijar una sola, 02 descargaba TODAS y las unia con
'cdo mergetime' como si fueran fragmentos consecutivos de una misma
serie, multiplicando los pasos de tiempo y rompiendo la continuidad del
eje temporal (verificado: ACCESS-CM2 ssp245 traia 10 miembros unidos en
un solo archivo de 10320 pasos en vez de los 1032 esperados). Ahora se
determina, por modelo, el 'variant_label' disponible en TODOS los
experimentos requeridos a la vez (prefiriendo 'r1i1p1f1'), y se filtra la busqueda
de archivos a ese unico miembro.
"""
import csv
import json
import re
import sys
from pathlib import Path

import pipeline_config

ESGF_SEARCH_URL = "https://esgf-node.llnl.gov/esg-search/search"
# El metodo de Szabo usado en esta propuesta estima la variabilidad
# interna a partir de los residuos de historical+escenario.
EXPERIMENTS = pipeline_config.experiments()
VARIABLE, TABLE = "tos", "Omon"


def _realization_number(member: str) -> int:
    m = re.match(r"r(\d+)", member)
    return int(m.group(1)) if m else 10**9


def find_common_member(model: str, variable: str, table: str) -> str | None:
    """Devuelve el variant_label disponible en todos los experimentos
    requeridos para este modelo (prefiere 'r1i1p1f1'; si no esta
    disponible en todos a la vez, usa el de menor numero que si lo
    este). None si no hay ningun miembro comun a todos."""
    members_per_exp: dict[str, set[str]] = {}
    for exp in EXPERIMENTS:
        params = {
            "project": "CMIP6", "source_id": model, "experiment_id": exp,
            "variable_id": variable, "table_id": table, "type": "File",
            "format": "application/solr+json", "limit": 0,
            "facets": "variant_label",
        }
        r = pipeline_config.esgf_get(ESGF_SEARCH_URL, params, timeout=30)
        facet_field = r.json()["facet_counts"]["facet_fields"].get("variant_label", [])
        members_per_exp[exp] = set(facet_field[0::2])  # [valor, conteo, valor, conteo, ...]

    common = set.intersection(*members_per_exp.values()) if members_per_exp else set()
    if not common:
        return None
    if "r1i1p1f1" in common:
        return "r1i1p1f1"
    return sorted(common, key=_realization_number)[0]


def esgf_file_search(model: str, experiment: str, variable: str, table: str, grid_label: str | None, member: str) -> list[dict]:
    """Busca archivos en ESGF para una grilla y un miembro de ensamble
    especificos, y devuelve una lista de {filename, urls}. Un mismo
    archivo logico puede estar replicado en varios nodos ESGF; se
    agrupan por nombre de archivo y se guardan todas las URLs
    HTTPServer encontradas, en orden de aparicion, como candidatos de
    descarga (02 los intenta en orden hasta que uno funcione).
    """
    params = {
        "project": "CMIP6", "source_id": model, "experiment_id": experiment,
        "variable_id": variable, "table_id": table, "type": "File",
        "variant_label": member,
        "format": "application/solr+json",
    }
    if grid_label:
        params["grid_label"] = grid_label

    docs = pipeline_config.esgf_get_all_docs(ESGF_SEARCH_URL, params, timeout=30)
    year_start, year_end = pipeline_config.experiment_year_range(experiment)

    by_filename: dict[str, list[str]] = {}
    for d in docs:
        filename = d.get("title")
        if not filename:
            continue
        # Descarta de entrada archivos fuera del rango de anios que
        # este pipeline necesita (ver file_overlaps_range) -- algunos
        # modelos publican corridas extendidas mas alla de 2100 en
        # algun nodo, y no tiene sentido verificar/imprimir nada sobre
        # archivos que de todas formas nunca se van a descargar.
        if not pipeline_config.file_overlaps_range(filename, year_start, year_end):
            continue
        for u in d.get("url", []):
            url, mime, service = (u.split("|") + ["", "", ""])[:3]
            if service == "HTTPServer":
                by_filename.setdefault(filename, [])
                if url not in by_filename[filename]:
                    by_filename[filename].append(url)

    # Confirma que al menos un mirror responde de verdad (HEAD, sin
    # bajar el archivo) antes de dar el archivo por encontrado -- ESGF
    # a veces indexa un archivo cuyo link ya no esta vivo (nodo
    # reorganizado, replica caida). Si ninguno responde, se descarta:
    # mejor marcar el modelo incompleto ahora que descubrirlo recien en
    # el paso 02, despues de gastar tiempo intentando la descarga real.
    verified: dict[str, list[str]] = {}
    for filename, urls in by_filename.items():
        live = pipeline_config.pick_first_live_url(urls)
        if live:
            verified[filename] = live
        else:
            print(f"    {filename}: ningun mirror responde, se descarta", file=sys.stderr)

    return [{"filename": fn, "urls": urls} for fn, urls in sorted(verified.items())]


CATALOG_FIELDNAMES = ["model", "grid_label", "complete", *EXPERIMENTS, "member_id", "fuente"]


def main(seed_csv: str, out_csv: str, out_files_json: str) -> None:
    # Nota: esto solo corre cuando out_csv NO existe todavia (ver el
    # gate de idempotencia en __main__ mas abajo) -- por eso arma
    # status_rows/file_catalog desde cero, sin fusionar con una corrida
    # anterior (no puede haber una: si existiera, no se habria llegado
    # hasta aca). Un modelo agregado a mano por fuera de la semilla
    # (via 00c + 02b_search_alt_esgf_nodes.py) que ya estaba resuelto
    # se pierde del catalogo si se borra para forzar un refresco -- hay
    # que volver a correr 02b para el.
    with open(seed_csv, newline="") as f:
        seed_rows = list(csv.DictReader(f))

    status_rows = []
    file_catalog: dict[str, dict] = {}

    for row in seed_rows:
        model = row["model"]
        grid_label = row.get("grid_label") or None

        member = find_common_member(model, VARIABLE, TABLE)
        if member is None:
            print(f"{model}: sin variant_label comun a todos los experimentos requeridos", file=sys.stderr)
            status_rows.append({
                "model": model, "grid_label": grid_label or "", "member_id": "", "complete": "False",
                **{exp: "False" for exp in EXPERIMENTS}, "fuente": "no_encontrado",
            })
            continue

        found = {exp: esgf_file_search(model, exp, VARIABLE, TABLE, grid_label, member) for exp in EXPERIMENTS}
        complete = all(found[exp] for exp in EXPERIMENTS)
        n_files = {exp: len(found[exp]) for exp in EXPERIMENTS}
        print(f"{model} (grid={grid_label}, miembro={member}): completo={complete} archivos_por_experimento={n_files}",
              file=sys.stderr)

        status_rows.append({
            "model": model, "grid_label": grid_label or "", "member_id": member, "complete": str(complete),
            **{exp: str(bool(found[exp])) for exp in EXPERIMENTS},
            "fuente": "esgf_principal" if complete else "no_encontrado",
        })

        if complete:
            file_catalog[model] = dict(found)

    Path(out_csv).parent.mkdir(parents=True, exist_ok=True)
    with open(out_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CATALOG_FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(status_rows)

    Path(out_files_json).parent.mkdir(parents=True, exist_ok=True)
    with open(out_files_json, "w") as f:
        json.dump(file_catalog, f, indent=2)

    n_complete = sum(1 for r in status_rows if r["complete"] == "True")
    print(f"Catalogo escrito en {out_csv} y {out_files_json} "
          f"({n_complete}/{len(status_rows)} modelos completos)", file=sys.stderr)


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit("uso: 01_query_esgf_catalog.py <seed.csv> <out_status.csv> <out_files.json>")
    seed_csv_arg, out_csv_arg, out_files_json_arg = sys.argv[1], sys.argv[2], sys.argv[3]

    # Idempotente (mismo patron que 00b_build_model_list.py): si el
    # catalogo ya existe, no se vuelve a consultar ESGF (8+ peticiones
    # por modelo). Esto significa que un modelo que antes fallo pero
    # ESGF ya publico via el MISMO nodo/miembro no se va a detectar
    # solo -- para eso hay que forzar un refresco. (02b/02c si siguen
    # actualizando el catalogo directamente cuando resuelven un modelo
    # por otra via, sin necesidad de correr esto de nuevo).
    if Path(out_csv_arg).exists():
        print(
            f"{out_csv_arg} ya existe, no se vuelve a consultar ESGF.\n"
            f"Para forzar un refresco (por si algun modelo se completo en ESGF desde la "
            f"ultima vez): borra {out_csv_arg} Y {out_files_json_arg} juntos "
            "(no uno solo, para que no queden inconsistentes entre si) y volve a correr esto. "
            "OJO: si habias resuelto algun modelo a mano por fuera de la semilla (00c + 02b), "
            "se pierde del catalogo y hay que correr 02b de nuevo para el.",
            file=sys.stderr,
        )
        sys.exit(0)

    main(seed_csv_arg, out_csv_arg, out_files_json_arg)
