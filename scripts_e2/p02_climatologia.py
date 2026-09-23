#!/usr/bin/env python3
"""Paso (2.) del calculo de E2: climatologia y ciclo anual, por caja,
para los 40 modelos de model_registry_e2.csv.

Ejecutable de forma independiente (no depende de que otro pXX haya
corrido antes): lee directamente data/processed/masked/ y
data/processed/e2/model_registry_e2.csv.

Salida: 2 archivos (uno por caja -- Nino3.4, Nino1+2), filas = modelos
(number M01..M40), columnas = mes 1..12 (C_m en grados C).

Uso:
    python3 scripts_e2/p02_climatologia.py
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common_e2 as c2

# Periodo de referencia de la climatologia -- EDITAR ACA para
# cambiarlo; el nombre del archivo de salida se arma solo a partir de
# estos dos valores. Independiente del REF_INICIO/REF_FIN de otros
# pXX -- cambiar este no afecta a p01_indices_enso.py ni viceversa.
REF_INICIO = 1981
REF_FIN = 2014


def climatologia_por_caja(box_key):
    registry = c2.read_model_registry()
    box = c2.BOXES[box_key]
    weighted = c2.WEIGHTED[box_key]

    rows = {}
    for row in registry:
        number, model = row["number"], row["model"]
        print(f"  [{box_key}] {number} {model} ...", file=sys.stderr)
        serie = c2.box_series(c2.model_path(model), box, "tos", weighted=weighted)
        clim = c2.climatology(serie, REF_INICIO, REF_FIN)
        rows[number] = clim.to_pandas()

    df = pd.DataFrame(rows).T  # filas = number, columnas = mes 1..12
    df.index.name = "number"
    df.columns.name = None
    return df.sort_index()


def main():
    for box_key, box_label in [("nino34", "nino34"), ("nino12", "nino12")]:
        df = climatologia_por_caja(box_key)
        out_path = c2.E2_DIR / f"climatologia_{box_label}_{REF_INICIO}-{REF_FIN}.csv"
        df.to_csv(out_path, float_format="%.4f")
        print(f"Listo: {out_path} ({df.shape[0]} filas, {df.shape[1]} columnas)", file=sys.stderr)


if __name__ == "__main__":
    main()
