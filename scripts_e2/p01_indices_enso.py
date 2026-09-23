#!/usr/bin/env python3
"""Paso (1.) del calculo de E2: series por caja -> ONI/RONI (Nino3.4)
e ICEN (Nino1+2), para los 40 modelos de model_registry_e2.csv.

Ejecutable de forma independiente (no depende de que otro pXX haya
corrido antes): lee directamente data/processed/masked/ y
data/processed/e2/model_registry_e2.csv.

Uso:
    python3 scripts_e2/p01_indices_enso.py
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common_e2 as c2

# Periodo de referencia para la climatologia de las anomalias -- EDITAR
# ACA para cambiarlo; el nombre del archivo de salida se arma solo a
# partir de estos dos valores, no hace falta tocarlo aparte.
REF_INICIO = 1981
REF_FIN = 2014


def indices_for(series, name_prefix):
    clim = {k: c2.climatology(v, REF_INICIO, REF_FIN) for k, v in series.items()}
    oni = c2.oni_index(series["nino34"], clim["nino34"])
    roni = c2.roni_index(oni, series["tropical"], clim["tropical"])
    icen = c2.icen_index(series["nino12"], clim["nino12"])
    return pd.DataFrame({
        f"{name_prefix}_ONI": oni.to_pandas(),
        f"{name_prefix}_RONI": roni.to_pandas(),
        f"{name_prefix}_ICEN": icen.to_pandas(),
    })


def main():
    registry = c2.read_model_registry()

    frames = []
    for row in registry:
        number, model = row["number"], row["model"]
        print(f"  {number} {model} ...", file=sys.stderr)
        series = {
            k: c2.box_series(c2.model_path(model), box, "tos", weighted=c2.WEIGHTED[k])
            for k, box in c2.BOXES.items()
        }
        frames.append(indices_for(series, number))

    result = pd.concat(frames, axis=1)
    result.index.name = "time"
    result = result.sort_index()

    # Ventana comun a los 40 modelos: algunos (ej. IITM-ESM) publican
    # 'historical' recien desde 1900, no 1850 -- se recorta al periodo
    # donde TODOS tienen dato valido (ver data/processed/e2/README.md).
    # El limite se calcula del propio resultado, no se hardcodea.
    oni_cols = [c for c in result.columns if c.endswith("_ONI")]
    common_start = max(result[c].dropna().index.min() for c in oni_cols)
    common_end = min(result[c].dropna().index.max() for c in oni_cols)
    result = result.loc[common_start:common_end]

    y0, y1 = common_start.year, common_end.year
    out_path = c2.E2_DIR / f"indices_enso_{y0}-{y1}_ref{REF_INICIO}-{REF_FIN}.csv"
    result.to_csv(out_path, float_format="%.4f")
    print(f"Ventana comun a los 40 modelos: {common_start.date()} a {common_end.date()}", file=sys.stderr)
    print(f"Listo: {out_path} ({result.shape[0]} filas, {result.shape[1]} columnas)", file=sys.stderr)


if __name__ == "__main__":
    main()
