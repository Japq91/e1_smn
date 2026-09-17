#!/usr/bin/env bash
# Orquestador principal (entry point único).
# Uso: ./run.sh [STEP_FROM] [STEP_TO] [MAX_MODELS]
#   - Sin args: ejecuta 00-07 (incluye 00b y 01b) sin límite.
#   - Con args: rango específico (ej. 02 07 3: desde descarga, limitado a 3 modelos).
#   - MAX_MODELS: limita a modelos completos (historical + escenarios SSP de
#     config/periods.yaml) según orden en models_catalog_status.csv.
#
# Ejemplo (prueba rápida, de punta a punta salvo QC/inventario):
#   ./run.sh 00 04 2
#   Corre desde el entorno (00) hasta el procesamiento a grilla común (04),
#   limitado a los primeros 2 modelos "completos" del catálogo (MAX_MODELS=2).
#
# Rediseños implementados:
# - Orden interno: remapeo PRIMERO, fusión temporal DESPUÉS. Pesos calculados una sola vez
#   por modelo (gencon/genbil según malla nativa) y cacheados en data/interim/.weights/.
# - Paso 05 (máscara): reescrito a Python por bug en CDO (scripts/05_apply_ocean_mask.py).
# - Gráficos bajo demanda desde: graficos_exploratorios.ipynb sobre data/processed/masked/.
# - Idempotencia: cada paso salta el procesamiento si el archivo de salida ya existe.
# - Nota: paso 00b_build_model_list.py se ejecuta entre 00 y 01 (sin renombrar scripts).
# - Paso 01b (check_model_availability.py): verifica en vivo contra ESGF la
#   disponibilidad real de cada modelo, para informe/model_availability_report.csv
#   (lo usa graficos_exploratorios.ipynb). Idempotente: si ese CSV ya existe no
#   vuelve a consultar ESGF -- se genera una sola vez por maquina/clone; para
#   forzar una nueva verificación hay que borrar ese archivo a mano.
# - Paso 02 ahora es scripts/02_download_all_sources.sh: encadena ESGF (nodo
#   principal) -> ESGF (nodos alternativos, 02b) -> Copernicus CDS (02c, solo
#   lista blanca config/models_copernicus_ssp245_whitelist.csv). 02b/02c ya
#   NO son pasos manuales -- un clone nuevo + run.sh los ejecuta solo.
# - Paso 02 se invoca via scripts/run_download_if_idle.sh: si YA hay una
#   descarga corriendo en otro proceso, no lanza otra (se puede correr
#   run.sh mientras una descarga anterior sigue en curso sin duplicarla).
# - Cada corrida de run.sh, sin importar STEP_FROM/STEP_TO, termina
#   escribiendo un reporte de estado en texto plano en
#   logs/run_report_<timestamp-de-esta-corrida>.txt (ver
#   generate_status_report.py): que modelos ya estan descargados, cuales
#   con descarga parcial, cuales procesados, cuales descargados-pero-sin-
#   procesar, y cuales pendientes via fuentes alternativas.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p logs

RUN_TS="$(date +%Y%m%d_%H%M%S)"
RUN_START_HUMAN="$(date '+%Y-%m-%d %H:%M:%S')"

STEP_ORDER=(00 00b 01 01b 02 03 04 05 06 07)

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

# Directorios y archivos clave (para acortar rutas)
MASKED_DIR="data/processed/masked"
CATALOG_FILE="data/interim/models_catalog_status.csv"
URLS_FILE="data/interim/esgf_file_urls.json"
QC_REPORT="data/processed/qc_report.csv"
INVENTORY_FILE="data/processed/models_inventory_final.csv"
LOG_FILE="logs/pipeline.log"

run_step () {
    local name="$1"; shift
    local idx; idx=$(index_of "$name")
    if [ "$idx" -ge "$FROM_IDX" ] && [ "$idx" -le "$TO_IDX" ]; then
        echo "== Paso $name: $* ==" | tee -a $LOG_FILE
        "$@" 2>&1 | tee -a $LOG_FILE
    fi
}


run_step 00  bash    scripts/00_setup_env.sh
run_step 00b python3 scripts/00b_build_model_list.py config/models_seed_cmip6.csv
run_step 01  python3 scripts/01_query_esgf_catalog.py config/models_seed_cmip6.csv $CATALOG_FILE $URLS_FILE
run_step 01b python3 scripts/check_model_availability.py
run_step 02  bash    scripts/run_download_if_idle.sh
run_step 03  bash    scripts/03_download_ersstv5.sh
run_step 04  bash    scripts/04_process_to_common_grid.sh
run_step 05  python3 scripts/05_apply_ocean_mask.py
run_step 06  python3 scripts/06_qc_checks.py $MASKED_DIR $QC_REPORT
run_step 07  python3 scripts/07_build_inventory_report.py $QC_REPORT $MASKED_DIR $INVENTORY_FILE

echo "Pipeline completo." | tee -a logs/pipeline.log

# Reporte de estado: siempre se genera, sin importar STEP_FROM/STEP_TO.
DOWNLOAD_FLAG_ARGS=()
[ -f data/interim/.download_running_flag ] && DOWNLOAD_FLAG_ARGS=(--downloading)
python3 scripts/generate_status_report.py \
    data/interim/models_catalog_status.csv data/raw/cmip6 data/interim/processed $MASKED_DIR \
    "logs/run_report_${RUN_TS}.txt" "$RUN_START_HUMAN" "$(date '+%Y-%m-%d %H:%M:%S')" \
    "${DOWNLOAD_FLAG_ARGS[@]}"
