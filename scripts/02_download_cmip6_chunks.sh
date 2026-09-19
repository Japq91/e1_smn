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
# descargan en esta corrida, contando en el orden en que aparecen en
# el catalogo.
set -euo pipefail
cd "$(dirname "$0")/.."

CATALOG_CSV="data/interim/models_catalog_status.csv"
if [ ! -f "config/models_seed_cmip6.csv" ] || [ ! -f "$CATALOG_CSV" ]; then
    echo "Falta config/models_seed_cmip6.csv o $CATALOG_CSV -- correr antes los pasos 00b y 01." >&2
    exit 1
fi
FILES_JSON="data/interim/esgf_file_urls.json"
OUTDIR="data/raw/cmip6"
INTERIM_PROCESSED_DIR="data/interim/processed"
MASKED_DIR="data/processed/masked"
FAIL_LOG="logs/download_failures.log"
MAX_MODELS="${MAX_MODELS:-}"   # vacio = sin limite
WGET_TIMEOUT=120
# Experimentos a descargar: historical + escenarios SSP, leidos de
# config/periods.yaml (fuente unica de verdad, ver scripts/pipeline_config.py).
mapfile -t EXPERIMENTS < <(python3 scripts/pipeline_config.py experiments | tr ' ' '\n')

mkdir -p "$OUTDIR" logs

# Modelos aptos para descarga: deben estar en config/models_seed_cmip6.csv
# (00b ya inspecciono el universo completo de 102 modelos bajo el
# criterio ACTUAL de config/periods.yaml y solo incluye ahi a los que
# de verdad tienen los 3 SSP + historical) Y tener, en el catalogo,
# 'True' explicito para CADA experimento actualmente configurado (ver
# pipeline_config.row_is_complete). No basta con la columna 'complete'
# del catalogo: una fila resuelta cuando el config tenia menos
# escenarios queda con 'complete=True' pero con la celda del escenario
# agregado despues vacia -- verificado en la practica con modelos como
# CIESM/GFDL-CM4 (les falta ssp370 segun el propio reporte de 00b) que
# sin este doble chequeo se reintentaban en cada corrida sin ninguna
# posibilidad real de completarse.
mapfile -t READY_MODELS < <(python3 -c "
import csv
import sys
sys.path.insert(0, 'scripts')
import pipeline_config as pc

with open('config/models_seed_cmip6.csv', newline='') as f:
    seed = {row['model'] for row in csv.DictReader(f)}

with open('$CATALOG_CSV', newline='') as f:
    for row in csv.DictReader(f):
        if row['model'] in seed and pc.row_is_complete(row):
            print(row['model'])
")

# Devuelve, una por linea, "filename\turl1,url2,..." para model/key
# (key = experimento: historical o alguno de los escenarios SSP de
# config/periods.yaml), leido del JSON escrito por 01.
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

    local start_ts downloaded_any=0
    start_ts=$(date +%s)

    # Contador de progreso (algunos modelos publican historical/ssp* en
    # decenas de archivos sueltos, ej. un chunk por anio individual y no
    # contiguo -- sin esto, avanzar por una lista larga parece "colgado"
    # aunque este funcionando bien).
    local file_list total i=0
    file_list=$(list_files_for "$model" "$exp")
    total=$(printf '%s\n' "$file_list" | grep -c .)

    while IFS=$'\t' read -r filename urls_csv; do
        [ -z "$filename" ] && continue
        i=$((i + 1))
        local outfile="$dest_dir/$filename"

        if [ -s "$outfile" ]; then
            continue   # idempotente: no re-descargar este chunk (-s: existe y no esta vacio)
        fi

        echo "  descargando archivo $i/$total: $filename"
        if download_with_mirrors "$urls_csv" "$outfile"; then
            downloaded_any=1
        else
            echo "FALLO descarga (todos los mirrors): $model $exp $filename" >> "$FAIL_LOG"
        fi
    done <<< "$file_list"

    # Tiempo real de descarga -- solo se registra si hubo algo NUEVO
    # descargado (no cuenta si todo ya estaba en disco). Alimenta el
    # estimado de "cuanto falta" del reporte preflight (ver
    # scripts/pipeline_timing.py y scripts/preflight_report.py).
    if [ "$downloaded_any" -eq 1 ]; then
        local elapsed=$(( $(date +%s) - start_ts ))
        python3 scripts/pipeline_timing.py record_download "$model" "$exp" "$elapsed" || true
    fi
}

model_count=0
for model in "${READY_MODELS[@]}"; do
    if [ -n "$MAX_MODELS" ] && [ "$model_count" -ge "$MAX_MODELS" ]; then
        echo "Limite MAX_MODELS=$MAX_MODELS alcanzado, se omiten los modelos restantes."
        break
    fi
    model_count=$((model_count + 1))

    for exp in "${EXPERIMENTS[@]}"; do
        # Si este modelo+experimento ya llego al resultado intermedio
        # (paso 04) o final (paso 05), no hace falta ni siquiera revisar
        # los crudos -- se re-descargarian sin necesidad si, por ejemplo,
        # se borraron a mano para liberar espacio despues de procesar.
        if [ -f "$INTERIM_PROCESSED_DIR/tos_${model}_${exp}.nc" ] || \
           [ -f "$MASKED_DIR/tos_${model}_${exp}.nc" ]; then
            echo "$model $exp: ya procesado (paso 04/05), se omite la descarga de crudos"
            continue
        fi

        echo "Procesando $model $exp ($model_count${MAX_MODELS:+/$MAX_MODELS}) ..."
        download_experiment "$model" "$exp"
    done
done
