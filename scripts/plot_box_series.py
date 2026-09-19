#!/usr/bin/env python3
"""GRAFICO 2: series de caja (Nino 3.4 / Nino 1+2) -- un panel por
modelo, con historical + cada escenario SSP configurado superpuestos
en el mismo eje. El promedio de caja se calcula en el momento, no hace
falta que el pipeline lo deje precalculado en disco. Extraido de
graficos_exploratorios.ipynb para poder correrlo desde terminal sin
Jupyter (ej. un cluster HPC sin interfaz grafica).

Requiere que data/processed/masked/ ya tenga archivos (correr
./run.sh hasta el paso 05 como minimo).

Uso:
    python3 scripts/plot_box_series.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import plot_common as pc  # noqa: E402 (fuerza el backend Agg antes de pyplot)

import matplotlib.pyplot as plt  # noqa: E402


def plot_box_series(model: str, box: dict, box_name: str, ax=None) -> None:
    """Serie de caja del modelo con historical + cada escenario SSP
    configurado (config/periods.yaml) superpuestos en el mismo eje."""
    ofile = pc.FIGURES_DIR / f"serie_{model}_sst_{box_name.replace(' ', '')}.png"
    standalone = ax is None
    if standalone and ofile.exists():
        print(f"  {model} {box_name}: {ofile.name} ya existe, se omite", file=sys.stderr)
        return
    if standalone:
        fig, ax = plt.subplots(figsize=(9, 3))

    for exp, estilo in pc.scenario_styles().items():
        if not os.path.exists(pc.masked_path(model, exp)):
            continue
        years, values = pc.box_mean(model, exp, **box)
        ax.plot(years, values, label=exp, **estilo)

    ax.set_xlabel("anio")
    ax.set_ylabel("SST (degC)")
    ax.set_title(f"{box_name} -- {model}")
    ax.legend()
    pc.FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    plt.savefig(ofile, dpi=pc.DPI, bbox_inches="tight")
    if standalone:
        plt.close()


def main() -> None:
    models = pc.list_available_models()
    if not models:
        sys.exit(f"No hay archivos tos_*_historical.nc en {pc.MASKED_DIR} -- corre run.sh hasta el paso 05.")

    n_done = 0
    for model in models:
        if not any(os.path.exists(pc.masked_path(model, s)) for s in pc.SCENARIOS):
            print(f"{model}: no tiene escenarios SSP descargados, se omite", file=sys.stderr)
            continue
        print(f"{model}", file=sys.stderr)
        plot_box_series(model, pc.NINO12, "Nino 1+2")
        plot_box_series(model, pc.NINO34, "Nino 3.4")
        n_done += 1

    print(f"Listo, {n_done} modelo(s) graficado(s) (2 figuras cada uno) en {pc.FIGURES_DIR}", file=sys.stderr)


if __name__ == "__main__":
    main()
