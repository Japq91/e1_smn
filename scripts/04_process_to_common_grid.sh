#!/usr/bin/env bash
# ======================================================================
# Procesamiento de CMIP6 a datos listos para cálculo
# Flujo por periodo (historical, ssp245, ssp585) y por chunk crudo:
#
# 1. selvar,tos: se descarta cualquier variable auxiliar del chunk
#    crudo salvo 'tos' (y sus coordenadas). Necesario porque algunos
#    modelos (p. ej. IPSL-CM6A-LR, malla curvilinea tripolar) publican
#    ademas 'area(y,x)' sin atributo 'coordinates' propio -- CDO no
#    sabe a que malla pertenece y aborta ('Unsupported generic
#    coordinates') al generar pesos o regrillar sobre el archivo
#    completo. Se aplica siempre, no solo para ese caso.
# 2. Remapeo de cada chunk (ya filtrado) a la grilla ERSSTv5 (dominio ya
#    recortado) usando pesos precalculados (ver abajo).
# 3. Fusión temporal (mergetime) de los chunks ya regrillados del mismo
#    periodo.
# 4. Recorte temporal: historical → 1850-2014; ssp245/ssp585 → 2015-2100.
# 5. Homogeneización de calendario: si falta el atributo 'calendar', se
#    asigna 'standard'; si existe, se respeta.
# 6. Homogeneización de unidades: conversión K → °C si corresponde.
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
# - Supuesto: la malla nativa no cambia entre experimentos. Si el remap
#   con esos pesos compartidos falla para un periodo puntual, se
#   recalculan pesos propios de ese periodo (WEIGHTS_DIR/<model>_<exp>.nc,
#   ver ensure_period_weights) y se reintenta -- asi un cambio de malla
#   entre historical/ssp245/ssp585 (detectado por el propio error de
#   CDO) no bloquea el resto del modelo.
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

# Unidades: K -> degC si corresponde. Ya no se confia en el atributo
# 'units' declarado: un archivo de GISS-E2-1-G (ssp585) publicado por
# ESGF trae el atributo en 'degC' pero los valores reales siguen en
# Kelvin. Por eso la prueba es por VALOR: se promedia el campo (todo el
# periodo, todo el dominio) en la caja Nino 3.4 (lon 190-240, lat -5/5,
# mismo formato 0-360 que config/domains.yaml); un promedio >= 100 solo
# es posible si el dato sigue en Kelvin. La variable de datos se
# detecta con showname (evita asumir 'tos': ERSSTv5 usa 'sst').
fix_units () {
    local infile="$1" outfile="$2"
    local varname mean_c
    varname=$(cdo -s showname "$infile" 2>/dev/null | tr -s ' ' '\n' \
        | grep -v '^$' | grep -vE '^(lat_bnds|lon_bnds|time_bnds|bnds)$' | head -1)
    mean_c=$(cdo -s output -timmean -fldmean -selname,"$varname" -sellonlatbox,190,240,-5,5 "$infile" 2>/dev/null | tr -d ' ')
    if awk -v v="$mean_c" 'BEGIN{exit !(v < 100)}'; then
        cp "$infile" "$outfile"
    else
        cdo -O -s setattribute,"${varname}"@units=degC -subc,273.15 "$infile" "$outfile"
    fi
}

# Paso 1 (ver encabezado): descarta toda variable auxiliar del chunk
# crudo salvo 'tos'. CDO conserva junto con ella las coordenadas/bounds
# que efectivamente use (nav_lat/nav_lon, lat/lon, etc.); lo que se
# descarta es lo que no está atado a 'tos' via el atributo
# 'coordinates' -- p. ej. 'area(y,x)' en IPSL-CM6A-LR.
select_tos () {
    local infile="$1" outfile="$2"
    cdo -s selvar,tos "$infile" "$outfile"
}

# Genera (por stdout) un archivo de pesos gencon/genbil hacia
# ERSSTV5_RAW a partir de un chunk crudo puntual (ya filtrado con
# select_tos por el llamador), detectando 'unstructured' igual que
# antes. La usan tanto ensure_weights (pesos compartidos por modelo)
# como el fallback por periodo de process_experiment.
gen_weights () {
    local chunk="$1" weights_file="$2"
    local gen_op="genbil"
    local gridtype
    gridtype=$(cdo -s griddes "$chunk" 2>/dev/null | grep -oP 'gridtype\s*=\s*\K\S+' | head -1)
    if [ "$gridtype" = "unstructured" ]; then
        gen_op="gencon"
        echo "  malla no estructurada detectada: usando gencon en vez de genbil" >&2
    fi
    echo "  calculando pesos ($gen_op) a partir de $(basename "$chunk") ..." >&2
    cdo -O -s "$gen_op","$ERSSTV5_RAW" "$chunk" "$weights_file"
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

    local tos_only="$TMPDIR/w_src.nc"
    select_tos "$first_chunk" "$tos_only"
    gen_weights "$tos_only" "$weights_file"
    rm -f "$tos_only"
    echo "$weights_file"
}

# Pesos propios de un periodo (model+exp), en cache aparte del archivo
# compartido del modelo. Solo se calculan como fallback (ver
# process_experiment) cuando el remap con los pesos compartidos falla
# -- eso indica que la malla nativa de ese periodo no coincide con la
# del chunk usado para los pesos compartidos (ver supuesto documentado
# arriba). Sirve ademas como verificacion: si nunca hace falta, es que
# la malla en efecto no cambia entre periodos para ese modelo.
ensure_period_weights () {
    local model="$1" exp="$2" chunk="$3"
    local weights_file="$WEIGHTS_DIR/${model}_${exp}.nc"

    if [ -f "$weights_file" ]; then
        echo "$weights_file"
        return
    fi

    local tos_only="$TMPDIR/w_src.nc"
    select_tos "$chunk" "$tos_only"
    gen_weights "$tos_only" "$weights_file"
    rm -f "$tos_only"
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
    local active_weights="$weights_file" switched_weights=0
    local regridded=() i=0
    for chunk in "${chunks[@]}"; do
        local chunk_tos="$TMPDIR/tos_${i}.nc"
        select_tos "$chunk" "$chunk_tos"
        local rg="$TMPDIR/regrid_${i}.nc"
        if ! cdo -O -s remap,"$ERSSTV5_RAW","$active_weights" "$chunk_tos" "$rg" 2>"$TMPDIR/remap_err.log"; then
            echo "  aviso: fallo el remap de $model $exp con los pesos compartidos del modelo:" >&2
            cat "$TMPDIR/remap_err.log" >&2
            echo "  recalculando pesos propios de $model $exp (verificacion: la malla puede cambiar entre periodos) ..." >&2
            active_weights=$(ensure_period_weights "$model" "$exp" "$chunk")
            switched_weights=1
            cdo -O -s remap,"$ERSSTV5_RAW","$active_weights" "$chunk_tos" "$rg"
        fi
        regridded+=("$rg")
        i=$((i + 1))
    done
    if [ "$switched_weights" -eq 1 ]; then
        echo "  $model $exp: se proceso con pesos propios de este periodo (distintos a los del resto del modelo)" >&2
    fi

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