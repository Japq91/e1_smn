#!/usr/bin/env python3
"""GRAFICO 4: comparacion Nino 3.4 / Nino 1+2 -- periodo historico,
modelos vs ERSSTv5. Dispersion (dsv. estandar) y mediana de SST sobre
la interseccion de anios comun a todas las fuentes. Solo el periodo
historico: los escenarios futuros no tienen contraparte observada.
Extraido de graficos_exploratorios.ipynb para poder correrlo desde
terminal sin Jupyter (ej. un cluster HPC sin interfaz grafica).

Requiere que data/processed/masked/ ya tenga archivos (correr
./run.sh hasta el paso 05 como minimo).

Uso:
    python3 scripts/plot_boxplot_comparison.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import plot_common as pc  # noqa: E402 (fuerza el backend Agg antes de pyplot)

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402


def plot_box_boxplot(box: dict, box_name: str) -> None:
    out_path = pc.FIGURES_DIR / f"boxplot_{box_name.replace(' ', '')}.png"
    if out_path.exists():
        print(f"  {box_name}: {out_path.name} ya existe, se omite", file=sys.stderr)
        return

    sources = ["ERSSTv5"] + pc.list_available_models()
    series = {}
    for src in sources:
        exp = "" if src == "ERSSTv5" else "historical"
        series[src] = pc.box_mean(src, exp, **box)

    common_years = None
    for src in sources:
        yrs = set(np.round(series[src][0]).astype(int))
        common_years = yrs if common_years is None else (common_years & yrs)
    common_years = sorted(common_years)

    data_for_box, labels = [], []
    for src in sources:
        years, values = series[src]
        yr_int = np.round(years).astype(int)
        mask = np.isin(yr_int, common_years)
        data_for_box.append(np.ma.compressed(values[mask]))
        labels.append(src)

    # Renombrar modelos a M1, M2, ... conservando solo ERSSTv5
    model_labels = [labels[0]] + [f"M{i}" for i in range(1, len(labels))]

    obs_median = np.median(data_for_box[0])
    boxprops = dict(facecolor="grey", alpha=0.5)
    medianprops = dict(color="black", linewidth=1.2)
    flierprops = dict(marker=".", alpha=0.8, markersize=4)

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.boxplot(data_for_box, tick_labels=model_labels, patch_artist=True,
               boxprops=boxprops, medianprops=medianprops, flierprops=flierprops)
    ax.axhline(y=obs_median, color="red", linewidth=0.9)

    ax.set_ylabel(f"SST {box_name} (degC)")
    ax.set_title(f"{box_name} -- periodo historico ({len(common_years)} anios comunes: "
                 f"{common_years[0]}-{common_years[-1]})")
    plt.setp(ax.get_xticklabels(), rotation=50, ha="right")

    pc.FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path, dpi=pc.DPI, bbox_inches="tight")
    plt.close()
    print(f"  {box_name}: {len(sources)} fuente(s), {len(common_years)} anios comunes -> {out_path}",
          file=sys.stderr)


def main() -> None:
    if not pc.list_available_models():
        sys.exit(f"No hay archivos tos_*_historical.nc en {pc.MASKED_DIR} -- corre run.sh hasta el paso 05.")
    if not pc.masked_path("ERSSTv5").exists():
        sys.exit(f"Falta {pc.masked_path('ERSSTv5')} -- corre run.sh hasta el paso 05.")

    print("Graficando boxplots comparativos ...", file=sys.stderr)
    plot_box_boxplot(pc.NINO34, "Nino 3.4")
    plot_box_boxplot(pc.NINO12, "Nino 1+2")
    print("Listo.", file=sys.stderr)


if __name__ == "__main__":
    main()
