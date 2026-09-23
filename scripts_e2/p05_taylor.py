#!/usr/bin/env python3
"""Pasos (5.)-(8.) del calculo de E2, consolidados: input completo
para el diagrama de Taylor, por caja (Nino3.4, Nino1+2).

Para cada dataset (ERSSTv5 y cada uno de los 40 modelos), sobre la
ANOMALIA (climatologia propia de cada dataset, periodo de referencia,
sin LS):
  - sigma: desviacion estandar de la anomalia -- (5.) Variabilidad.
  - r: correlacion de PEARSON con la anomalia de ERSSTv5 -- (7.).
    Pearson y no Spearman: la identidad de Taylor de abajo se deriva
    de la covarianza, solo vale para Pearson (Spearman, basado en
    rangos, no tiene esa relacion algebraica con la varianza de la
    diferencia). Ver informe/borradores/marco_teorico_e2.txt.
  - rmse_centrado: RMSE de las anomalias ya centradas (cada serie
    menos su propia media) contra ERSSTv5 -- (6.). Centrado, no el
    RMSE total: asi la identidad de Taylor
        E'^2 = sigma_f^2 + sigma_r^2 - 2*sigma_f*sigma_r*r
    cierra exactamente, y el sesgo medio (que ya se reporta aparte en
    p03_sesgo.py) queda fuera del todo.
  - sigma_norm: sigma/sigma_obs -- (8.). El radio del diagrama,
    adimensional para poder comparar Nino3.4 y Nino1+2 (magnitudes
    distintas) en el mismo grafico.

Referencias: Taylor, K. E. (2001). Summarizing multiple aspects of
model performance in a single diagram. JGR, 106(D7), 7183-7192.
doi:10.1029/2000JD900719 -- Wilks, D. S. (2011). Statistical Methods
in the Atmospheric Sciences (3rd ed.), Academic Press, para la
eleccion Pearson vs. Spearman.

Fila 1 = OBS (ERSSTv5; r=1, rmse_centrado=0, sigma_norm=1 por
definicion); filas 2-41 = M01..M40.

Ejecutable de forma independiente (no depende de que otro pXX haya
corrido antes): lee directamente data/processed/masked/ y
data/processed/e2/model_registry_e2.csv.

Uso:
    python3 scripts_e2/p05_taylor.py
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common_e2 as c2

# Periodo de referencia de la climatologia (para las anomalias que
# alimentan sigma/r/rmse_centrado) -- EDITAR ACA para cambiarlo; el
# nombre del archivo de salida se arma solo a partir de estos dos
# valores. Independiente del REF_INICIO/REF_FIN de los demas pXX.
REF_INICIO = 1981
REF_FIN = 2014


def taylor_table(box_key):
    registry = c2.read_model_registry()
    box = c2.BOXES[box_key]
    weighted = c2.WEIGHTED[box_key]

    obs_serie = c2.box_series(c2.obs_path(), box, "sst", weighted=weighted)
    obs_clim = c2.climatology(obs_serie, REF_INICIO, REF_FIN)
    obs_anom = c2.anomaly(obs_serie, obs_clim)
    sigma_obs = float(obs_anom.std(ddof=1))

    rows = [{"number": "OBS", "sigma": sigma_obs, "r": 1.0, "rmse_centrado": 0.0, "sigma_norm": 1.0}]

    for row in registry:
        number, model = row["number"], row["model"]
        print(f"  [{box_key}] {number} {model} ...", file=sys.stderr)
        serie = c2.box_series(c2.model_path(model), box, "tos", weighted=weighted)
        clim = c2.climatology(serie, REF_INICIO, REF_FIN)
        anom = c2.anomaly(serie, clim)

        sigma = float(anom.std(ddof=1))
        r = c2.pearson_r(anom, obs_anom)
        rmse_c = c2.rmse(anom, obs_anom, centered=True)
        rows.append({
            "number": number, "sigma": sigma, "r": r,
            "rmse_centrado": rmse_c, "sigma_norm": sigma / sigma_obs,
        })

    return pd.DataFrame(rows).set_index("number")


def main():
    for box_key in ("nino34", "nino12"):
        df = taylor_table(box_key)
        out_path = c2.E2_DIR / f"taylor_{box_key}_ref{REF_INICIO}-{REF_FIN}.csv"
        df.to_csv(out_path, float_format="%.4f")
        print(f"Listo: {out_path} ({df.shape[0]} filas, {df.shape[1]} columnas)", file=sys.stderr)


if __name__ == "__main__":
    main()
