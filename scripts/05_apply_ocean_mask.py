#!/usr/bin/env python3
"""Mascara oceano-tierra y su aplicacion a los modelos procesados
(paso 05).

Reescrito en Python (antes era CDO): la cadena anterior
('mulc,0 -> setmisstoc,-1 -> addc,1' sobre el timmean de ERSSTv5)
calculaba mal la mascara -- verificado: 'cdo mulc,0' multiplica el
propio valor de relleno (_FillValue ~ -9.97e+36) por 0, da ~0, y ese 0
ya no coincide con _FillValue, asi que los puntos de tierra dejan de
quedar marcados como faltantes. Resultado: mascara = 1 (oceano) en TODO
el dominio, incluida la tierra (confirmado con 'cdo infon': el timmean
trae 175 puntos faltantes de 2016, pero tras mulc,0 quedan 0). Con
netCDF4 el manejo de faltantes es explicito via numpy.ma y no tiene
esa trampa.

Un punto se considera oceano si tiene al menos un valor valido en algun
mes del registro completo de ERSSTv5 (equivalente al criterio anterior:
solo es tierra si TODOS los meses estan faltantes ahi).

Uso:
    python3 05_apply_ocean_mask.py
"""
import shutil
import sys
from pathlib import Path

import netCDF4 as nc
import numpy as np

NON_DATA_NAMES = {
    "lat", "lon", "x", "y", "time", "lat_bnds", "lon_bnds", "time_bnds", "bnds",
}

IN_DIR = Path("data/interim/processed")
OUT_DIR = Path("data/processed/masked")
MASK_FILE = Path("data/interim/ocean_mask.nc")


def _first_data_var(ds: nc.Dataset) -> str:
    for name, var in ds.variables.items():
        if name not in NON_DATA_NAMES and var.ndim >= 1:
            return name
    raise ValueError("No se encontro una variable de datos en el archivo")


def build_ocean_mask(ersstv5_path: Path, mask_path: Path) -> None:
    with nc.Dataset(ersstv5_path) as ds:
        varname = _first_data_var(ds)
        data = ds.variables[varname][:]  # masked array: netCDF4 respeta _FillValue
        lat = ds.variables["lat"][:]
        lon = ds.variables["lon"][:]

    land = np.ma.getmaskarray(data).all(axis=0)  # faltante en TODOS los meses -> tierra
    ocean_mask = (~land).astype("int8")

    with nc.Dataset(mask_path, "w") as out:
        out.createDimension("lat", len(lat))
        out.createDimension("lon", len(lon))
        v_lat = out.createVariable("lat", "f8", ("lat",))
        v_lat[:] = lat
        v_lat.units = "degrees_north"
        v_lon = out.createVariable("lon", "f8", ("lon",))
        v_lon[:] = lon
        v_lon.units = "degrees_east"
        v_mask = out.createVariable("ocean_mask", "i1", ("lat", "lon"))
        v_mask[:] = ocean_mask
        v_mask.long_name = "1 = oceano, 0 = tierra (derivada de ERSSTv5)"

    n_ocean = int(ocean_mask.sum())
    print(f"Mascara construida: {n_ocean}/{ocean_mask.size} puntos de oceano", file=sys.stderr)


def apply_mask(infile: Path, outfile: Path, ocean_mask: np.ndarray) -> None:
    shutil.copyfile(infile, outfile)
    with nc.Dataset(outfile, "r+") as ds:
        varname = _first_data_var(ds)
        var = ds.variables[varname]
        data = var[:]
        land = np.broadcast_to(~ocean_mask.astype(bool), data.shape)
        var[:] = np.ma.masked_where(land, data)


def main() -> None:
    ersstv5 = IN_DIR / "ersstv5_region.nc"
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if not ersstv5.exists():
        sys.exit(f"FALTA {ersstv5} -- corre antes los pasos 03 (ERSSTv5) y 04 (procesamiento).")

    if not MASK_FILE.exists():
        print("Construyendo mascara oceano-tierra a partir de ERSSTv5 ...", file=sys.stderr)
        build_ocean_mask(ersstv5, MASK_FILE)

    with nc.Dataset(MASK_FILE) as ds:
        ocean_mask = ds.variables["ocean_mask"][:]

    for f in sorted(IN_DIR.glob("tos_*.nc")):
        outfile = OUT_DIR / f.name
        if outfile.exists():
            print(f"Ya procesado, se omite: {f.name}", file=sys.stderr)
            continue
        apply_mask(f, outfile, ocean_mask)

    out_ersst = OUT_DIR / "ersstv5_region.nc"
    if not out_ersst.exists():
        shutil.copyfile(ersstv5, out_ersst)


if __name__ == "__main__":
    main()
