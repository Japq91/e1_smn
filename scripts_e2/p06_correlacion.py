#!/usr/bin/env python3
"""Paso (13.) del calculo de E2 (propuesta del usuario): correlacion
por punto de grid entre modelo y ERSSTv5, con significancia.

Misma logica espacial que p03_sesgo.py/p04_variabilidad.py (un valor
por punto de grid, no por caja), pero correlacionando -- en cada punto
(lat,lon) -- la serie temporal del MODELO en ese punto contra la serie
temporal de ERSSTv5 en ese MISMO punto (no contra un indice fijo tipo
Nino3.4, a diferencia de la Seccion 18 del notebook de pruebas).

Sobre la ANOMALIA (climatologia propia de cada dataset, periodo de
referencia, sin LS) -- igual criterio que p04, para que la correlacion
no quede inflada por el ciclo anual compartido.

Significancia: p-value continuo (no un flag booleano a un umbral fijo
-- se decide despues, al graficar), via test-t CORREGIDO por
autocorrelacion temporal (Bretherton et al., 1999): la TSM mensual
esta fuertemente autocorrelacionada, tratar los ~N meses como
observaciones independientes sobreestima donde es significativo (bug
real detectado y corregido en el notebook de pruebas, Seccion 18 --
ver lag1_autocorr en common_e2.py). n_efectivo = n*(1-r1_o*r1_m)/(1+r1_o*r1_m).

Salida: un unico NetCDF con dimension 'number' (1..40) + (lat, lon),
variables 'corr' y 'sign' (p-value).

Ejecutable de forma independiente (no depende de que otro pXX haya
corrido antes): lee directamente data/processed/masked/ y
data/processed/e2/model_registry_e2.csv.

Uso:
    python3 scripts_e2/p06_correlacion.py
"""
import sys
from pathlib import Path

import numpy as np
import xarray as xr
from scipy import stats as _stats

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common_e2 as c2

# Periodo de referencia (climatologia Y ventana de la correlacion) --
# EDITAR ACA para cambiarlo; el nombre del archivo de salida se arma
# solo a partir de estos dos valores.
REF_INICIO = 1981
REF_FIN = 2014


def corr_and_significance(model_anom, obs_anom):
    m, o = xr.align(model_anom, obs_anom, join="inner")
    r = xr.corr(m, o, dim="time")
    n = int(m.sizes["time"])
    r1_m = c2.lag1_autocorr(m)
    r1_o = c2.lag1_autocorr(o)
    n_eff = (n * (1 - r1_o * r1_m) / (1 + r1_o * r1_m)).clip(min=3, max=n)
    with np.errstate(invalid="ignore", divide="ignore"):
        t = r.values * np.sqrt((n_eff.values - 2) / (1 - r.values ** 2))
        p = 2 * (1 - _stats.t.cdf(np.abs(t), df=n_eff.values - 2))
    return r, xr.DataArray(p, coords=r.coords, dims=r.dims)


def main():
    registry = c2.read_model_registry()

    print("  ERSSTv5 (obs) ...", file=sys.stderr)
    obs_anom = c2.field_anomaly(c2.obs_path(), "sst", REF_INICIO, REF_FIN)

    corr_maps, sign_maps, numbers, model_names = [], [], [], []
    for row in registry:
        number_str, model = row["number"], row["model"]
        n = int(number_str[1:])  # 'M01' -> 1
        print(f"  {number_str} ({n}) {model} ...", file=sys.stderr)
        model_anom = c2.field_anomaly(c2.model_path(model), "tos", REF_INICIO, REF_FIN)
        r, p = corr_and_significance(model_anom, obs_anom)
        corr_maps.append(r)
        sign_maps.append(p)
        numbers.append(n)
        model_names.append(model)

    corr_da = xr.concat(corr_maps, dim="number").assign_coords(number=numbers).sortby("number")
    sign_da = xr.concat(sign_maps, dim="number").assign_coords(number=numbers).sortby("number")

    corr_da.name = "corr"
    corr_da.attrs["long_name"] = "Correlacion de Pearson (anomalia), modelo vs ERSSTv5, mismo punto de grid"
    corr_da.attrs["units"] = "1"

    sign_da.name = "sign"
    sign_da.attrs["long_name"] = "p-value (test-t, n efectivo corregido por autocorrelacion, Bretherton et al. 1999)"
    sign_da.attrs["units"] = "1"

    orden = sorted(range(len(numbers)), key=lambda i: numbers[i])
    model_coord = xr.DataArray(
        [model_names[i] for i in orden], dims="number",
        coords={"number": [numbers[i] for i in orden]},
    )

    ds_out = xr.Dataset({"corr": corr_da, "sign": sign_da, "model": model_coord})
    ds_out.attrs["descripcion"] = (
        "Correlacion de Pearson y significancia (p-value, n efectivo) por punto de grid, "
        f"modelo vs ERSSTv5 en el mismo punto, periodo de referencia {REF_INICIO}-{REF_FIN}. "
        "Sin correccion Linear Scaling."
    )
    ds_out["number"].attrs["long_name"] = "Numero de modelo (ver model_registry_e2.csv, M01..M40)"

    out_path = c2.E2_DIR / f"correlacion_tsm_ref{REF_INICIO}-{REF_FIN}.nc"
    ds_out.to_netcdf(out_path)
    print(f"Listo: {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
