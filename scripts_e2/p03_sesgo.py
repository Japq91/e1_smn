#!/usr/bin/env python3
"""Paso (3.) del calculo de E2: sesgo (BIAS) por punto de grid.

Un solo valor de sesgo por punto (lat, lon), promediando TODA la serie
temporal del periodo de referencia (12*34 = 408 meses para 1981-2014),
no 12 mapas separados por mes calendario:

    B(lat, lon) = media_tiempo(TOS_modelo(t, lat, lon)) - media_tiempo(SST_obs(t, lat, lon))

Dominio: el mismo de data/processed/masked/*.nc completo (lat -30/30,
lon global) -- no se recorta a ninguna caja.

Salida: un unico NetCDF con dimension 'number' (1..40, uno por
modelo, mismo orden que model_registry_e2.csv) ademas de (lat, lon).

Ejecutable de forma independiente (no depende de que otro pXX haya
corrido antes): lee directamente data/processed/masked/ y
data/processed/e2/model_registry_e2.csv.

Uso:
    python3 scripts_e2/p03_sesgo.py
"""
import sys
from pathlib import Path

import xarray as xr

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common_e2 as c2

# Periodo de referencia -- EDITAR ACA para cambiarlo; el nombre del
# archivo de salida se arma solo a partir de estos dos valores.
# Independiente del REF_INICIO/REF_FIN de los demas pXX.
REF_INICIO = 1981
REF_FIN = 2014


def main():
    registry = c2.read_model_registry()

    print("  ERSSTv5 (obs) ...", file=sys.stderr)
    obs_mean = c2.field_time_mean(c2.obs_path(), "sst", REF_INICIO, REF_FIN)

    bias_maps, numbers, model_names = [], [], []
    for row in registry:
        number_str, model = row["number"], row["model"]
        n = int(number_str[1:])  # 'M01' -> 1
        print(f"  {number_str} ({n}) {model} ...", file=sys.stderr)
        model_mean = c2.field_time_mean(c2.model_path(model), "tos", REF_INICIO, REF_FIN)
        bias_maps.append(model_mean - obs_mean)
        numbers.append(n)
        model_names.append(model)

    bias_da = xr.concat(bias_maps, dim="number").assign_coords(number=numbers).sortby("number")
    bias_da.name = "bias"
    bias_da.attrs["units"] = "degC"
    bias_da.attrs["long_name"] = "Sesgo TOS modelo menos ERSSTv5, media del periodo de referencia"
    bias_da.attrs["periodo_referencia"] = f"{REF_INICIO}-{REF_FIN}"
    bias_da["number"].attrs["long_name"] = "Numero de modelo (ver model_registry_e2.csv, M01..M40)"

    orden = sorted(range(len(numbers)), key=lambda i: numbers[i])
    model_coord = xr.DataArray(
        [model_names[i] for i in orden], dims="number",
        coords={"number": [numbers[i] for i in orden]},
    )

    ds_out = bias_da.to_dataset()
    ds_out["model"] = model_coord
    ds_out.attrs["descripcion"] = (
        "Sesgo (BIAS) de TSM por punto de grid, modelo menos ERSSTv5, "
        f"periodo de referencia {REF_INICIO}-{REF_FIN}. Sin correccion Linear Scaling."
    )

    out_path = c2.E2_DIR / f"sesgo_tsm_ref{REF_INICIO}-{REF_FIN}.nc"
    ds_out.to_netcdf(out_path)
    print(f"Listo: {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
