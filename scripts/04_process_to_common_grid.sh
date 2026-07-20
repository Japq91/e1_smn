#!/usr/bin/env bash
# ======================================================================
# Procesamiento de CMIP6 a datos listos para cálculo
# Flujo por periodo (historical, ssp245, ssp585) y por chunk crudo:
#
# 1. Remapeo de cada chunk a la grilla ERSSTv5 (dominio ya recortado)
#    usando pesos precalculados (ver abajo).
# 2. Fusión temporal (mergetime) de los chunks ya regrillados del mismo
#    periodo.
# 3. Recorte temporal: historical → 1850-2014; ssp245/ssp585 → 2015-2100.
# 4. Homogeneización de calendario: si falta el atributo 'calendar', se
#    asigna 'standard'; si existe, se respeta.
# 5. Homogeneización de unidades: conversión K → °C si corresponde.
#
# ======================================================================
# Cálculo de pesos (una sola vez por modelo)
# - Los pesos se generan con 'gencon' o 'genbil' según el tipo de malla
#   nativa del modelo, detectado con 'cdo griddes' sobre el primer chunk
#   disponible:
#     * 'unstructured' (p. ej. AWI-CM-1-1-MR) → gencon
#     * cualquier otro → genbil
# - Ambos operadores usan la misma grilla objetivo (ERSSTV5_RAW).
# - Los pesos se guardan en WEIGHTS_DIR/<model>.nc y se reutilizan para
#   todos los experimentos del modelo (historical, ssp245, ssp585).
# - Supuesto: la malla nativa no cambia entre experimentos. Si se rompe,
#   borrar el archivo de pesos para forzar el recalculo.
#
# ======================================================================
# ERSSTv5 (grilla objetivo)
# - No se regrilla ni se fusiona (ya es un solo archivo desde el paso 03).
# - Solo se verifica calendario y unidades para mantener consistencia.
# - Se usa directamente 'ersstv5_region.nc' (ya contiene solo la variable
#   'sst' y el dominio recortado) como referencia espacial.
# ======================================================================
set -euo pipefail
cd "$(dirname "$0")/.."

RAW_DIR="data/raw/cmip6"
ERSSTV5_RAW="data/raw/ersstv5/ersstv5_region.nc"
OUT_DIR="data/interim/processed"
TMPDIR="data/interim/.tmp_process"
WEIGHTS_DIR="data/interim/.weights"
mkdir -p "$OUT_DIR" "$TMPDIR" "$WEIGHTS_DIR"

declare -A YEAR_START=( [historical]=1850 [ssp245]=2015 [ssp585]=2015 )
declare -A YEAR_END=(   [historical]=2014 [ssp245]=2100 [ssp585]=2100 )

if [ ! -f "$ERSSTV5_RAW" ]; then
    echo "FALTA $ERSSTV5_RAW -- corre antes el paso 03 (descarga de ERSSTv5)." >&2
    exit 1
fi

# Calendario: falta el atributo -> se asigna 'standard'; si esta, se
# deja igual.
fix_calendar () {
    local infile="$1" outfile="$2"
    local cal
    cal=$(cdo -s sinfo "$infile" 2>/dev/null | grep -oP 'Calendar\s*=\s*\K\S+' || true)
    if [ -z "$cal" ]; then
        cdo -O -s setcalendar,standard "$infile" "$outfile"
    else
        cp "$infile" "$outfile"
    fi
}

# Unidades: K -> degC si corresponde (CMIP6 casi siempre publica K,
# pero al menos un modelo -- GFDL-ESM4, grid gr -- ya viene en degC).
# La variable de datos se detecta con showname (evita asumir 'tos':
# ERSSTv5 usa 'sst').
fix_units () {
    local infile="$1" outfile="$2"
    local varname unit
    varname=$(cdo -s showname "$infile" 2>/dev/null | tr -s ' ' '\n' \
        | grep -v '^$' | grep -vE '^(lat_bnds|lon_bnds|time_bnds|bnds)$' | head -1)
    unit=$(cdo -s showattribute,"${varname}@units" "$infile" 2>/dev/null | tail -1 | tr -d ' ')
    if [ "$unit" = "K" ]; then
        cdo -O -s chunit,K,degC -subc,273.15 "$infile" "$outfile"
    else
        cp "$infile" "$outfile"
    fi
}

