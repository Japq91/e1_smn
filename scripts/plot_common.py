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
MASKED_DIR = BASE_DIR / "data/processed/masked"
QC_CSV = BASE_DIR / "data/processed/qc_report.csv"
MODEL_AVAILABILITY_CSV = BASE_DIR / "informe/model_availability_priority.csv"
FIGURES_DIR = BASE_DIR / "figures"

# Todas las figuras se guardan livianas (DPI 100) -- pensado para que
# el informe/presentacion no pese de mas, y para no generar archivos
# grandes en el HPC sin necesidad.
DPI = 100

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


def list_available_models() -> list[str]:
    return sorted(
        f.stem.replace("tos_", "", 1).replace("_historical", "")
        for f in MASKED_DIR.glob("tos_*_historical.nc")
    )


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
