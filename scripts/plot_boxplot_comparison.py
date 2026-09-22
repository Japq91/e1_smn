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

import matplotlib.colors as mcolors  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

plt.rcParams.update({"font.size": 10})
plt.rcParams["font.family"] = "serif"
plt.rcParams["font.serif"] = ["Times New Roman"] + plt.rcParams["font.serif"]
def plot_box_boxplot(box: dict, box_name: str, force: bool = False) -> None:
    out_path = pc.FIGURES_DIR / f"boxplot_{box_name.replace(' ', '')}.png"
    if out_path.exists() and not force:
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

    # Nombres reales de modelo en el eje (no M1, M2, ...) -- version
    # anterior de este mismo grafico (encontrada por el usuario en
    # figures/boxplot_3.4.png, de una version mas vieja del notebook
    # que ya no existe en el repo).
    model_labels = labels

    # Color de cada caja segun el sesgo de su mediana respecto a la
    # mediana observada (ERSSTv5): mapa divergente rojo-azul,
    # normalizado simetricamente alrededor de sesgo=0 -- mas rojo cuanto
    # mas caliente que lo observado, mas azul cuanto mas frio. ERSSTv5
    # tiene sesgo 0 consigo misma, sale neutro (blanco/rosado palido).
    medians = [np.median(d) for d in data_for_box]
    obs_median = medians[0]
    biases = [m - obs_median for m in medians]
    max_abs_bias = max((abs(b) for b in biases), default=1.0) or 1.0
    norm = mcolors.TwoSlopeNorm(vmin=-max_abs_bias, vcenter=0.0, vmax=max_abs_bias)
    cmap = plt.get_cmap("RdBu_r")
    box_colors = [cmap(norm(b)) for b in biases]

    medianprops = dict(color="black", linewidth=1.2)
    flierprops = dict(marker="x", color="gray", alpha=0.6, markersize=4)

    fig, ax = plt.subplots(figsize=(12, 3))
    bp = ax.boxplot(data_for_box, tick_labels=model_labels, patch_artist=True,
                     medianprops=medianprops, flierprops=flierprops)
    for patch, color in zip(bp["boxes"], box_colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.85)
    ax.axhline(y=obs_median, color="red", linewidth=0.9, linestyle="--")

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

    boxes = [(pc.NINO34, "Nino 3.4"), (pc.NINO12, "Nino 1+2")]
    existing = [pc.FIGURES_DIR / f"boxplot_{name.replace(' ', '')}.png" for _, name in boxes
                if (pc.FIGURES_DIR / f"boxplot_{name.replace(' ', '')}.png").exists()]
    force = pc.should_regenerate_batch(existing, kind="boxplot(s) comparativo(s)") if existing else False

    print("Graficando boxplots comparativos ...", file=sys.stderr)
    for box, name in boxes:
        plot_box_boxplot(box, name, force=force)
    print("Listo.", file=sys.stderr)


if __name__ == "__main__":
    main()
