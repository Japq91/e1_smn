#!/usr/bin/env bash
# Orquestador principal (entry point único).
# Uso: ./run.sh [STEP_FROM] [STEP_TO] [MAX_MODELS]
#   - Sin args: ejecuta 00-07 sin límite.
#   - Con args: rango específico (ej. 02 07 3: desde descarga, limitado a 3 modelos).
#   - MAX_MODELS: limita a modelos completos (historical/ssp245/ssp585) según orden en models_catalog_status.csv.
#
# Rediseños implementados:
# - Orden interno: remapeo PRIMERO, fusión temporal DESPUÉS. Pesos calculados una sola vez
#   por modelo (gencon/genbil según malla nativa) y cacheados en data/interim/.weights/.
# - Paso 05 (máscara): reescrito a Python por bug en CDO (scripts/05_apply_ocean_mask.py).
# - Gráficos bajo demanda desde: graficos_exploratorios.ipynb sobre data/processed/masked/.
# - Idempotencia: cada paso salta el procesamiento si el archivo de salida ya existe.
# - Nota: paso 00b_build_model_list.py se ejecuta entre 00 y 01 (sin renombrar scripts).
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p logs

STEP_ORDER=(00 00b 01 02 03 04 05 06 07)

STEP_FROM="${1:-00}"
STEP_TO="${2:-07}"
MAX_MODELS="${3:-}"   # vacio = sin limite

if [ -n "$MAX_MODELS" ] && ! [[ "$MAX_MODELS" =~ ^[0-9]+$ ]]; then
    echo "MAX_MODELS debe ser un numero entero positivo, se recibio: '$MAX_MODELS'" >&2
    exit 1
fi
export MAX_MODELS

index_of () {
    local target="$1"
    for i in "${!STEP_ORDER[@]}"; do
        if [ "${STEP_ORDER[$i]}" = "$target" ]; then
            echo "$i"
            return
        fi
    done
    echo "-1"
}

FROM_IDX=$(index_of "$STEP_FROM")
TO_IDX=$(index_of "$STEP_TO")

if [ "$FROM_IDX" -lt 0 ] || [ "$TO_IDX" -lt 0 ]; then
    echo "Paso desconocido. Pasos validos: ${STEP_ORDER[*]}" >&2
    exit 1
fi

if [ -n "$MAX_MODELS" ]; then
    echo "Limite de modelos activo: MAX_MODELS=$MAX_MODELS"
fi

run_step () {
    local name="$1"; shift
    local idx; idx=$(index_of "$name")
    if [ "$idx" -ge "$FROM_IDX" ] && [ "$idx" -le "$TO_IDX" ]; then
        echo "== Paso $name: $* ==" | tee -a logs/pipeline.log
        "$@" 2>&1 | tee -a logs/pipeline.log
    fi
}

run_step 00  bash    scripts/00_setup_env.sh
run_step 00b python3 scripts/00b_build_model_list.py ../config/models_seed_cmip6.csv
run_step 01  python3 scripts/01_query_esgf_catalog.py ../config/models_seed_cmip6.csv data/interim/models_catalog_status.csv data/interim/esgf_file_urls.json
run_step 02  bash    scripts/02_download_cmip6_chunks.sh
run_step 03  bash    scripts/03_download_ersstv5.sh
run_step 04  bash    scripts/04_process_to_common_grid.sh
run_step 05  python3 scripts/05_apply_ocean_mask.py
run_step 06  python3 scripts/06_qc_checks.py data/processed/masked data/processed/qc_report.csv
run_step 07  python3 scripts/07_build_inventory_report.py data/processed/qc_report.csv data/processed/masked data/processed/models_inventory_final.csv

echo "Pipeline completo." | tee -a logs/pipeline.log
