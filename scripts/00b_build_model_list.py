#!/usr/bin/env python3
"""Construye la lista de modelos CMIP6 a usar (paso 00b).

A diferencia de la version anterior (que partia de una lista semilla
curada, la de Bruno Ramirez 2023), este script inspecciona TODOS los
modelos CMIP6 publicados en ESGF y los filtra segun el criterio
acordado con el proyecto:

  1. Deben tener la variable 'tos' (Omon) disponible.
  2. Deben tener 'historical' (o su equivalente 'hist-1950' de
     HighResMIP, ver pipeline_config.has_historical) publicado --
     requisito duro, es la base para el calculo de TOE. Se busca
     primero en el nodo principal de ESGF (ORNL); si no aparece ahi, se
     prueba en los nodos alternativos de la federacion (mismo fallback
     que 02b_search_alt_esgf_nodes.py) antes de descartar el modelo --
     asi no se pierde un modelo solo porque el nodo principal tiene ese
     indice incompleto.
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
informe/model_availability_priority.csv -- una fila por TODOS los
modelos inspeccionados (no solo los seleccionados), con columnas 0/1
(tiene_tos, tiene_hist, tiene_sspXXX por cada escenario de
config/periods.yaml) y una columna 'prioridad' pensada para buscar
manualmente en ESGF en el orden que mas rinde: primero los que no
tienen tos en absoluto, despues los que tienen tos pero no
historical/hist-1950, despues los que tienen historical pero les falta
el primer SSP configurado, y asi -- los ya completos (prioridad 0)
quedan al final. check_model_availability.py sigue disponible aparte
como herramienta manual de segunda opinion (ver su propio docstring),
con su propio reporte categorico (informe/model_availability_report.*).

Este script reemplaza a config/models_seed_bruno2023.csv como fuente
de la lista de modelos; ese archivo se conserva sin usar, como
referencia historica (no se elimina).

Idempotente con deteccion de cambio: antes de decidir si hace falta
rehacer el barrido completo (100+ modelos, varias peticiones cada
uno), hace una sola consulta barata (cuantos modelos con tos/Omon hay
AHORA en el nodo principal) y la compara contra la cantidad de filas
que tiene informe/model_availability_priority.csv de la corrida
anterior. Si coincide, no repite el barrido. Si no coincide (o es la
primera vez), lo rehace -- asi un modelo nuevo publicado en ESGF se
detecta solo, sin tener que acordarse de borrar nada a mano.
"""
import csv
import re
import sys
from pathlib import Path

import requests

import pipeline_config

BASE_DIR = Path(__file__).resolve().parent.parent
# Nodo principal: esgf-node.ornl.gov (via /proxy/search -- su endpoint
# clasico '/esg-search/search' ya no sirve JSON, ver pipeline_config.py).
# Cambiado desde esgf-node.llnl.gov: verificado que ambos conocen
# exactamente el mismo universo de 102 modelos con tos/Omon (cruzado
# nombre por nombre, cero diferencias), asi que el cambio no pierde
# cobertura.
ESGF_SEARCH_URL = "https://esgf-node.ornl.gov/proxy/search"
VARIABLE, TABLE = "tos", "Omon"
REQUIRED_EXPERIMENTS = set(pipeline_config.experiments())
PRIORITY_REPORT_CSV = BASE_DIR / "informe/model_availability_priority.csv"


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


ALT_NODE_MAX_RETRIES = 2  # igual que 02b_search_alt_esgf_nodes.py: hay 8 nodos
# de respaldo para probar en cascada, asi que conviene fallar rapido en uno
# que esta realmente caido y pasar al siguiente, en vez de esperar ~160s
# (6 reintentos con backoff) por cada nodo problematico y por cada modelo
# que necesita este fallback.


def model_datasets(model: str, base_url: str = ESGF_SEARCH_URL, max_retries: int = pipeline_config.ESGF_MAX_RETRIES) -> list[dict]:
    """Todos los datasets (cualquier experimento/grilla) de tos/Omon para un
    modelo, contra el nodo indicado (por defecto, el principal). Pagina
    con esgf_get_all_docs en vez de un limit fijo -- un dataset es mucho
    mas grueso que un archivo (agrupa todos los timesteps de un
    modelo/experimento/variante/grilla en un solo registro), asi que en
    la practica nunca se acercaba al limit=500 anterior, pero es el
    mismo patron de riesgo que causo el bug real de
    esgf_file_search (ver pipeline_config.esgf_get_all_docs) -- mejor
    no dejarlo con un techo fijo tampoco aca."""
    params = {
        "project": "CMIP6", "source_id": model, "variable_id": VARIABLE, "table_id": TABLE,
        "type": "Dataset", "format": "application/solr+json",
    }
    return pipeline_config.esgf_get_all_docs(base_url, params, timeout=60, max_retries=max_retries)


