#!/usr/bin/env bash
# Descarga de CMIP6 (paso 02): SOLO descarga, sin fusionar
# ni recortar. Cada archivo/chunk de ESGF se guarda tal cual llega,
# organizado en data/raw/cmip6/<modelo>/<experimento>/<archivo original>.nc.
#
# NOTA (rediseno): antes este paso tambien fusionaba (mergetime) y
# recortaba (sellonlatbox+selyear) los chunks antes de guardarlos. Esa
# logica se movio al paso 04, que ahora regrilla cada chunk crudo
# (remapbil a la grilla de ERSSTv5) ANTES de fusionarlos -- asi todos
# los chunks de un mismo periodo quedan en la misma grilla antes de
# unirse con mergetime, evitando cualquier inconsistencia entre chunks.
#
# NOTA: el bucket AWS Open Data de CMIP6 almacena los datos en Zarr, no
# en NetCDF, por lo que CDO no puede leerlo ("Unsupported file type",
# verificado). Por eso este script descarga por HTTP directo
# (fileServer) desde los nodos ESGF listados por
# 01_query_esgf_catalog.py -- NetCDF real, verificado con 'cdo sinfo'.
#
# Ya no se descarga 'sftlf' por modelo: el paso 05 (mascara) aplica la
# mascara oceano-tierra de ERSSTv5 sobre los campos ya procesados.
# Solo se descarga la variable 'tos' mensual, un unico miembro de
# ensamble por modelo (ver 01_query_esgf_catalog.py).
#
# MAX_MODELS (variable de entorno, exportada por run.sh): si esta
# definida, limita cuantos modelos "completos" del catalogo se
# descargan en esta corrida, contando en el orden del CSV.
set -euo pipefail
cd "$(dirname "$0")/.."

CATALOG_CSV="data/interim/models_catalog_status.csv"
FILES_JSON="data/interim/esgf_file_urls.json"
OUTDIR="data/raw/cmip6"
FAIL_LOG="logs/download_failures.log"
MAX_MODELS="${MAX_MODELS:-}"   # vacio = sin limite
WGET_TIMEOUT=120

mkdir -p "$OUTDIR" logs

# Devuelve, una por linea, "filename\turl1,url2,..." para model/key
# (key = experimento: historical, ssp245 o ssp585), leido del JSON
# escrito por 01.
list_files_for () {
    python3 -c "
import json, sys
d = json.load(open('$FILES_JSON'))
entries = d.get('$1', {}).get('$2', [])
for e in entries:
    print(e['filename'] + '\t' + ','.join(e['urls']))
"
}

# Descarga un archivo probando cada URL candidata hasta que una funcione.
download_with_mirrors () {
    local urls_csv="$1" outfile="$2"
    IFS=',' read -ra urls <<< "$urls_csv"
    for url in "${urls[@]}"; do
        if wget -q --timeout="$WGET_TIMEOUT" --tries=1 -O "$outfile" "$url"; then
            [ -s "$outfile" ] && return 0
        fi
        rm -f "$outfile"
    done
    return 1
}

download_experiment () {
    local model="$1" exp="$2"
    local dest_dir="$OUTDIR/$model/$exp"
    mkdir -p "$dest_dir"

    while IFS=$'\t' read -r filename urls_csv; do
        [ -z "$filename" ] && continue
        local outfile="$dest_dir/$filename"

        if [ -f "$outfile" ]; then
            continue   # idempotente: no re-descargar este chunk
        fi

        echo "  descargando $filename"
        if ! download_with_mirrors "$urls_csv" "$outfile"; then
            echo "FALLO descarga (todos los mirrors): $model $exp $filename" >> "$FAIL_LOG"
        fi
    done < <(list_files_for "$model" "$exp")
}

model_count=0
while IFS=, read -r model grid_label complete hist ssp245 ssp585; do
    [ "$model" = "model" ] && continue          # saltar encabezado
    [ "$complete" != "True" ] && continue        # solo modelos completos

    if [ -n "$MAX_MODELS" ] && [ "$model_count" -ge "$MAX_MODELS" ]; then
        echo "Limite MAX_MODELS=$MAX_MODELS alcanzado, se omiten los modelos restantes."
        break
    fi
    model_count=$((model_count + 1))

    for exp in historical ssp245 ssp585; do
        echo "Procesando $model $exp ($model_count${MAX_MODELS:+/$MAX_MODELS}) ..."
        download_experiment "$model" "$exp"
    done
done < "$CATALOG_CSV"
