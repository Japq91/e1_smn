#!/usr/bin/env python3
"""Utilidades compartidas por los scripts de graficado (plot_*.py),
extraidas de graficos_exploratorios.ipynb para poder correrlos desde
terminal sin Jupyter -- pensado para un cluster HPC sin interfaz
grafica.

Fuerza el backend 'Agg' de matplotlib (sin ventana/GUI) ANTES de
importar pyplot: cualquier script que importe este modulo primero
queda con ese backend fijo para el resto del proceso, sin necesidad de
tener un $DISPLAY disponible.
"""
import csv
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402 (import despues de matplotlib.use, a proposito)
import netCDF4 as nc  # noqa: E402
import numpy as np  # noqa: E402

plt.rcParams.update({"font.size": 10})
plt.rcParams["font.family"] = "serif"
plt.rcParams["font.serif"] = ["Times New Roman"] + plt.rcParams["font.serif"]

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "data/raw/cmip6"
MASKED_DIR = BASE_DIR / "data/processed/masked"
QC_CSV = BASE_DIR / "data/processed/qc_report.csv"
MODEL_AVAILABILITY_CSV = BASE_DIR / "informe/model_availability_priority.csv"
CATALOG_CSV = BASE_DIR / "data/interim/models_catalog_status.csv"
INVENTORY_CSV = BASE_DIR / "data/processed/models_inventory_final.csv"
FIGURES_DIR = BASE_DIR / "figures"

# Todas las figuras se guardan livianas (DPI 100) -- pensado para que
# el informe/presentacion no pese de mas, y para no generar archivos
# grandes en el HPC sin necesidad.
DPI = 150

sys.path.insert(0, str(BASE_DIR / "scripts"))
import pipeline_config  # noqa: E402

EXPERIMENTS = pipeline_config.experiments()  # ["historical", <escenarios SSP>]
SCENARIOS = pipeline_config.scenarios()

NON_DATA_NAMES = {"lat", "lon", "x", "y", "time", "lat_bnds",
                  "lon_bnds", "time_bnds", "bnds", "area"}

# Cajas de referencia (formato de longitud 0-360, igual que config/domains.yaml)
NINO34 = dict(lon1=190, lon2=240, lat1=-5, lat2=5)
NINO12 = dict(lon1=270, lon2=280, lat1=-10, lat2=0)

# Paleta de escenarios: 'historical' siempre gris; cada escenario SSP de
# SCENARIOS (config/periods.yaml) toma el siguiente color de esta lista,
# en orden -- asi ssp245 sigue en azul y ssp585 en rojo aunque se
# agreguen escenarios nuevos en el medio (p.ej. ssp370 en naranja).
SCENARIO_COLORS = ["tab:blue", "tab:orange", "tab:red", "tab:purple", "tab:green", "tab:brown"]


def should_regenerate_batch(existing_paths, kind: str = "figura(s)") -> bool:
    """Pregunta UNA sola vez si se deben regenerar TODAS las figuras
    de 'existing_paths' (las que YA EXISTEN) -- nunca una pregunta por
    archivo/modelo. Decision explicita del usuario: una tanda de N
    modelos no debe significar N preguntas identicas; los archivos
    NUEVOS (de un modelo recien descargado, por ejemplo) los generan
    los llamadores directamente, sin pasar por aca, porque no hay nada
    que decidir sobre algo que todavia no existe.

    Limite de 15s (misma mecanica que la confirmacion de nodos
    alternativos en 02_download_all_sources.sh): el default ante
    silencio/timeout/sin terminal interactiva es MANTENER las figuras
    ya generadas (el comportamiento historico de este pipeline era
    saltarlas siempre) -- al reves del default de esa otra
    confirmacion (ahi 'sin respuesta' significaba seguir intentando
    fuentes nuevas), porque aca 'sin respuesta' corresponde a no tocar
    algo que ya existe, no a arrancar algo nuevo.

    Si 'existing_paths' esta vacia no hay nada que preguntar (False,
    sin efecto: los llamadores solo la consultan cuando SI hay algo
    existente de por medio)."""
    existing_paths = list(existing_paths)
    if not existing_paths:
        return False
    if not sys.stdin.isatty():
        print(f"{len(existing_paths)} {kind} ya existen, se omiten "
              "(sin terminal interactiva para preguntar).", file=sys.stderr)
        return False
    import select
    print(f"{len(existing_paths)} {kind} ya existen. Regenerar TODAS? [s/N, 15s, por defecto N] ",
          end="", file=sys.stderr, flush=True)
    rlist, _, _ = select.select([sys.stdin], [], [], 15)
    if not rlist:
        print("", file=sys.stderr)
        print("(sin respuesta en 15s, se mantienen las existentes)", file=sys.stderr)
        return False
    respuesta = sys.stdin.readline().strip().lower()
    return respuesta.startswith("s")


