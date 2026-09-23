#!/usr/bin/env python3
"""Paso (4.) del calculo de E2: sesgo de variabilidad (diferencia
porcentual de desviacion estandar) por punto de grid.

    D(lat, lon) = 100 * (sigma_modelo - sigma_obs) / sigma_obs

sigma = desviacion estandar de la ANOMALIA (climatologia propia de
cada dataset removida primero, mismo periodo de referencia que la
climatologia), no del valor crudo -- si se usara el valor crudo la
diferencia quedaria dominada por el ciclo anual (que apenas difiere
entre datasets), tapando la variabilidad interanual real. Equivalente
a 100*(sigma_norm - 1), el mismo cociente que se usa en el diagrama de
Taylor (Secciones 8/17 del notebook de prueba), pero calculado punto a
punto en todo el dominio, no sobre el promedio de una caja.

Dominio: igual a p03_sesgo.py -- el mismo de data/processed/masked/*.nc
completo (lat -30/30, lon global), sin recortar a ninguna caja.
Complementa directamente al sesgo de p03 (esto es el sesgo de
variabilidad/segundo momento; p03 es el de la media/primer momento).

Ejecutable de forma independiente (no depende de que otro pXX haya
corrido antes): lee directamente data/processed/masked/ y
data/processed/e2/model_registry_e2.csv.

Uso:
    python3 scripts_e2/p04_variabilidad.py
"""
import sys
from pathlib import Path

import xarray as xr

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common_e2 as c2

# Periodo de referencia (climatologia Y calculo de sigma de la
# anomalia) -- EDITAR ACA para cambiarlo; el nombre del archivo de
# salida se arma solo a partir de estos dos valores. Independiente del
# REF_INICIO/REF_FIN de los demas pXX.
REF_INICIO = 1981
REF_FIN = 2014


def main():
    registry = c2.read_model_registry()

    print("  ERSSTv5 (obs) ...", file=sys.stderr)
    obs_std = c2.field_anomaly_std(c2.obs_path(), "sst", REF_INICIO, REF_FIN)

    diff_maps, numbers, model_names = [], [], []
    for row in registry:
        number_str, model = row["number"], row["model"]
        n = int(number_str[1:])  # 'M01' -> 1
        print(f"  {number_str} ({n}) {model} ...", file=sys.stderr)
        model_std = c2.field_anomaly_std(c2.model_path(model), "tos", REF_INICIO, REF_FIN)
        diff_maps.append(100.0 * (model_std - obs_std) / obs_std)
        numbers.append(n)
        model_names.append(model)

    diff_da = xr.concat(diff_maps, dim="number").assign_coords(number=numbers).sortby("number")
    diff_da.name = "std_diff_pct"
    diff_da.attrs["units"] = "%"
    diff_da.attrs["long_name"] = "Diferencia porcentual de sigma de la anomalia, modelo vs ERSSTv5"
    diff_da.attrs["formula"] = "100 * (sigma_modelo - sigma_obs) / sigma_obs"
    diff_da.attrs["periodo_referencia"] = f"{REF_INICIO}-{REF_FIN}"
    diff_da["number"].attrs["long_name"] = "Numero de modelo (ver model_registry_e2.csv, M01..M40)"

    orden = sorted(range(len(numbers)), key=lambda i: numbers[i])
    model_coord = xr.DataArray(
        [model_names[i] for i in orden], dims="number",
        coords={"number": [numbers[i] for i in orden]},
    )

    ds_out = diff_da.to_dataset()
    ds_out["model"] = model_coord
    ds_out.attrs["descripcion"] = (
        "Sesgo de variabilidad (diferencia % de sigma sobre la anomalia) por punto de grid, "
        f"periodo de referencia {REF_INICIO}-{REF_FIN}. Sin correccion Linear Scaling."
    )

    out_path = c2.E2_DIR / f"variabilidad_tsm_ref{REF_INICIO}-{REF_FIN}.nc"
    ds_out.to_netcdf(out_path)
    print(f"Listo: {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
