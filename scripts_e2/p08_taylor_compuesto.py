#!/usr/bin/env python3
"""Paso (12.) del calculo de E2: diagrama de Taylor sobre la evolucion
COMPUESTA de los eventos calidos extremos (no sobre la serie completa
del indice).

Insumo directo del paso (11.) (eventos_*.csv, p07_eventos.py) -- no
son pasos independientes. Ver
informe/borradores/propuesta_puntos_11_12.md para la justificacion
completa: la correlacion de fase entre un modelo historical libre y
las observaciones es practicamente nula (no reproducen El Nino en el
mismo anio -- no son corridas inicializadas), asi que el diagrama de
Taylor sobre la serie completa (p05_taylor.py) tiene poco poder para
distinguir modelos. El analisis compuesto evita el problema: en vez de
"?el evento paso el mismo anio?" (imposible de acertar en libre),
pregunta "cuando el modelo SI genera un evento, ?tiene la forma
correcta?" (arma, pico, decaimiento) -- respondible con una corrida
libre, y mas fiel a lo que pide el TdR.

Metodologia (confirmada por el usuario):
  1. Para cada evento de eventos_<INDICE>_ref<ref>.csv: ventana de
     +-12 meses (24 meses totales) centrada en fecha_pico -- mismo
     ancho que Kaur et al. (2021) y Kumar et al. (2023).
  2. Eventos en el borde del registro (la ventana pediria meses fuera
     del rango disponible) se DESCARTAN enteros, no se rellenan con
     NaN -- decision explicita del usuario.
  3. Promediar las ventanas validas de cada dataset -> una curva de 25
     puntos ("meses relativos al pico", eje t=-12..0..+12): el "evento
     tipico" de ese dataset.
  4. Comparar la curva compuesta del modelo contra la de ERSSTv5 con
     las mismas 4 metricas de p05_taylor.py (sigma, r, rmse_centrado,
     sigma_norm) -- pero sobre la forma del compuesto, no la serie
     completa.

    Kaur, S., Kumar, P., Min, S.-K., Patra, A., & Wang, X. L. (2021).
    CMIP5 model evaluation for extreme ocean wave height responses to
    ENSO. Climate Dynamics. doi:10.1007/s00382-021-06039-6

Salida: 3 archivos, mismo formato de 4 columnas que taylor_*.csv (fila
OBS + M01..M40): taylor_compuesto_ONI_ref<ref>.csv,
taylor_compuesto_RONI_ref<ref>.csv, taylor_compuesto_ICEN_ref<ref>.csv.

Ejecutable de forma independiente: lee directamente
data/processed/e2/eventos_*_ref<REF_INICIO>-<REF_FIN>.csv (salida de
p07_eventos.py -- si no existe, avisa y corta) y
data/processed/e2/indices_enso_*_ref<REF_INICIO>-<REF_FIN>.csv (salida
de p01_indices_enso.py).

Uso:
    python3 scripts_e2/p08_taylor_compuesto.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common_e2 as c2

# Periodo de referencia -- EDITAR ACA para cambiarlo; debe coincidir
# con el usado en p01_indices_enso.py y p07_eventos.py (busca los
# archivos de entrada por este sufijo). Independiente del
# REF_INICIO/REF_FIN de los demas pXX.
REF_INICIO = 1981
REF_FIN = 2014

# Ancho de la ventana compuesta -- Kaur et al. (2021) / Kumar et al.
# (2023): 24 meses totales, +-12 centrados en el pico.
VENTANA_MESES = 12


def eventos_path(index_key):
    p = c2.E2_DIR / f"eventos_{index_key}_ref{REF_INICIO}-{REF_FIN}.csv"
    if not p.exists():
        sys.exit(f"Falta {p}. Correr antes p07_eventos.py con REF_INICIO={REF_INICIO}, REF_FIN={REF_FIN}.")
    return p


def composite_curve(serie, fechas_pico, ventana=VENTANA_MESES):
    """serie: pd.Series indexada por tiempo (mensual, sin huecos).
    fechas_pico: lista de Timestamps. Devuelve (curva, n_usados,
    n_descartados) -- curva: array de 2*ventana+1 puntos (mes relativo
    -ventana..+ventana), promedio de los eventos con ventana COMPLETA
    disponible; los que caen parcialmente fuera del rango se descartan
    enteros (no se rellenan), decision explicita del usuario."""
    ventanas_validas = []
    n_descartados = 0
    for fecha in fechas_pico:
        try:
            pos = serie.index.get_loc(fecha)
        except KeyError:
            n_descartados += 1
            continue
        ini, fin = pos - ventana, pos + ventana
        if ini < 0 or fin >= len(serie):
            n_descartados += 1
            continue
        tramo = serie.iloc[ini:fin + 1].values
        if np.any(np.isnan(tramo)):
            n_descartados += 1
            continue
        ventanas_validas.append(tramo)

    if not ventanas_validas:
        return None, 0, n_descartados
    curva = np.mean(np.vstack(ventanas_validas), axis=0)
    return curva, len(ventanas_validas), n_descartados


def taylor_compuesto_tabla(index_key):
    df_indices = c2.load_all_indices(REF_INICIO, REF_FIN)
    df_eventos = pd.read_csv(eventos_path(index_key), parse_dates=["fecha_pico"])

    obs_serie = df_indices[f"OBS_{index_key}"]
    obs_fechas = df_eventos.loc[df_eventos["number"] == "OBS", "fecha_pico"].tolist()
    obs_curva, n_obs_usados, n_obs_desc = composite_curve(obs_serie, obs_fechas)
    if obs_curva is None:
        sys.exit(f"{index_key}: OBS no tiene ningun evento con ventana completa -- no se puede armar el compuesto.")
    print(f"  [{index_key}] OBS: {n_obs_usados} eventos usados, {n_obs_desc} descartados por borde", file=sys.stderr)
    sigma_obs = float(np.std(obs_curva, ddof=1))

    rows = [{"number": "OBS", "sigma": sigma_obs, "r": 1.0, "rmse_centrado": 0.0, "sigma_norm": 1.0}]

    registry = c2.read_model_registry()
    for row in registry:
        number, model = row["number"], row["model"]
        serie = df_indices[f"{number}_{index_key}"]
        fechas = df_eventos.loc[df_eventos["number"] == number, "fecha_pico"].tolist()
        curva, n_usados, n_desc = composite_curve(serie, fechas)
        print(f"  [{index_key}] {number} {model}: {n_usados} eventos usados, {n_desc} descartados por borde",
              file=sys.stderr)
        if curva is None:
            print(f"    AVISO: {number} sin ningun evento con ventana completa -- fila omitida.", file=sys.stderr)
            continue
        stats = c2.taylor_stats_arrays(curva, obs_curva)
        rows.append({"number": number, **stats})

    return pd.DataFrame(rows).set_index("number")


def main():
    for index_key in ("ONI", "RONI", "ICEN"):
        df = taylor_compuesto_tabla(index_key)
        out_path = c2.E2_DIR / f"taylor_compuesto_{index_key}_ref{REF_INICIO}-{REF_FIN}.csv"
        df.to_csv(out_path, float_format="%.4f")
        print(f"Listo: {out_path} ({df.shape[0]} filas, {df.shape[1]} columnas)", file=sys.stderr)


if __name__ == "__main__":
    main()
