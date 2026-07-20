#!/usr/bin/env bash
# Verifica dependencias (cdo, wget, python3+requests) y crea el
# esqueleto de carpetas de datos/logs del pipeline. No instala nada:
# solo falla temprano y con un mensaje claro si falta una herramienta.
#
# NOTA (correccion): ya no se requiere AWS CLI. La adquisicion de datos
# se hace por HTTP directo contra nodos ESGF (ver 02 y 03), tras
# verificar que el bucket AWS Open Data de CMIP6 esta en formato Zarr
# (incompatible con CDO) y que el bucket de ERSSTv5 en S3 no existe.
set -euo pipefail
cd "$(dirname "$0")/.."

REQUIRED_BINS=(cdo wget python3)
missing=0

for bin in "${REQUIRED_BINS[@]}"; do
    if ! command -v "$bin" >/dev/null 2>&1; then
        echo "FALTA: '$bin' no esta instalado o no esta en el PATH." >&2
        missing=1
    fi
done

if ! python3 -c "import requests" >/dev/null 2>&1; then
    echo "FALTA: el paquete de Python 'requests' no esta instalado (pip install requests)." >&2
    missing=1
fi

if [ "$missing" -ne 0 ]; then
    echo "00_setup_env.sh: dependencias faltantes, abortando." >&2
    exit 1
fi

mkdir -p data/raw/cmip6 data/raw/ersstv5
mkdir -p data/interim data/processed logs

echo "Entorno verificado: cdo=$(cdo -V 2>&1 | head -1), python3=$(python3 --version 2>&1)"
echo "Estructura de carpetas lista bajo $(pwd)/data y $(pwd)/logs"
