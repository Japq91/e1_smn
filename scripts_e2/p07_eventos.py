#!/usr/bin/env python3
"""Paso (11.) del calculo de E2: clasificacion de eventos calidos
extremos, para ONI, RONI e ICEN.

Dos sistemas de umbral en paralelo, no uno solo (ver
informe/borradores/propuesta_puntos_11_12.md para la justificacion
completa -- un umbral absoluto fijo no es robusto entre 40 modelos con
sigma_norm muy distinta entre si, ver taylor_*.csv):

  - OFICIAL: umbral fijo en grados C, el mismo que usa SENAMHI/IGP/
    NOAA operacionalmente -- comparabilidad real con el monitoreo
    oficial. ONI/RONI: >=0.5, sostenido >=5 estaciones consecutivas de
    3 meses (NOAA CPC, confianza alta). ICEN: >=0.4, sostenido >=3
    meses consecutivos (confianza alta para el umbral de inicio; la
    tabla de categorias de magnitud -- debil/moderado/fuerte/
    extraordinario -- es de confianza MEDIA, no verificada contra la
    fuente primaria de ENFEN, ver propuesta_puntos_11_12.md).
    RONI usa las MISMAS categorias que ONI: por construccion,
    std(RONI) == std(ONI) (ver p01_indices_enso.py::roni_index, el
    reescalado de varianza), asi que aplicar la tabla de ONI a RONI es
    consistente, no arbitrario.

  - RELATIVO: umbral proporcional a la propia sigma de cada dataset
    (Shin et al., 2022): moderado >=0.5*sigma, fuerte >=1*sigma,
    extremo >=2*sigma -- sigma calculada sobre la MISMA serie que se
    esta clasificando (ONI/RONI/ICEN, no la anomalia cruda de caja de
    taylor_*.csv, que es una cantidad distinta). Evita que un modelo
    con varianza inflada aparezca con "mas eventos extremos" solo por
    su escala, no por su ENOS real. Esquema de 3 categorias (Shin et
    al. no definen una cuarta categoria "debil"), a diferencia del
    esquema oficial de 4.

    Shin, N.-Y., Kug, J.-S., Stuecker, M. F., Jin, F.-F., Timmermann,
    A., & Kim, G.-I. (2022). More frequent central Pacific El Niño and
    stronger eastern Pacific El Niño in a warmer climate. npj Climate
    and Atmospheric Science, 5, 101.
    doi:10.1038/s41612-022-00324-9

Salida: 3 archivos (uno por indice), formato LARGO (una fila por
evento detectado, no una fila por modelo -- un modelo puede tener 0 o
varios eventos): eventos_ONI_ref<ref>.csv, eventos_RONI_ref<ref>.csv,
eventos_ICEN_ref<ref>.csv. Columnas: number, inicio, fin, fecha_pico,
duracion_meses, magnitud_pico, categoria_oficial, categoria_relativa.
fecha_pico la usa p08_taylor_compuesto.py para centrar la ventana del
compuesto.

Ejecutable de forma independiente: lee directamente
data/processed/e2/indices_enso_*_ref<REF_INICIO>-<REF_FIN>.csv (salida
de p01_indices_enso.py -- si no existe, avisa y corta en vez de
recalcular indices por su cuenta).

Uso:
    python3 scripts_e2/p07_eventos.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common_e2 as c2

# Periodo de referencia -- EDITAR ACA para cambiarlo; debe coincidir
# con el usado al correr p01_indices_enso.py (busca el archivo de
# indices por este sufijo). Independiente del REF_INICIO/REF_FIN de
# los demas pXX.
REF_INICIO = 1981
REF_FIN = 2014

# Umbrales oficiales: (inicio, duracion_minima_meses, categorias)
# categorias: lista de (min, max, nombre), evaluada sobre la magnitud
# PICO del evento (NOAA clasifica por el valor pico alcanzado, no mes
# a mes).
UMBRAL_OFICIAL = {
    "ONI": dict(inicio=0.5, duracion_min=5, categorias=[
        (0.5, 0.9, "debil"), (1.0, 1.4, "moderado"),
        (1.5, 1.9, "fuerte"), (2.0, float("inf"), "muy_fuerte"),
    ]),
    "RONI": dict(inicio=0.5, duracion_min=5, categorias=[
        (0.5, 0.9, "debil"), (1.0, 1.4, "moderado"),
        (1.5, 1.9, "fuerte"), (2.0, float("inf"), "muy_fuerte"),
    ]),
    "ICEN": dict(inicio=0.4, duracion_min=3, categorias=[
        (0.4, 1.3, "debil"), (1.3, 2.1, "moderado"),
        (2.1, 3.5, "fuerte"), (3.5, float("inf"), "extraordinario"),
    ]),
}

# Umbral relativo (Shin et al. 2022): multiplos de la sigma propia del
# dataset. Mismo esquema para los 3 indices -- la duracion minima se
# reusa del umbral oficial de cada indice (no hay una regla de
# duracion propia en Shin et al., que trabaja con eventos anuales, no
# mensuales).
UMBRAL_RELATIVO_SIGMAS = [(0.5, 1.0, "moderado"), (1.0, 2.0, "fuerte"), (2.0, float("inf"), "extremo")]


def detect_events(series, threshold, min_consecutive):
    """series: pd.Series indexada por tiempo (puede tener NaN en los
    bordes). Devuelve lista de dicts inicio/fin/fecha_pico/
    duracion_meses/magnitud_pico. fecha_pico: usada por
    p08_taylor_compuesto.py para centrar la ventana del compuesto."""
    vals = series.values
    times = series.index
    events = []
    i, n = 0, len(vals)
    while i < n:
        if np.isfinite(vals[i]) and vals[i] >= threshold:
            j = i
            while j < n and np.isfinite(vals[j]) and vals[j] >= threshold:
                j += 1
            if (j - i) >= min_consecutive:
                idx_pico = i + int(np.nanargmax(vals[i:j]))
                events.append({
                    "inicio": times[i], "fin": times[j - 1],
                    "fecha_pico": times[idx_pico],
                    "duracion_meses": j - i,
                    "magnitud_pico": float(vals[idx_pico]),
                })
            i = j
        else:
            i += 1
    return events


def categorize(value, categorias):
    # NOAA clasifica sobre el valor YA REDONDEADO a 1 decimal (asi se
    # publican los boletines oficiales) -- las categorias oficiales
    # (0.5-0.9/1.0-1.4/1.5-1.9/>=2.0) fueron definidas para ese valor
    # redondeado, no el continuo. Sin redondear, un valor como 1.4179
    # cae en el hueco entre "moderado" (hasta 1.4) y "fuerte" (desde
    # 1.5) -- bug real detectado al revisar la salida.
    value = round(value, 1)
    for lo, hi, nombre in categorias:
        if lo <= value <= hi:
            return nombre
    return None  # no deberia pasar si value >= umbral de inicio y las categorias cubren desde ahi


def eventos_para_indice(df, index_key):
    # Los eventos se DETECTAN una sola vez, con el umbral oficial (asi
    # se define "que cuenta como evento" -- comparable con monitoreo
    # real). El umbral relativo NO detecta una lista de eventos aparte
    # (eso llevaba a un bug real: al ser mas bajo que el oficial en la
    # mayoria de los casos, el evento relativo "empezaba" antes, fecha
    # de inicio distinta, y el cruce por fecha exacta contra el evento
    # oficial fallaba en silencio para varios eventos). En cambio, el
    # PICO ya detectado se reclasifica en la escala de sigma propia --
    # dos etiquetas sobre el mismo evento, no dos listas de eventos.
    cfg = UMBRAL_OFICIAL[index_key]
    numbers = [c.rsplit("_", 1)[0] for c in df.columns if c.endswith(f"_{index_key}")]

    rows = []
    for number in numbers:
        serie = df[f"{number}_{index_key}"]
        sigma = float(serie.std(ddof=1))

        eventos = detect_events(serie, cfg["inicio"], cfg["duracion_min"])
        for ev in eventos:
            ev["number"] = number
            ev["categoria_oficial"] = categorize(ev["magnitud_pico"], cfg["categorias"])
            ev["categoria_relativa"] = categorize(ev["magnitud_pico"] / sigma, UMBRAL_RELATIVO_SIGMAS)
            rows.append(ev)

    cols = ["number", "inicio", "fin", "fecha_pico", "duracion_meses", "magnitud_pico", "categoria_oficial", "categoria_relativa"]
    return pd.DataFrame(rows, columns=cols) if rows else pd.DataFrame(columns=cols)


def main():
    print("Cargando indices (40 modelos + OBS) ...", file=sys.stderr)
    df = c2.load_all_indices(REF_INICIO, REF_FIN)

    for index_key in ("ONI", "RONI", "ICEN"):
        print(f"  Detectando eventos {index_key} ...", file=sys.stderr)
        eventos = eventos_para_indice(df, index_key)
        out_path = c2.E2_DIR / f"eventos_{index_key}_ref{REF_INICIO}-{REF_FIN}.csv"
        eventos.to_csv(out_path, index=False, float_format="%.4f")
        print(f"  Listo: {out_path} ({len(eventos)} eventos)", file=sys.stderr)


if __name__ == "__main__":
    main()
