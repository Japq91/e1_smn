#!/usr/bin/env bash
# Descarga observaciones ERSSTv5 desde NOAA PSL (HTTPS, NetCDF real,
# verificado con 'cdo sinfo') y recorta a la misma ventana regional
# usada para CMIP6. Se descarga una sola vez (es la referencia
# observacional fija de todo el pipeline).
#
# Actualizado: ventana ampliada a 100E-70W (antes 120E-80W), 20S-20N.
# El pipeline no genera graficos (ver graficos_exploratorios.ipynb).
set -euo pipefail
cd "$(dirname "$0")/.."

OUTDIR="data/raw/ersstv5"
mkdir -p "$OUTDIR"

echo "Descargando ERSSTv5 desde NOAA PSL..."
wget -q -c --timeout=120 -P "$OUTDIR" \
    "https://downloads.psl.noaa.gov/Datasets/noaa.ersst.v5/sst.mnmean.nc"

# Ventana de descarga (debe coincidir con download_window de config/domains.yaml)
# 100E a 70W (100 a 290 en 0-360), 20S a 20N
LON1=100.0; LON2=290.0; LAT1=-20.0; LAT2=20.0
cdo -O -s -sellonlatbox,${LON1},${LON2},${LAT1},${LAT2} -selvar,sst \
    "$OUTDIR/sst.mnmean.nc" "$OUTDIR/ersstv5_region.nc"
