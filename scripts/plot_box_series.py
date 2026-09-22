#!/usr/bin/env python3
"""GRAFICO 2: series de caja (Nino 3.4 / Nino 1+2) -- un panel por
modelo, con historical + cada escenario SSP configurado superpuestos
en el mismo eje. El promedio de caja se calcula en el momento, no hace
falta que el pipeline lo deje precalculado en disco. Extraido de
graficos_exploratorios.ipynb para poder correrlo desde terminal sin
Jupyter (ej. un cluster HPC sin interfaz grafica).

Requiere data/processed/models_inventory_final.csv (correr
./run.sh hasta el paso 07 como minimo): solo grafica modelos
selected=True.

Uso:
    python3 scripts/plot_box_series.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import plot_common as pc  # noqa: E402 (fuerza el backend Agg antes de pyplot)

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.ticker import MaxNLocator  # noqa: E402

plt.rcParams.update({"font.size": 10})
plt.rcParams["font.family"] = "serif"
plt.rcParams["font.serif"] = ["Times New Roman"] + plt.rcParams["font.serif"]


def _historical_medians(model: str, box: dict) -> tuple[float, float] | None:
    """(mediana_ERSSTv5, mediana_modelo) sobre el periodo historico
    comun a ambos (misma logica que plot_boxplot_comparison.py, pero
    pairwise contra un solo modelo en vez de exigir interseccion entre
    los 40 a la vez) -- None si ERSSTv5 o el historical de este modelo
    no estan disponibles."""
    if not os.path.exists(pc.masked_path("ERSSTv5")) or not os.path.exists(pc.masked_path(model, "historical")):
        return None
    obs_years, obs_values = pc.box_mean("ERSSTv5", "", **box)
    hist_years, hist_values = pc.box_mean(model, "historical", **box)
    obs_yr = np.round(obs_years).astype(int)
    hist_yr = np.round(hist_years).astype(int)
    common = np.intersect1d(obs_yr, hist_yr)
    if common.size == 0:
        return None
    # np.ma.compressed() antes de la mediana (no np.median directo):
    # box_mean devuelve un MaskedArray, y np.median ignora la mascara
    # en vez de excluir esos puntos (mismo criterio que
    # plot_boxplot_comparison.py).
    obs_median = float(np.median(np.ma.compressed(obs_values[np.isin(obs_yr, common)])))
    hist_median = float(np.median(np.ma.compressed(hist_values[np.isin(hist_yr, common)])))
    return obs_median, hist_median


def plot_box_series(model: str, box: dict, box_name: str, ax=None, force: bool = False,
                     model_number: str | None = None) -> None:
    """Serie de caja del modelo con historical + cada escenario SSP
    configurado (config/periods.yaml) superpuestos en el mismo eje."""
    ofile = pc.FIGURES_DIR / pc.series_filename(model, box_name, model_number)
    standalone = ax is None
    if standalone and ofile.exists() and not force:
        print(f"  {model} {box_name}: {ofile.name} ya existe, se omite", file=sys.stderr)
        return
    if standalone:
        fig, ax = plt.subplots(figsize=(12, 3))

    for exp, estilo in pc.scenario_styles().items():
        if not os.path.exists(pc.masked_path(model, exp)):
            continue
        years, values = pc.box_mean(model, exp, **box)
        ax.plot(years, values, label=exp, linewidth=0.4, marker=".", markersize=1.8, **estilo)

    # Dos lineas horizontales de referencia, sobre el mismo periodo
    # historico comun que usa plot_boxplot_comparison.py: la mediana
    # observada (ERSSTv5) y la mediana historica de este modelo -- para
    # ver de un vistazo el sesgo del modelo respecto a lo observado.
    medians = _historical_medians(model, box)
    if medians is not None:
        obs_median, hist_median = medians
        ax.axhline(obs_median, color="red", linewidth=0.9, linestyle="--",
                    label=f"ERSSTv5 median ({obs_median:.1f}°C)")
        ax.axhline(hist_median, color="black", linewidth=0.9, linestyle=":",
                    label=f"Historical median ({hist_median:.1f}°C)")

    display_name = box_name.replace("Nino", "Niño")
    ax.set_ylim(19, 35)
    ax.yaxis.set_major_locator(MaxNLocator(integer=True))
    ax.set_xlabel("Year")
    ax.set_ylabel("SST (°C)")
    ax.set_title(f"{display_name} – {model}")
    # Codigo M001..M102 como titulo aparte a la izquierda -- mismo
    # criterio que plot_maps.py (informe/model_registry.csv). ERSSTv5
    # no tiene codigo (no es de los 102 modelos CMIP6), pero tampoco
    # pasa por aca (esta funcion solo grafica modelos, no el observado).
    if model_number:
        ax.set_title(model_number, loc="left", fontsize=9, fontweight="bold")
    ax.legend(loc="upper left", ncol=2, frameon=False, fontsize=8)
    pc.FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    plt.savefig(ofile, dpi=pc.DPI, bbox_inches="tight")
    if standalone:
        plt.close()


BOXES = [(pc.NINO12, "Nino 1+2"), (pc.NINO34, "Nino 3.4")]


def main() -> None:
    models = pc.selected_models()
    if not models:
        sys.exit(f"Ningun modelo selected=True en {pc.INVENTORY_CSV} -- corre run.sh hasta el paso 07.")

    numbers = pc.model_numbers()
    existing = [pc.FIGURES_DIR / pc.series_filename(m, box_name, numbers.get(m))
                for m in models for _, box_name in BOXES
                if (pc.FIGURES_DIR / pc.series_filename(m, box_name, numbers.get(m))).exists()]
    force = pc.should_regenerate_batch(existing, kind="serie(s) de caja") if existing else False

    n_done = 0
    for model in models:
        print(f"{model}", file=sys.stderr)
        for box, box_name in BOXES:
            plot_box_series(model, box, box_name, force=force, model_number=numbers.get(model))
        n_done += 1

    print(f"Listo, {n_done} modelo(s) graficado(s) (2 figuras cada uno) en {pc.FIGURES_DIR}", file=sys.stderr)


if __name__ == "__main__":
    main()
