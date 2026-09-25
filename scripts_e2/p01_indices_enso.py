#!/usr/bin/env python3
"""Paso (1.) del calculo de E2: series por caja -> ONI/RONI (Nino3.4)
e ICEN (Nino1+2), para los 40 modelos de model_registry_e2.csv.
Ejecutable de forma independiente (no depende de que otro pXX haya
corrido antes): lee directamente data/processed/masked/ y
data/processed/e2/model_registry_e2.csv.
Uso: python3 scripts_e2/p01_indices_enso.py
"""
import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
import common_e2 as c2

# Periodo de referencia para la climatologia de las anomalias -- EDITAR
# ACA para cambiarlo; el nombre del archivo de salida se arma solo a
# partir de estos dos valores, no hace falta tocarlo aparte.
def indices_for(series, name_prefix):    
    oni = c2.oni_index(series["nino34"])
    roni = c2.roni_index(oni, series["tropical"])
    icen = c2.icen_index(series["nino12"])
    return pd.DataFrame({
        f"{name_prefix}_ONI": oni.to_pandas(),
        f"{name_prefix}_RONI": roni.to_pandas(),
        f"{name_prefix}_ICEN": icen.to_pandas(),
    })

def main():
    registry = c2.read_model_registry()
    # Dict numero -> nombre, para mensajes de error legibles
    num2name = {row["number"]: row["model"] for row in registry}
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
    # CAMBIO 1: ventana comun calculada sobre los TRES indices
    # (ONI/RONI/ICEN), no solo ONI -- si un modelo tiene huecos en la
    # serie tropical, su RONI puede tener NaN donde el ONI es valido.
    all_idx_cols = [c for c in result.columns if c.endswith(("_ONI", "_RONI", "_ICEN"))]
    # CAMBIO 2: error claro si algun modelo/modelo quedo sin datos,
    # en vez del ValueError críptico de .min() sobre un Series vacío.
    starts, ends = [], []
    for col in all_idx_cols:
        valid = result[col].dropna()
        if valid.empty:
            number = col.split("_")[0]          # "M23_ONI" -> "M23"
            sys.exit(f"ERROR: {col} quedo sin datos validos "
                     f"(modelo {number} {num2name.get(number, '?')}).")
        starts.append(valid.index.min())
        ends.append(valid.index.max())
    common_start = max(starts)
    common_end = min(ends)
    result = result.loc[common_start:common_end]

    # CAMBIO 3 (opcional): quitar la primera y ultima fila, que tienen
    # NaN en todos los indices por el rolling 3m centrado.
    result = result.dropna(subset=all_idx_cols, how="all")

    y0, y1 = common_start.year, common_end.year
    out_path = c2.E2_DIR / f"p01_indices_enso_{y0}-{y1}.csv"
    result.to_csv(out_path, float_format="%.4f")
    print(f"Ventana comun a los 40 modelos: {common_start.date()} a {common_end.date()}", file=sys.stderr)
    print(f"Listo: {out_path} ({result.shape[0]} filas, {result.shape[1]} columnas)", file=sys.stderr)
    
if __name__ == "__main__":
    main()