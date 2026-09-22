#!/usr/bin/env python3
"""GRAFICO 1: mapas -- promedio temporal (mes 1950-12) del campo
completo, por modelo/experimento y para ERSSTv5. Extraido de
graficos_exploratorios.ipynb para poder correrlo desde terminal sin
Jupyter (ej. un cluster HPC sin interfaz grafica).

Requiere data/processed/models_inventory_final.csv (correr
./run.sh hasta el paso 07 como minimo): solo grafica modelos
selected=True.

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
from matplotlib.ticker import FuncFormatter  # noqa: E402

plt.rcParams.update({"font.size": 10})
plt.rcParams["font.family"] = "serif"
plt.rcParams["font.serif"] = ["Times New Roman"] + plt.rcParams["font.serif"]

# Mes de muestra para el mapa 2D -- unica fuente de verdad: cambiar
# solo aca para que el titulo de la figura y el dato graficado se
# actualicen juntos (antes el titulo decia "HISTORICAL" a secas, sin
# decir que mes se estaba mostrando en realidad).
SAMPLE_MONTH = "1950-12"

_DEG = FuncFormatter(lambda v, _pos: f"{v:g}°")


def plot_map(model: str, exp: str = "historical", ax=None, force: bool = False,
             model_number: str | None = None) -> None:
    out_path = pc.FIGURES_DIR / pc.sst_2d_filename(model, model_number)
    if ax is None and out_path.exists() and not force:
        print(f"  {model}: {out_path.name} ya existe, se omite", file=sys.stderr)
        return

    with nc.Dataset(pc.masked_path(model, exp)) as ds:
        varname = next(v for v in ds.variables if v not in pc.NON_DATA_NAMES)
    d = xr.open_dataset(pc.masked_path(model, exp))

    standalone = ax is None
    if standalone:
        fig, ax = plt.subplots(figsize=(12, 4))
    # .sel(...).squeeze() puede dejar dimensiones sueltas de tamano 1
    # (ej. una malla nativa con una dimension extra) -- si no queda
    # 2D (lat, lon), NO usar el dispatch generico d1.plot(...): para
    # datos ambiguos xarray a veces elige plot.hist() en vez de un
    # campo 2D, y revienta con un error de matplotlib que no dice nada
    # del problema real (visto en la practica con CESM2). Mejor un
    # error propio, claro, que decirle a xarray que adivine.
    d1 = d[varname].sel(time=slice(SAMPLE_MONTH, SAMPLE_MONTH)).squeeze()
    if d1.ndim != 2:
        raise ValueError(
            f"{model} {exp}: se esperaba un campo 2D (lat, lon) para {SAMPLE_MONTH}, "
            f"se obtuvo dims={d1.dims} shape={d1.shape} -- revisar el archivo de entrada"
        )
    im = d1.plot.pcolormesh(ax=ax, cmap="turbo", levels=np.arange(20, 34, 1), extend="both",
                             add_colorbar=False)
    cbar = plt.colorbar(im, ax=ax)
    cbar.set_label("SST (°C)")
    ax.xaxis.set_major_formatter(_DEG)
    ax.yaxis.set_major_formatter(_DEG)
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    # Titulo con el mes de muestra exacto (SAMPLE_MONTH), no solo el
    # nombre del experimento -- asi queda claro que dato puntual se
    # esta mostrando, y cambiar SAMPLE_MONTH arriba lo actualiza solo.
    ax.set_title(f"{model} – {SAMPLE_MONTH}")
    # Codigo M001..M102 (informe/model_registry.csv) como titulo
    # aparte, alineado a la izquierda -- identifica el modelo sin
    # competir con el titulo centrado de arriba. ERSSTv5 (el dato
    # observado, no uno de los 102 modelos CMIP6) no tiene codigo.
    if model_number:
        ax.set_title(model_number, loc="left", fontsize=9, fontweight="bold")
    pc.FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path, dpi=pc.DPI, bbox_inches="tight")
    if standalone:
        plt.close()


def main() -> None:
    models = pc.selected_models()
    if not models:
        sys.exit(f"Ningun modelo selected=True en {pc.INVENTORY_CSV} -- corre run.sh hasta el paso 07.")

    targets = models + ["ERSSTv5"]
    numbers = pc.model_numbers()
    existing = [pc.FIGURES_DIR / pc.sst_2d_filename(m, numbers.get(m)) for m in targets
                if (pc.FIGURES_DIR / pc.sst_2d_filename(m, numbers.get(m))).exists()]
    force = pc.should_regenerate_batch(existing, kind="mapa(s) 2D") if existing else False

    print(f"Graficando mapas: {len(models)} modelo(s) + ERSSTv5 ...", file=sys.stderr)
    n_ok, n_fail = 0, 0
    for model in targets:
        print(f"  {model}", file=sys.stderr)
        try:
            plot_map(model, "historical", force=force, model_number=numbers.get(model))
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
