#!/usr/bin/env python3
"""GRAFICO 3: resumen de control de calidad -- matriz PASS/FAIL/no
disponible por modelo y experimento, a partir de data/processed/qc_report.csv
(paso 06) y la disponibilidad real que escribe el paso 00b
(informe/model_availability_report.csv). Extraido de
graficos_exploratorios.ipynb para poder correrlo desde terminal sin
Jupyter (ej. un cluster HPC sin interfaz grafica).

Uso:
    python3 scripts/plot_qc_summary.py [n_paneles]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import plot_common as pc  # noqa: E402 (fuerza el backend Agg antes de pyplot)

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402


def plot_qc_summary(n_panels: int = 4) -> None:
    out_path = pc.FIGURES_DIR / "sst_QD_vf.png"
    if out_path.exists():
        print(f"{out_path.name} ya existe, se omite. Para regenerarlo (ej. tras una nueva "
              "descarga/QC), borralo primero.", file=sys.stderr)
        return

    if not pc.QC_CSV.exists():
        sys.exit(f"Falta {pc.QC_CSV}. Se genera con run.sh (paso 06).")
    if not pc.MODEL_AVAILABILITY_CSV.exists():
        sys.exit(
            f"Falta {pc.MODEL_AVAILABILITY_CSV}. Se genera al correr el paso 00b "
            "de run.sh, o a mano con: "
            "python3 scripts/00b_build_model_list.py config/models_seed_cmip6.csv"
        )

    df = pd.read_csv(pc.QC_CSV)
    df["status_simple"] = df["status"].replace({"ERROR_CDO": "FAIL"})

    avail_df = pd.read_csv(pc.MODEL_AVAILABILITY_CSV, dtype=str)

    def avail_col(exp: str) -> str:
        return "tiene_hist" if exp == "historical" else f"tiene_{exp}"

    experiments = [e for e in pc.EXPERIMENTS if avail_col(e) in avail_df.columns]
    missing_cols = [e for e in pc.EXPERIMENTS if avail_col(e) not in avail_df.columns]
    if missing_cols:
        print(f"AVISO: {pc.MODEL_AVAILABILITY_CSV.name} no tiene columna(s) para {missing_cols} "
              "-- regeneralo (borrar y correr de nuevo el paso 00b) para incluir "
              "los escenarios SSP mas recientes de config/periods.yaml", file=sys.stderr)

    # 'historical'/'hist' aca es solo si tiene el experimento que este
    # pipeline usa (historical o hist-1950) -- ver
    # pipeline_config.has_historical. NO es lo mismo que "tiene tos":
    # todos los modelos de este CSV tienen tos/Omon publicado en algun
    # lado (ver columna tiene_tos y experimentos_encontrados), solo que
    # algunos lo tienen bajo experimentos que este pipeline no usa
    # (omip, PMIP, DCPP, HighResMIP sin hist-1950, etc.).
    availability = {
        row["model"]: {exp for exp in experiments if row[avail_col(exp)] == "1"}
        for _, row in avail_df.iterrows()
    }
    all_models = sorted(availability)

    # Matriz de QC
    status_matrix = pd.DataFrame(index=all_models, columns=experiments, data="")
    for _, row in df.iterrows():
        model = row["model"]
        exp = row["experiment"]
        if model in status_matrix.index and exp in experiments:
            status_matrix.loc[model, exp] = row["status_simple"]

    # Estado final honesto:
    #  - fila en el CSV -> PASS o FAIL (fallo QC/CDO sobre un archivo que si se bajo)
    #  - catalogo dice que existe pero sin fila en el CSV -> FAIL_DESCARGA
    #  - catalogo dice que no existe -> UNAVAILABLE
    final_status = status_matrix.copy()
    missing_download = []
    for model in all_models:
        for exp in experiments:
            if final_status.loc[model, exp] == "":
                if exp in availability[model]:
                    final_status.loc[model, exp] = "FAIL_DESCARGA"
                    missing_download.append((model, exp))
                else:
                    final_status.loc[model, exp] = "UNAVAILABLE"

    # OJO: esto es "tiene historical o hist-1950" (lo que este pipeline
    # puede usar), NO "tiene tos en algun lado" -- todos los modelos de
    # informe/model_availability_priority.csv tienen tos publicado en
    # algun experimento (ver columna tiene_tos, siempre 1 en la
    # practica), solo que algunos lo tienen bajo protocolos que este
    # pipeline no usa (omip, PMIP, DCPP, etc.) -- antes esta figura
    # llamaba a eso "TOS_NO", lo cual era enganoso (bug real,
    # encontrado por el usuario).
    hist_available = {
        model: ("HIST_YES" if "historical" in availability[model] else "HIST_NO")
        for model in all_models
    }

    model_order = sorted(
        all_models,
        key=lambda m: (
            -(1 if hist_available[m] == "HIST_YES" else 0),
            -sum(final_status.loc[m, e] == "PASS" for e in experiments),
            m,
        ),
    )

    panel_size = int(np.ceil(len(model_order) / n_panels))
    panels = [model_order[i * panel_size: (i + 1) * panel_size] for i in range(n_panels)]

    color_map = {
        "PASS": "tab:green", "FAIL": "tab:red", "FAIL_DESCARGA": "darkred",
        "UNAVAILABLE": "lightgrey", "HIST_YES": "tab:green", "HIST_NO": "lightgrey",
    }
    marker_map = {
        "PASS": "o", "FAIL": "X", "FAIL_DESCARGA": "v",
        "UNAVAILABLE": "s", "HIST_YES": "o", "HIST_NO": "s",
    }
    size_map = {
        "PASS": 30, "FAIL": 30, "FAIL_DESCARGA": 30,
        "UNAVAILABLE": 15, "HIST_YES": 30, "HIST_NO": 15,
    }

    fig, axes = plt.subplots(1, n_panels, figsize=(n_panels * 2.4, panel_size * 0.12 + .4),
                              sharey=False, gridspec_kw={"wspace": 1.4, "hspace": 0.2})
    for idx, ax in enumerate(axes):
        chunk = panels[idx]
        for i, model in enumerate(chunk):
            hist_status = hist_available[model]
            ax.scatter(0, i, marker=marker_map[hist_status], s=size_map[hist_status],
                       c=color_map[hist_status],
                       edgecolors="none" if hist_status != "HIST_NO" else "white",
                       linewidth=0.5, alpha=0.9)
            for j, exp in enumerate(experiments):
                status = final_status.loc[model, exp]
                col = j + 1
                ax.scatter(col, i, marker=marker_map[status], s=size_map[status],
                           c=color_map[status],
                           edgecolors="none" if status != "UNAVAILABLE" else "white",
                           linewidth=0.5, alpha=0.9)

        all_cols = ["hist"] + experiments
        ax.set_xticks(range(len(all_cols)))
        ax.set_xticklabels(all_cols, rotation=45, ha="left", fontsize=8)
        ax.set_yticks(range(len(chunk)))
        ax.set_yticklabels(chunk, fontsize=6.5)
        ax.set_ylim(-0.5, len(chunk) - 0.5)
        ax.invert_yaxis()
        ax.set_xlim(-0.6, len(all_cols) - 1 + 0.6)
        ax.xaxis.tick_top()
        ax.tick_params(axis="y", length=0)
        ax.grid(axis="x", linewidth=0.5, alpha=0.3)

    from matplotlib.lines import Line2D
    legend_elements = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor="tab:green",
               markersize=8, label="PASS / historical o hist-1950 disponible"),
        Line2D([0], [0], marker="X", color="w", markerfacecolor="tab:red",
               markersize=8, label="FAIL (QC/CDO, sobre archivo descargado)"),
        Line2D([0], [0], marker="v", color="w", markerfacecolor="darkred",
               markersize=8, label="FAIL descarga (nunca se obtuvo el archivo)"),
        Line2D([0], [0], marker="s", color="w", markerfacecolor="lightgrey",
               markersize=8, label="Columna 'hist': sin historical/hist-1950 -- "
                                   "columnas SSP: sin ese escenario (puede igual tener tos, ver CSV)"),
    ]
    fig.legend(handles=legend_elements, ncol=2, frameon=False, fontsize=8,
               loc="upper center", bbox_to_anchor=(0.5, .1))

    pc.FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path, dpi=pc.DPI, bbox_inches="tight")
    plt.close()

    if missing_download:
        print(f"\n{len(missing_download)} caso(s) marcados como FAIL_DESCARGA "
              "(catalogo dice disponible, sin fila en qc_report.csv):", file=sys.stderr)
        for model, exp in missing_download:
            print(f"   - {model} / {exp}", file=sys.stderr)

    print(f"\nListo: {len(df)} filas de QC procesadas, figura en {out_path}", file=sys.stderr)


if __name__ == "__main__":
    n_panels_arg = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    plot_qc_summary(n_panels=n_panels_arg)
