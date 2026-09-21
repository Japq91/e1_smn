#!/usr/bin/env bash
# Envoltorio del paso 02: si YA hay una descarga corriendo en otro
# proceso (util cuando se corre run.sh mientras una descarga anterior
# sigue en curso), no lanza otra -- solo lo deja constancia para el
# reporte de estado (generate_status_report.py) via el archivo de
# marca data/interim/.download_running_flag.
set -uo pipefail
cd "$(dirname "$0")/.."

FLAG="data/interim/.download_running_flag"
mkdir -p data/interim

# Patron anclado a "bash/python3 scripts/<nombre>" -- un pgrep -f
# suelto (texto libre) tambien coincide con cualquier proceso que solo
# MENCIONE estos nombres (ej. un 'until ! pgrep -f "02b_..." ...' de
# monitoreo dejado corriendo de fondo), dando un falso positivo de
# "descarga en curso" que bloquea silenciosamente el paso 02 -- pasó en
# la practica.
if pgrep -f "(bash|python3) .*/(02_download_all_sources\.sh|02_download_cmip6_chunks\.sh|02b_search_alt_esgf_nodes\.py|02c_download_copernicus_cds\.py)" > /dev/null; then
    echo "Descarga ya en curso en otro proceso -- no se lanza otra (ver reporte de estado)."
    touch "$FLAG"
else
    rm -f "$FLAG"
    bash scripts/02_download_all_sources.sh
fi