def experiments_present(docs: list[dict]) -> set[str]:
    """experiment_id de cualquier dataset de la lista, sin importar la
    grilla -- para el reporte de disponibilidad (a diferencia de
    pick_coarsest_grid, que exige que TODOS esten bajo una misma grilla)."""
    return {_first(d, "experiment_id") for d in docs if _first(d, "experiment_id")}


def fetch_model_docs(model: str) -> tuple[list[dict], str]:
    """Devuelve (docs, fuente) para un modelo. 'historical' (o su
    equivalente 'hist-1950', ver pipeline_config.has_historical) es
    requisito duro: se busca primero en el nodo principal (ORNL); si no
    aparece ahi, se prueba en los nodos alternativos de la federacion
    (uno por uno, el primero que lo tenga) y se agregan esos docs a los
    del principal. Si ningun nodo lo tiene, se devuelven los docs del
    principal tal cual (pueden tener igual algun SSP, para el reporte
    de disponibilidad) con fuente='sin_historical'."""
    docs = model_datasets(model)
    if pipeline_config.has_historical(experiments_present(docs)):
        return docs, "esgf_principal"

    for alt_url in pipeline_config.ALT_ESGF_SEARCH_URLS:
        if alt_url == ESGF_SEARCH_URL:
            continue  # ya es el nodo principal, no tiene sentido consultarlo de nuevo
        try:
            alt_docs = model_datasets(model, base_url=alt_url, max_retries=ALT_NODE_MAX_RETRIES)
        except requests.RequestException:
            continue
        if pipeline_config.has_historical(experiments_present(alt_docs)):
            return docs + alt_docs, "esgf_alt_node"

    return docs, "sin_historical"


KM_PER_DEGREE = 111.0  # aprox. en el ecuador; suficiente como proxy de resolucion


def parse_resolution_km(res_str: str):
    """La 'nominal_resolution' de CMIP6 casi siempre usa bins fijos en km
    (p.ej. '100 km'), pero algunas grillas regrilladas la reportan en
    grados (p.ej. '1x1 degree') -- se extrae el primer numero y, si la
    unidad es 'degree', se convierte a km aproximados (1 grado ~111 km)
    antes de devolverlo, para no comparar numeros en unidades distintas.

    BUG real evitado: antes se tomaba el numero crudo sin mirar la
    unidad -- '1x1 degree' se leia como '1 km', mucho mas fino que los
    '100 km' de la otra grilla, cuando en realidad 1 grado son ~111 km
    (bastante MAS grueso). Verificado con CESM2: eso hacia que 00b
    eligiera la grilla 'gn' (100 km reales) en vez de 'gr' (~111 km
    reales, la efectivamente mas gruesa) -- y 'gn' resulto no tener
    publicado el miembro r1i1p1f1 para los escenarios SSP (solo
    r4i1p1f1), mientras que 'gr' si lo tenia."""
    if not res_str:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)", res_str)
    if not m:
        return None
    value = float(m.group(1))
    if "degree" in res_str.lower():
        value *= KM_PER_DEGREE
    return value


def priority_tier(present: set[str]) -> int:
    """Orden de prioridad para busqueda manual (pedido explicito del
    usuario): 1=sin tos, 2=con tos pero sin historical/hist-1950,
    3..N=con historical, le falta el primer escenario de
    config/periods.yaml que no tenga (en el orden ahi definido -- hoy
    ssp245, ssp370, ssp585 -> tiers 3, 4, 5), 0=completo (ultimo, no
    necesita busqueda manual). En la practica el tier 1 nunca aparece
    (list_all_models() ya filtra por tos), se deja por si acaso."""
    if not present:
        return 1
    if not pipeline_config.has_historical(present):
        return 2
    for i, scenario in enumerate(pipeline_config.scenarios()):
        if scenario not in present:
            return 3 + i
    return 0