# Devuelve (por stdout) la ruta al archivo de pesos de un modelo,
# calculandolo con gencon/genbil si todavia no existe en cache. Los
# pesos se calculan una unica vez por modelo (no por chunk ni por
# experimento) usando el primer chunk crudo que se encuentre entre
# todos sus experimentos disponibles.
ensure_weights () {
    local model="$1"
    local weights_file="$WEIGHTS_DIR/${model}.nc"

    if [ -f "$weights_file" ]; then
        echo "$weights_file"
        return
    fi

    local first_chunk=""
    for exp in historical ssp245 ssp585; do
        local candidate=("$RAW_DIR/$model/$exp"/*.nc)
        if [ -e "${candidate[0]}" ]; then
            first_chunk="${candidate[0]}"
            break
        fi
    done
    if [ -z "$first_chunk" ]; then
        echo "Sin ningun chunk crudo para $model, no se pueden calcular pesos" >&2
        return 1
    fi

    # gencon/genbil no soporta remapbil sobre malla no estructurada;
    # se detecta el tipo de grilla igual que antes.
    local gen_op="genbil"
    local gridtype
    gridtype=$(cdo -s griddes "$first_chunk" 2>/dev/null | grep -oP 'gridtype\s*=\s*\K\S+' | head -1)
    if [ "$gridtype" = "unstructured" ]; then
        gen_op="gencon"
        echo "  malla no estructurada detectada en $model: usando gencon en vez de genbil" >&2
    fi

    echo "  calculando pesos de $model ($gen_op) a partir de $(basename "$first_chunk") ..." >&2
    cdo -O -s "$gen_op","$ERSSTV5_RAW" "$first_chunk" "$weights_file"

    echo "$weights_file"
}

process_experiment () {
    local model="$1" exp="$2" weights_file="$3"
    local outfile="$OUT_DIR/tos_${model}_${exp}.nc"

    if [ -f "$outfile" ]; then
        echo "Ya procesado, se omite: $(basename "$outfile")"
        return
    fi

    local chunk_dir="$RAW_DIR/$model/$exp"
    local chunks=("$chunk_dir"/*.nc)
    if [ ! -e "${chunks[0]}" ]; then
        echo "Sin datos crudos para $model $exp, se omite" >&2
        return
    fi

    rm -rf "${TMPDIR:?}"/*
    local regridded=() i=0
    for chunk in "${chunks[@]}"; do
        local rg="$TMPDIR/regrid_${i}.nc"
        cdo -O -s remap,"$ERSSTV5_RAW","$weights_file" "$chunk" "$rg"
        regridded+=("$rg")
        i=$((i + 1))
    done

    local merged="$TMPDIR/merged.nc"
    if [ "${#regridded[@]}" -gt 1 ]; then
        cdo -O -s mergetime "${regridded[@]}" "$merged"
    else
        cp "${regridded[0]}" "$merged"
    fi

    local cropped="$TMPDIR/cropped.nc"
    cdo -O -s selyear,${YEAR_START[$exp]}/${YEAR_END[$exp]} "$merged" "$cropped"

    local cal_ok="$TMPDIR/cal_ok.nc"
    fix_calendar "$cropped" "$cal_ok"
    fix_units "$cal_ok" "$outfile"

    rm -rf "${TMPDIR:?}"/*
}

for model_dir in "$RAW_DIR"/*/; do
    [ -d "$model_dir" ] || continue
    model=$(basename "$model_dir")

    # MODELS (variable de entorno opcional): lista de modelos separada
    # por espacios para restringir el procesamiento a esos, sin tocar
    # los demas -- util para procesar los modelos ya descargados
    # mientras otro sigue en curso (02 puede tardar mucho en algunos
    # modelos con muchos chunks, p.ej. AWI-CM-1-1-MR).
    if [ -n "${MODELS:-}" ]; then
        case " $MODELS " in
            *" $model "*) ;;
            *) continue ;;
        esac
    fi

    echo "Preparando pesos de regrilla para $model ..."
    weights_file=$(ensure_weights "$model") || continue

    for exp in historical ssp245 ssp585; do
        echo "Procesando $model $exp ..."
        process_experiment "$model" "$exp" "$weights_file"
    done
done

# ERSSTv5: no se regrilla (es la grilla objetivo) ni se fusiona; solo
# se homogeneiza calendario/unidades para compartir el mismo espacio
# de nombres de salida que los modelos.
if [ ! -f "$OUT_DIR/ersstv5_region.nc" ]; then
    fix_calendar "$ERSSTV5_RAW" "$TMPDIR/ersst_cal.nc"
    fix_units "$TMPDIR/ersst_cal.nc" "$OUT_DIR/ersstv5_region.nc"
    rm -rf "${TMPDIR:?}"/*
fi

rm -rf "$TMPDIR"