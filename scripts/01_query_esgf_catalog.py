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
        "format": "application/solr+json", "limit": 200,
    }
    if grid_label:
        params["grid_label"] = grid_label

    r = pipeline_config.esgf_get(ESGF_SEARCH_URL, params, timeout=30)
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


CATALOG_FIELDNAMES = ["model", "grid_label", "complete", *EXPERIMENTS, "member_id", "fuente"]


def main(seed_csv: str, out_csv: str, out_files_json: str) -> None:
    with open(seed_csv, newline="") as f:
        seed_rows = list(csv.DictReader(f))

    # Fusiona con lo que ya exista, en vez de sobreescribir: preserva
    # modelos que no estan en la semilla (agregados a mano via 00c/02b/
    # 02c, ej. los 56 citados en la literatura). Se re-consulta ESGF
    # SIEMPRE para cada modelo de la semilla (asi se detectan mejoras --
    # ESGF publica datos nuevos con el tiempo; se confirmo en la
    # practica con CESM2: la primera corrida solo probo 'r1i1p1f1' y no
    # encontro ssp245/ssp585 bajo ese miembro, pero 'r4i1p1f1' si tiene
    # los 3 experimentos). La regla para no perder trabajo previo es al
    # ESCRIBIR el resultado, no al consultar:
    #   - si la consulta fresca da complete=True, siempre se usa (mejora
    #     real, sea cual sea el estado anterior)
    #   - si NO da complete=True, se conserva el estado anterior tal
    #     cual cuando ese estado anterior ya era 'lo mejor posible'
    #     (complete=True por cualquier fuente, o resuelto via
    #     copernicus_parcial/esgf_alt_node) -- para no degradar un
    #     modelo ya resuelto solo porque esta consulta puntual al nodo
    #     principal no lo encuentre completo
    existing_by_model: dict[str, dict] = {}
    if Path(out_csv).exists():
        with open(out_csv, newline="") as f:
            for row in csv.DictReader(f):
                existing_by_model[row["model"]] = row

    file_catalog: dict[str, dict] = {}
    if Path(out_files_json).exists():
        file_catalog = json.loads(Path(out_files_json).read_text())

    for row in seed_rows:
        model = row["model"]
        grid_label = row.get("grid_label") or None
        existing = existing_by_model.get(model)
        existing_is_protected = existing is not None and (
            existing.get("complete") == "True"
            or existing.get("fuente") in ("copernicus_parcial", "esgf_alt_node")
        )

        member = find_common_member(model, VARIABLE, TABLE)
        if member is None:
            print(f"{model}: sin variant_label comun a los 3 experimentos", file=sys.stderr)
            if not existing_is_protected:
                existing_by_model[model] = {
                    "model": model, "grid_label": grid_label or "", "member_id": "", "complete": "False",
                    **{exp: "False" for exp in EXPERIMENTS}, "fuente": "no_encontrado",
                }
            elif existing is not None:
                print(f"  {model}: se conserva el estado existente ('{existing.get('fuente')}'), no se degrada", file=sys.stderr)
            continue

        found = {exp: esgf_file_search(model, exp, VARIABLE, TABLE, grid_label, member) for exp in EXPERIMENTS}
        complete = all(found[exp] for exp in EXPERIMENTS)
        n_files = {exp: len(found[exp]) for exp in EXPERIMENTS}
        print(f"{model} (grid={grid_label}, miembro={member}): completo={complete} archivos_por_experimento={n_files}",
              file=sys.stderr)

        if not complete and existing_is_protected:
            print(f"  {model}: se conserva el estado existente ('{existing.get('fuente')}'), no se degrada", file=sys.stderr)
            continue

        existing_by_model[model] = {
            "model": model, "grid_label": grid_label or "", "member_id": member, "complete": str(complete),
            **{exp: str(bool(found[exp])) for exp in EXPERIMENTS},
            "fuente": "esgf_principal" if complete else "no_encontrado",
        }

        if complete:
            file_catalog[model] = dict(found)

    status_rows = list(existing_by_model.values())

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
    main(sys.argv[1], sys.argv[2], sys.argv[3])
