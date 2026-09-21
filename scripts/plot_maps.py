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
    out_path = pc.FIGURES_DIR / f"sst_2d_{model}.png"
    if ax is None and not pc.should_regenerate(out_path, label=f"{model}: {out_path.name}"):
        return

    with nc.Dataset(pc.masked_path(model, exp)) as ds:
        varname = next(v for v in ds.variables if v not in pc.NON_DATA_NAMES)
    d = xr.open_dataset(pc.masked_path(model, exp))

    standalone = ax is None
    if standalone:
        fig, ax = plt.subplots(figsize=(9, 4))
    # .sel(...).squeeze() puede dejar dimensiones sueltas de tamano 1
    # (ej. una malla nativa con una dimension extra) -- si no queda
    # 2D (lat, lon), NO usar el dispatch generico d1.plot(...): para
    # datos ambiguos xarray a veces elige plot.hist() en vez de un
    # campo 2D, y revienta con un error de matplotlib que no dice nada
    # del problema real (visto en la practica con CESM2). Mejor un
    # error propio, claro, que decirle a xarray que adivine.
    d1 = d[varname].sel(time=slice("1950-12", "1950-12")).squeeze()
    if d1.ndim != 2:
        raise ValueError(
            f"{model} {exp}: se esperaba un campo 2D (lat, lon) para 1950-12, "
            f"se obtuvo dims={d1.dims} shape={d1.shape} -- revisar el archivo de entrada"
        )
    d1.plot.pcolormesh(ax=ax, cmap="turbo", levels=np.arange(20, 34, 1), extend="both")
    ax.set_xlabel("longitud")
    ax.set_ylabel("latitud")
    ax.set_title(f"{model} {exp.upper()}")
    pc.FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path, dpi=pc.DPI, bbox_inches="tight")
    if standalone:
        plt.close()


def main() -> None:
    models = pc.list_available_models()
    if not models:
        sys.exit(f"No hay archivos tos_*_historical.nc en {pc.MASKED_DIR} -- corre run.sh hasta el paso 05.")

    print(f"Graficando mapas: {len(models)} modelo(s) + ERSSTv5 ...", file=sys.stderr)
    n_ok, n_fail = 0, 0
    for model in models + ["ERSSTv5"]:
        print(f"  {model}", file=sys.stderr)
        try:
            plot_map(model, "historical")
            n_ok += 1
        except Exception as e:
            # Un modelo con datos raros no debe tirar abajo el resto
            # del lote (ver el chequeo de dimensionalidad en plot_map).
            print(f"  {model}: fallo ({e}), se omite y se sigue con el resto", file=sys.stderr)
            n_fail += 1
    print(f"Listo, {n_ok} figura(s) en {pc.FIGURES_DIR}"
          + (f" ({n_fail} modelo(s) fallaron, ver arriba)" if n_fail else ""), file=sys.stderr)


if __name__ == "__main__":
    main()
