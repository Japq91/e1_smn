#!/usr/bin/env python3
"""Paso (14.) del calculo de E2: score de habilidad S (Taylor, 2001)
por modelo, agregado en un solo numero final, y particion
buenos/malos vía gap statistic + Jenks natural breaks -- responde a la
pregunta del TdR ("seleccionar los modelos con mejor capacidad de
representacion") sin imponer un umbral arbitrario.

1. Skill score de Taylor (2001), forma general con exponente n:

       S_n = 4*(1+R)^n / [ (sigma_hat + 1/sigma_hat)^2 * (1+R0)^n ]

   n=1, R0=1 -- EXPONENTE VERIFICADO contra el uso real del skill score
   en evaluacion de modelos CMIP para ENOS (no supuesto, leido
   directamente del PDF): Kaur, S., Kumar, P., Min, S.-K., Patra, A., &
   Wang, X. L. (2021). CMIP5 model evaluation for extreme ocean wave
   height responses to ENSO. Climate Dynamics, 59, 1323-1337, ecuacion
   (3) -- doi:10.1007/s00382-021-06039-6. Con n=1, R0=1 se simplifica
   ((1+R0)^1 = 2):

       S = 4*(1+R) / [ 2*(sigma_hat + 1/sigma_hat)^2 ] = 2*(1+R) / (sigma_hat + 1/sigma_hat)^2

   sigma_hat = sigma_norm (ya en taylor_*.csv), R = r (idem). NO usa
   rmse_centrado -- es redundante dada la identidad de Taylor
   (E'^2 = sigma_hat^2 + 1 - 2*sigma_hat*R en forma normalizada),
   meterlo tambien seria contar la misma informacion dos veces. No usa
   sesgo -- se reporta aparte (p03_sesgo.py), fuera del diagrama de
   Taylor por diseno (ver informe/borradores/marco_teorico_e2.txt,
   Seccion 3).

       Taylor, K. E. (2001). Summarizing multiple aspects of model
       performance in a single diagram. Journal of Geophysical
       Research: Atmospheres, 106(D7), 7183-7192.
       doi:10.1029/2000JD900719

2. Agregacion: SOLO los 3 indices compuestos (ONI, RONI, ICEN),
   promediados con igual peso -- taylor_nino34/nino12 (serie completa)
   quedan deliberadamente FUERA de S_final, decision del usuario tras
   encontrar que ese bloque no es informativo:

       S_final = mean(S_ONI, S_RONI, S_ICEN)

   Por que se excluye la serie completa: `historical` es una corrida
   LIBRE, no inicializada con el estado oceanico real -- nada obliga al
   modelo a estar en fase alta (Nino) el mismo año calendario que la
   observacion. La correlacion de taylor_nino34/nino12 pregunta
   literalmente "¿coincide el año del evento?", pregunta sin respuesta
   posible en una corrida libre (R~0 para CUALQUIER modelo, bueno o
   malo) -- con n=1 el techo matematico de S ahi es ~0.5 (no ~0.06, ese
   numero era con el exponente n=4 sin verificar, ya corregido), pero
   el argumento de fondo no cambia: ese R~0 sigue siendo ruido de fase,
   no señal real de habilidad, y en la corrida real con n=1 el rango de
   S_nino34/S_nino12 (~0.30-0.60) queda igual muy por debajo del rango
   de S_ONI/RONI/ICEN (~0.35-0.99), que si mide algo que el modelo
   puede efectivamente acertar o fallar. Las columnas S_nino34/S_nino12
   se calculan y reportan igual en el CSV, como referencia/diagnostico,
   pero no entran en S_final ni en la particion buenos/malos.

3. Gap statistic (Tibshirani, Walther & Hastie, 2001): responde
   primero si existe siquiera una separacion real entre "buenos" y
   "malos", ANTES de imponer una particion. Compara la dispersion
   intra-grupo real (K=1 vs K=2, K-means) contra la esperada bajo una
   referencia SIN estructura (uniforme en el rango de S_final, B
   datasets de referencia generados por Monte Carlo). Se elige K=1 (sin
   particion, solo ranking continuo) salvo que Gap(2) supere a Gap(1)
   por mas que el margen de error de la referencia (regla estandar del
   paper: elegir el menor k tal que Gap(k) >= Gap(k+1) - s_{k+1}).

       Tibshirani, R., Walther, G., & Hastie, T. (2001). Estimating
       the number of clusters in a data set via the gap statistic.
       Journal of the Royal Statistical Society: Series B, 63(2),
       411-423. doi:10.1111/1467-9868.00293

4. Si el gap statistic confirma K=2: Jenks natural breaks (Fisher,
   1958) sobre S_final da el punto de corte exacto -- el que minimiza
   la varianza dentro de cada grupo (equivalente a K-means 1D con k=2,
   resuelto por busqueda exhaustiva de todos los cortes posibles, exacto
   para 40 puntos). Se reporta tambien el GVF (goodness of variance
   fit): GVF cercano a 1 = corte limpio; GVF bajo = corte debil aunque
   el gap statistic haya preferido K=2, se deja explicito en el CSV.

       Fisher, W. D. (1958). On grouping for maximum homogeneity.
       Journal of the American Statistical Association, 53(284),
       789-798. doi:10.2307/2281952

Ejecutable de forma independiente: lee directamente
data/processed/e2/taylor_nino34_ref<ref>.csv,
taylor_nino12_ref<ref>.csv, taylor_compuesto_ONI/RONI/ICEN_vent12m_ref<ref>.csv
(salidas de p05_taylor.py y p08_taylor_compuesto.py -- si falta alguna,
avisa y corta).

Uso:
    python3 scripts_e2/p09_skill_score.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common_e2 as c2

# Periodo de referencia -- EDITAR ACA para cambiarlo; debe coincidir
# con el usado al generar las 5 tablas taylor_*.csv que este script
# consume (p05_taylor.py, p08_taylor_compuesto.py). Independiente del
# REF_INICIO/REF_FIN de los demas pXX.
REF_INICIO = 1981
REF_FIN = 2014

# Ancho de ventana del compuesto a consumir -- debe coincidir con
# VENTANA_MESES de p08_taylor_compuesto.py. Se usa la corrida principal
# (12, 25 puntos); la de sensibilidad (15, 31 puntos) NO alimenta el
# score final, queda solo como comparacion en el informe.
VENTANA_MESES = 12

# R0: correlacion maxima alcanzable en la formula de Taylor (2001).
# R0=1 -- default estandar sin una estimacion propia de incertidumbre
# observacional de ERSSTv5 (decision del usuario).
R0 = 1.0

# Exponente n de la formula general S_n de Taylor (2001). n=1 -- valor
# verificado contra la ecuacion (3) de Kaur et al. (2021), que aplica
# este mismo skill score a evaluacion de modelos CMIP para ENOS (ver
# docstring del modulo). No es un supuesto propio.
N_EXP = 1

# Gap statistic: numero de datasets de referencia uniforme (Monte
# Carlo) y semilla, para reproducibilidad exacta entre corridas.
N_REF = 1000
SEED = 0


def skill_score(r, sigma_norm):
    """S_n de Taylor (2001), R0 y N_EXP fijos en el modulo (n=1,
    verificado contra Kaur et al. 2021, ecuacion 3 -- ver docstring)."""
    sigma_hat = sigma_norm
    num = 4 * (1 + r) ** N_EXP
    den = (sigma_hat + 1 / sigma_hat) ** 2 * (1 + R0) ** N_EXP
    return num / den


def cargar_S(path, etiqueta):
    if not path.exists():
        sys.exit(f"Falta {path}. Correr antes p05_taylor.py / p08_taylor_compuesto.py con REF_INICIO={REF_INICIO}, REF_FIN={REF_FIN}.")
    df = pd.read_csv(path, index_col="number")
    df = df.drop(index="OBS")  # S=1 trivial por definicion, no es un modelo a evaluar
    return skill_score(df["r"], df["sigma_norm"]).rename(etiqueta)


def gap_statistic(x, k_max=2, b=N_REF, seed=SEED):
    """Tibshirani et al. (2001), k=1 vs k=2 sobre datos 1D. Devuelve el
    k elegido, y los Gap(k)/s(k) para diagnostico en el CSV/README."""
    x = np.asarray(x, dtype=float).reshape(-1, 1)
    rng = np.random.default_rng(seed)

    def wk(data, k):
        if k == 1:
            centro = data.mean(axis=0)
            return float(np.sum((data - centro) ** 2))
        km = KMeans(n_clusters=k, n_init=10, random_state=seed).fit(data)
        return float(km.inertia_)

    logWk = {k: np.log(wk(x, k)) for k in range(1, k_max + 1)}
    xmin, xmax = float(x.min()), float(x.max())

    logWkb = {k: [] for k in range(1, k_max + 1)}
    for _ in range(b):
        ref = rng.uniform(xmin, xmax, size=x.shape)
        for k in range(1, k_max + 1):
            logWkb[k].append(np.log(wk(ref, k)))

    gap, sk = {}, {}
    for k in range(1, k_max + 1):
        arr = np.array(logWkb[k])
        gap[k] = float(arr.mean() - logWk[k])
        sd = float(arr.std(ddof=1))
        sk[k] = sd * np.sqrt(1 + 1 / b)

    elegido = 1
    for k in range(1, k_max):
        if gap[k] >= gap[k + 1] - sk[k + 1]:
            elegido = k
            break
    else:
        elegido = k_max

    return dict(k=elegido, gap=gap, sk=sk)


def natural_break_2(values):
    """Jenks natural breaks, k=2, por busqueda exhaustiva (exacto para
    n=40) -- equivalente a K-means 1D con k=2. Devuelve el punto de
    corte (punto medio entre los dos grupos) y el GVF."""
    v = np.sort(np.asarray(values, dtype=float))
    n = len(v)
    media_total = v.mean()
    sdam = float(np.sum((v - media_total) ** 2))

    mejor_sdcm, mejor_i = None, None
    for i in range(1, n):
        g1, g2 = v[:i], v[i:]
        sdcm = float(np.sum((g1 - g1.mean()) ** 2) + np.sum((g2 - g2.mean()) ** 2))
        if mejor_sdcm is None or sdcm < mejor_sdcm:
            mejor_sdcm, mejor_i = sdcm, i

    corte = float((v[mejor_i - 1] + v[mejor_i]) / 2)
    gvf = 1 - mejor_sdcm / sdam
    return dict(corte=corte, gvf=float(gvf), n_bajo=mejor_i, n_alto=n - mejor_i)


def main():
    print("Cargando taylor_*.csv (5 tablas) ...", file=sys.stderr)
    s_nino34 = cargar_S(c2.E2_DIR / f"taylor_nino34_ref{REF_INICIO}-{REF_FIN}.csv", "S_nino34")
    s_nino12 = cargar_S(c2.E2_DIR / f"taylor_nino12_ref{REF_INICIO}-{REF_FIN}.csv", "S_nino12")
    s_oni = cargar_S(c2.E2_DIR / f"taylor_compuesto_ONI_vent{VENTANA_MESES}m_ref{REF_INICIO}-{REF_FIN}.csv", "S_ONI")
    s_roni = cargar_S(c2.E2_DIR / f"taylor_compuesto_RONI_vent{VENTANA_MESES}m_ref{REF_INICIO}-{REF_FIN}.csv", "S_RONI")
    s_icen = cargar_S(c2.E2_DIR / f"taylor_compuesto_ICEN_vent{VENTANA_MESES}m_ref{REF_INICIO}-{REF_FIN}.csv", "S_ICEN")

    df = pd.concat([s_nino34, s_nino12, s_oni, s_roni, s_icen], axis=1)
    registro = c2.read_model_registry()
    orden = [r["number"] for r in registro]
    df = df.reindex(orden)

    # S_nino34/S_nino12 se reportan como referencia/diagnostico -- no
    # entran en S_final, ver docstring (problema de fase, serie
    # completa no informativa en corridas libres).
    df["S_final"] = df[["S_ONI", "S_RONI", "S_ICEN"]].mean(axis=1)

    print("Corriendo gap statistic (K=1 vs K=2, Tibshirani et al. 2001) ...", file=sys.stderr)
    gap = gap_statistic(df["S_final"].values)
    print(f"  Gap(1)={gap['gap'][1]:.4f} +- s(1)={gap['sk'][1]:.4f}", file=sys.stderr)
    print(f"  Gap(2)={gap['gap'][2]:.4f} +- s(2)={gap['sk'][2]:.4f}", file=sys.stderr)
    print(f"  K elegido = {gap['k']}", file=sys.stderr)

    if gap["k"] == 2:
        brk = natural_break_2(df["S_final"].values)
        print(f"  Jenks: corte={brk['corte']:.4f}, GVF={brk['gvf']:.4f} "
              f"({brk['n_bajo']} 'malo' / {brk['n_alto']} 'bueno')", file=sys.stderr)
        df["grupo"] = np.where(df["S_final"] >= brk["corte"], "bueno", "malo")
    else:
        print("  Sin separacion real confirmada (K=1) -- se deja 'grupo' vacio, "
              "solo ranking continuo por S_final.", file=sys.stderr)
        df["grupo"] = ""

    df = df.sort_values("S_final", ascending=False)
    df.index.name = "number"

    out_path = c2.E2_DIR / f"skill_score_ref{REF_INICIO}-{REF_FIN}.csv"
    df.to_csv(out_path, float_format="%.4f")
    print(f"Listo: {out_path} ({df.shape[0]} filas, {df.shape[1]} columnas)", file=sys.stderr)


if __name__ == "__main__":
    main()
