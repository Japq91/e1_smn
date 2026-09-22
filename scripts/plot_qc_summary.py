#!/usr/bin/env python3
"""GRAFICO 3: resumen de control de calidad -- matriz PASS/FAIL/PENDIENTE/
SIN_LINK/UNAVAILABLE (mas el caso especial SOLO_HIST1950) por modelo y
experimento, a partir de
data/processed/qc_report.csv (paso 06), la disponibilidad real que
escribe el paso 00b (informe/model_availability_priority.csv) y el
contenido de data/raw/cmip6/ (para distinguir "nunca se descargo" de
"se descargo pero no llego al QC"). Extraido de
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
    if out_path.exists() and not pc.should_regenerate_batch([out_path]):
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

    # data/interim/models_catalog_status.csv (paso 01): dice, por
    # modelo/experimento, si se encontro un link de descarga real que
    # respondio (no solo si el experimento existe segun 00b -- eso es
    # informe/model_availability_priority.csv, una capa mas superficial).
    catalog_df = None
    if pc.CATALOG_CSV.exists():
        catalog_df = pd.read_csv(pc.CATALOG_CSV, dtype=str).set_index("model")

    avail_by_model = avail_df.set_index("model")

    def link_found(model: str, exp: str) -> bool:
        if catalog_df is None or model not in catalog_df.index or exp not in catalog_df.columns:
            return False
        return catalog_df.loc[model, exp] == "True"

    # Estado final honesto, en 6 niveles:
    #  - fila en el CSV -> PASS o FAIL (QC/CDO sobre un archivo ya descargado)
    #  - sin fila, pero 01 encontro un link que respondio -> PENDIENTE
    #    (ya sea que falte descargar o que falte procesar/QC -- ambos
    #    casos son "en camino a ser PASS", no hace falta distinguirlos
    #    visualmente)
    #  - columna 'historical' especificamente, cuando lo unico que hay
    #    es hist-1950 (HighResMIP) -- el modelo nunca llega a 01 (no
    #    tiene SSP, no califica como seed) asi que nunca se busco un
    #    link de 'historical' en si -> SOLO_HIST1950 (distinto de
    #    SIN_LINK: aca no se busco y fallo, directamente no aplica)
    #  - sin fila, el experimento existe segun 00b pero 01 NO encontro
    #    un link que funcione -> SIN_LINK (existe el dato en alguna
    #    parte, pero no lo pudimos ubicar nosotros)
    #  - el experimento no existe en absoluto segun 00b -> UNAVAILABLE
    final_status = status_matrix.copy()
    pendientes = {"PENDIENTE": [], "SIN_LINK": []}
    for model in all_models:
        for exp in experiments:
            if final_status.loc[model, exp] != "":
                continue
            if exp not in availability[model]:
                final_status.loc[model, exp] = "UNAVAILABLE"
            elif link_found(model, exp):
                final_status.loc[model, exp] = "PENDIENTE"
                pendientes["PENDIENTE"].append((model, exp))
            elif exp == "historical" and avail_by_model.loc[model, "cual_historical"] == "hist-1950":
                final_status.loc[model, exp] = "SOLO_HIST1950"
            else:
                final_status.loc[model, exp] = "SIN_LINK"
                pendientes["SIN_LINK"].append((model, exp))

    # 'tos' es la unica columna aparte de los experimentos -- tiene_tos
    # tal cual (en la practica casi siempre 1, ver
    # informe/model_availability_priority.csv). La distincion
    # historical/hist-1950 ya no es una columna aparte: queda fundida
    # en el estado SOLO_HIST1950 de la columna 'historical' (ver arriba).
    tos_available = {
        model: ("TOS_YES" if avail_by_model.loc[model, "tiene_tos"] == "1" else "TOS_NO")
        for model in all_models
    }

    # Orden alfabetico simple (no por PASS/disponibilidad) -- asi el
    # numero M001..M102 que se muestra en el eje queda en secuencia,
    # sin saltos. El cruce numero <-> nombre real de modelo queda en
    # informe/model_registry.csv (build_model_registry.py, misma
    # numeracion: alfabetico sobre el mismo universo de 102 modelos).
    model_order = sorted(all_models)
    width = max(3, len(str(len(model_order))))
    model_number = {m: f"M{i:0{width}d}" for i, m in enumerate(model_order, start=1)}

    panel_size = int(np.ceil(len(model_order) / n_panels))
    panels = [model_order[i * panel_size: (i + 1) * panel_size] for i in range(n_panels)]

    # Logica de forma/relleno/color, consistente en las 5 columnas:
    #   circulo  = hay (o puede haber) un archivo real de por medio --
    #              relleno = confirmado (ya paso QC); hueco = pendiente
    #   cuadrado = no existe estructuralmente (siempre rojo)
    #   X        = existe y se descargo, pero fallo el QC (siempre rojo)
    # Color dentro de la familia "circulo": verde = buen camino (hay
    # link vivo), gris = camino trabado (existe pero no encontramos
    # ningun link que funcione).
    color_map = {
        "PASS": "tab:green", "FAIL": "tab:red", "PENDIENTE": "tab:green",
        "SIN_LINK": "gray", "SOLO_HIST1950": "tab:orange", "UNAVAILABLE": "tab:red",
        "TOS_YES": "tab:green", "TOS_NO": "tab:red",
    }
    marker_map = {
        "PASS": "o", "FAIL": "X", "PENDIENTE": "o",
        "SIN_LINK": "o", "SOLO_HIST1950": "o", "UNAVAILABLE": "s",
        "TOS_YES": "o", "TOS_NO": "s",
    }
    size_map = {
        "PASS": 30, "FAIL": 30, "PENDIENTE": 30,
        "SIN_LINK": 30, "SOLO_HIST1950": 30, "UNAVAILABLE": 22,
        "TOS_YES": 30, "TOS_NO": 22,
    }
    # PENDIENTE (verde), SIN_LINK (gris) y SOLO_HIST1950 (naranja) van
    # huecos -- todavia no se confirmaron con un PASS real. PASS es el
    # unico circulo relleno.
    HOLLOW = {"PENDIENTE", "SIN_LINK", "SOLO_HIST1950"}

    fig, axes = plt.subplots(1, n_panels, figsize=(n_panels * 2.4, panel_size * 0.12 + .4),
                              sharey=False, gridspec_kw={"wspace": 1.4, "hspace": 0.2})
    for idx, ax in enumerate(axes):
        chunk = panels[idx]
        for i, model in enumerate(chunk):
            tos_status = tos_available[model]
            ax.scatter(0, i, marker=marker_map[tos_status], s=size_map[tos_status],
                       c=color_map[tos_status],
                       edgecolors="none" if tos_status != "TOS_NO" else "white",
                       linewidth=0.5, alpha=0.9)
            for j, exp in enumerate(experiments):
                status = final_status.loc[model, exp]
                col = j + 1
                if status in HOLLOW:
                    ax.scatter(col, i, marker=marker_map[status], s=size_map[status],
                               facecolors="none", edgecolors=color_map[status],
                               linewidth=0.8, alpha=0.9)
                else:
                    ax.scatter(col, i, marker=marker_map[status], s=size_map[status],
                               c=color_map[status],
                               edgecolors="none" if status != "UNAVAILABLE" else "white",
                               linewidth=0.5, alpha=0.9)

        all_cols = ["tos"] + experiments
        ax.set_xticks(range(len(all_cols)))
        ax.set_xticklabels(all_cols, rotation=45, ha="left", fontsize=8)
        ax.set_yticks(range(len(chunk)))
        ax.set_yticklabels([f"{m} [{model_number[m]}]" for m in chunk], fontsize=6.5)
        ax.set_ylim(-0.5, len(chunk) - 0.5)
        ax.invert_yaxis()
        ax.set_xlim(-0.6, len(all_cols) - 1 + 0.6)
        ax.xaxis.tick_top()
        ax.tick_params(axis="y", length=0)
        ax.grid(axis="x", linewidth=0.5, alpha=0.3)

    from matplotlib.lines import Line2D
    legend_elements = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor="tab:green",
               markersize=8, label="PASS"),
        Line2D([0], [0], marker="X", color="w", markerfacecolor="tab:red",
               markersize=8, label="FAIL (QC/CDO, sobre archivo descargado)"),
        Line2D([0], [0], marker="o", color="tab:green", markerfacecolor="none",
               markersize=8, label="Link vivo encontrado, falta descargar y/o procesar"),
        Line2D([0], [0], marker="o", color="gray", markerfacecolor="none",
               markersize=8, label="Existe segun 00b, pero 01 no encontro ningun link vivo"),
        Line2D([0], [0], marker="o", color="tab:orange", markerfacecolor="none",
               markersize=8, label="Columna 'historical': solo tiene hist-1950 (HighResMIP), "
                                   "no se busco link (no califica como seed)"),
        Line2D([0], [0], marker="s", color="w", markerfacecolor="tab:red",
               markersize=8, label="No existe en absoluto (columna 'tos') / sin ese "
                                   "experimento en ningun lado (columnas historical/SSP)"),
    ]
    fig.legend(handles=legend_elements, ncol=2, frameon=False, fontsize=8,
               loc="upper center", bbox_to_anchor=(0.5, .1))

    pc.FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path, dpi=pc.DPI, bbox_inches="tight")
    plt.close()

    if pendientes["PENDIENTE"]:
        print(f"\n{len(pendientes['PENDIENTE'])} caso(s) PENDIENTE (link vivo encontrado, "
              "falta descargar y/o procesar):", file=sys.stderr)
        for model, exp in pendientes["PENDIENTE"]:
            print(f"   - {model} / {exp}", file=sys.stderr)
    if pendientes["SIN_LINK"]:
        print(f"\n{len(pendientes['SIN_LINK'])} caso(s) SIN_LINK (existe segun 00b, pero 01 "
              "no encontro ningun link vivo):", file=sys.stderr)
        for model, exp in pendientes["SIN_LINK"]:
            print(f"   - {model} / {exp}", file=sys.stderr)

    print(f"\nListo: {len(df)} filas de QC procesadas, figura en {out_path}", file=sys.stderr)


if __name__ == "__main__":
    n_panels_arg = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    plot_qc_summary(n_panels=n_panels_arg)
