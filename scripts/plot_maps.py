#!/usr/bin/env python3
"""GRAFICO 1: mapas -- promedio temporal (mes 1950-12) del campo
completo, por modelo/experimento y para ERSSTv5. Extraido de
graficos_exploratorios.ipynb para poder correrlo desde terminal sin
Jupyter (ej. un cluster HPC sin interfaz grafica).

Requiere que data/processed/masked/ ya tenga archivos (correr
./run.sh hasta el paso 05 como minimo).

Uso:
    python3 scripts/plot_maps.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import plot_common as pc  # noqa: E402 (fuerza el backend Agg antes de pyplot)

import matplotlib.pyplot as plt  # noqa: E402
import netCDF4 as nc  # noqa: E402
import numpy as np  # noqa: E402
import xarray as xr  # noqa: E402


def plot_map(model: str, exp: str = "historical", ax=None) -> None:
    with nc.Dataset(pc.masked_path(model, exp)) as ds:
        varname = next(v for v in ds.variables if v not in pc.NON_DATA_NAMES)
    d = xr.open_dataset(pc.masked_path(model, exp))

    standalone = ax is None
    if standalone:
        fig, ax = plt.subplots(figsize=(9, 4))
    d1 = d[varname].sel(time=slice("1950-12", "1950-12"))
    d1.plot(ax=ax, extend="both", cmap="turbo", levels=np.arange(20, 34, 1))
    ax.set_xlabel("longitud")
    ax.set_ylabel("latitud")
    ax.set_title(f"{model} {exp.upper()}")
    pc.FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    plt.savefig(pc.FIGURES_DIR / f"sst_2d_{model}.png", dpi=pc.DPI, bbox_inches="tight")
    if standalone:
        plt.close()


def main() -> None:
    models = pc.list_available_models()
    if not models:
        sys.exit(f"No hay archivos tos_*_historical.nc en {pc.MASKED_DIR} -- corre run.sh hasta el paso 05.")

    print(f"Graficando mapas: {len(models)} modelo(s) + ERSSTv5 ...", file=sys.stderr)
    for model in models:
        print(f"  {model}", file=sys.stderr)
        plot_map(model, "historical")
    print("  ERSSTv5", file=sys.stderr)
    plot_map("ERSSTv5")
    print(f"Listo, {len(models) + 1} figura(s) en {pc.FIGURES_DIR}", file=sys.stderr)


if __name__ == "__main__":
    main()