def write_priority_report(rows: list[dict], out_path: Path) -> None:
    """Escribe informe/model_availability_priority.csv: una fila por
    modelo, 0/1 en vez de True/False, ordenada por prioridad de
    busqueda manual (ver priority_tier). Reemplaza a
    informe/model_availability_report.csv/.md como reporte principal de
    00b -- ese esquema viejo (True/False por columna fija) confundia
    'no tiene historical/ssp' con 'no tiene tos en absoluto' (bug real
    encontrado por el usuario, ver has_historical); este es honesto
    sobre la diferencia."""
    scenarios = pipeline_config.scenarios()
    fieldnames = ["prioridad", "model", "tiene_tos", "tiene_hist", "cual_historical",
                  *[f"tiene_{s}" for s in scenarios], "experimentos_encontrados"]
    rows_sorted = sorted(rows, key=lambda r: (r["prioridad"], r["model"]))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows_sorted)
    n_completos = sum(1 for r in rows if r["prioridad"] == 0)
    print(f"\n{n_completos}/{len(rows)} modelos completos (prioridad 0). "
          f"Detalle de prioridad de busqueda manual en {out_path}", file=sys.stderr)


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


def main(out_csv: str, models: list[str], priority_csv: Path = PRIORITY_REPORT_CSV) -> None:
    seed_rows = []
    priority_rows = []
    for i, model in enumerate(sorted(models), start=1):
        docs, fuente_hist = fetch_model_docs(model)
        present = experiments_present(docs)
        hist_variant = pipeline_config.has_historical(present)
        tier = priority_tier(present)
        scenarios = pipeline_config.scenarios()
        priority_rows.append({
            "prioridad": tier,
            "model": model,
            "tiene_tos": 1 if present else 0,
            "tiene_hist": 1 if hist_variant else 0,
            "cual_historical": hist_variant or "",
            **{f"tiene_{s}": (1 if s in present else 0) for s in scenarios},
            "experimentos_encontrados": "|".join(sorted(present)),
        })

        choice = pick_coarsest_grid(docs) if hist_variant else None
        detalle = f" (prioridad={tier}" + (f", historical via {fuente_hist}" if fuente_hist == "esgf_alt_node" else "") + ")"
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

    write_priority_report(priority_rows, priority_csv)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("uso: 00b_build_model_list.py <out_seed.csv>")
    out_csv_arg = sys.argv[1]

    # Idempotente, pero con deteccion de cambio: en vez de "si el
    # archivo ya existe, no tocar nunca mas", se hace primero UNA sola
    # consulta barata (list_all_models(), una faceta) para saber cuantos
    # modelos con tos/Omon hay AHORA en el nodo principal, y se compara
    # contra cuantos habia la ultima vez (la cantidad de filas de
    # PRIORITY_REPORT_CSV). Si coincide, no se repite el barrido
    # completo (100+ peticiones). Si no coincide (o es la primera vez),
    # se rehace todo -- asi un modelo nuevo publicado en ESGF se detecta
    # solo, sin tener que acordarse de borrar el CSV a mano.
    models_now = list_all_models()
    n_now = len(models_now)
    print(f"Modelos CMIP6 con tos/Omon publicado (nodo principal): {n_now}", file=sys.stderr)

    n_before = None
    if PRIORITY_REPORT_CSV.exists():
        with open(PRIORITY_REPORT_CSV, newline="") as f:
            n_before = sum(1 for _ in csv.DictReader(f))

    if Path(out_csv_arg).exists() and n_before == n_now:
        print(
            f"{out_csv_arg} ya existe y el universo de modelos con tos/Omon sigue en {n_now} "
            f"-- no se vuelve a inspeccionar. Para forzar un refresco de todas formas "
            f"(ej. cambio en config/periods.yaml): borra {out_csv_arg} y {PRIORITY_REPORT_CSV} "
            "y volve a correr esto.",
            file=sys.stderr,
        )
        sys.exit(0)

    if Path(out_csv_arg).exists() and n_before is not None and n_before != n_now:
        print(f"El universo de modelos con tos/Omon cambio de {n_before} a {n_now} -- se vuelve a inspeccionar todo.",
              file=sys.stderr)

    main(out_csv_arg, models_now)