def model_numbers() -> dict[str, str]:
    """{model: "M001"} -- orden alfabetico sobre TODOS los modelos de
    MODEL_AVAILABILITY_CSV (el mismo universo de 102 que inspecciona
    00b, no solo los descargados), misma fuente/orden/ancho que
    build_model_registry.py y plot_qc_summary.py -- para que el numero
    de un modelo sea siempre el mismo en cualquier figura o reporte
    que lo use."""
    with open(MODEL_AVAILABILITY_CSV, newline="") as f:
        models = sorted(row["model"] for row in csv.DictReader(f))
    width = max(3, len(str(len(models))))
    return {m: f"M{i:0{width}d}" for i, m in enumerate(models, start=1)}


def sst_2d_filename(model: str, model_number: str | None) -> str:
    """Nombre de archivo del mapa 2D de plot_maps.py, con el codigo
    M001..M102 como primer segmento (pedido del usuario, para poder
    ordenar/identificar las figuras por numero de modelo a simple
    vista) -- ej. "M001_sst_2d_ACCESS-CM2.png". ERSSTv5 no tiene
    codigo (no es uno de los 102 modelos CMIP6): queda sin prefijo,
    como antes."""
    prefix = f"{model_number}_" if model_number else ""
    return f"{prefix}sst_2d_{model}.png"


def series_filename(model: str, box_name: str, model_number: str | None) -> str:
    """Nombre de archivo de la serie de plot_box_series.py, con el
    mismo prefijo M001..M102 que sst_2d_filename."""
    prefix = f"{model_number}_" if model_number else ""
    return f"{prefix}serie_{model}_sst_{box_name.replace(' ', '')}.png"


def selected_models() -> list[str]:
    """Modelos que de verdad quedaron en el entregable final: los
    marcados selected=True en data/processed/models_inventory_final.csv
    (paso 07 -- exige los 4 experimentos requeridos, todos con PASS en
    control de calidad). Antes los scripts de plot usaban un criterio
    mas laxo (cualquier archivo tos_<modelo>_historical.nc presente en
    data/processed/masked/, sin mirar QC ni si estan los 4
    experimentos) -- eso graficaba modelos con descarga parcial que el
    inventario ya excluia (mismo bug real corregido en
    07_build_inventory_report.py: un modelo como CIESM, con solo 3 de
    4 experimentos, apareceria en las figuras como si fuera uno mas)."""
    if not INVENTORY_CSV.exists():
        sys.exit(f"Falta {INVENTORY_CSV}. Se genera con run.sh (paso 07).")
    with open(INVENTORY_CSV, newline="") as f:
        return sorted(row["model"] for row in csv.DictReader(f) if row["selected"] == "True")


def masked_path(model: str, exp: str = "historical") -> Path:
    if model.upper().startswith("ERSST"):
        return MASKED_DIR / "ersstv5_region.nc"
    return MASKED_DIR / f"tos_{model}_{exp}.nc"


def box_mean(model: str, exp: str, lon1: float, lon2: float, lat1: float, lat2: float):
    """Devuelve (anios_decimales, valores) promediados en la caja dada."""
    with nc.Dataset(masked_path(model, exp)) as ds:
        varname = next(v for v in ds.variables if v not in NON_DATA_NAMES)
        lat = ds.variables["lat"][:]
        lon = ds.variables["lon"][:]
        data = np.ma.masked_invalid(ds.variables[varname][:])
        time = ds.variables["time"]
        dates = nc.num2date(time[:], time.units, getattr(time, "calendar", "standard"))

    lat_idx = np.where((lat >= lat1) & (lat <= lat2))[0]
    lon_idx = np.where((lon >= lon1) & (lon <= lon2))[0]
    sub = data[:, lat_idx, :][:, :, lon_idx]
    serie = sub.mean(axis=(1, 2))
    years = np.array([d.year + (d.month - 0.5) / 12 for d in dates])
    return years, serie


def scenario_styles() -> dict:
    styles = {"historical": dict(color="gray", alpha=1.0)}
    for i, exp in enumerate(SCENARIOS):
        styles[exp] = dict(color=SCENARIO_COLORS[i % len(SCENARIO_COLORS)], alpha=0.8)
    return styles
