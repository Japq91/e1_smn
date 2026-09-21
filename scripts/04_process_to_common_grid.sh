#!/usr/bin/env bash
# ======================================================================
# Procesamiento de CMIP6 a datos listos para cálculo
# Flujo por periodo (historical + escenarios SSP de config/periods.yaml) y por chunk crudo:
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
# 4. Recorte temporal: rango por experimento leido de config/periods.yaml
#    (historical: descarga_temporal.inicio-referencia_historica.fin;
#    cada SSP: referencia_historica.fin+1-descarga_temporal.fin).
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
#   todos los experimentos del modelo (historical + escenarios SSP configurados).
# - Supuesto: la malla nativa no cambia entre experimentos. Si el remap
#   con esos pesos compartidos falla para un periodo puntual, se
#   recalculan pesos propios de ese periodo (WEIGHTS_DIR/<model>_<exp>.nc,
#   ver ensure_period_weights) y se reintenta -- asi un cambio de malla
#   entre experimentos (detectado por el propio error de
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
CATALOG_CSV="data/interim/models_catalog_status.csv"
INCOMPLETE_LOG="logs/incomplete_merge.log"
mkdir -p "$OUT_DIR" "$TMPDIR" "$WEIGHTS_DIR" logs

# Experimentos a procesar y su rango de anios de recorte: leidos de
# config/periods.yaml (fuente unica de verdad, ver scripts/pipeline_config.py),
# no hardcodeados aqui.
mapfile -t EXPERIMENTS < <(python3 scripts/pipeline_config.py experiments | tr ' ' '\n')
declare -A YEAR_START YEAR_END
for exp in "${EXPERIMENTS[@]}"; do
    read -r y_start y_end < <(python3 scripts/pipeline_config.py year_range "$exp")
    YEAR_START[$exp]="$y_start"
    YEAR_END[$exp]="$y_end"
done

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
    for exp in "${EXPERIMENTS[@]}"; do
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

# Verifica que el .nc de salida tenga EXACTAMENTE la misma lista de
# meses (YYYYMM) que prometen los nombres de los chunks crudos ya
# descargados de $RAW_DIR/<model>/<exp>/ (ver
# pipeline_config.expected_months_from_chunks) -- no un conteo ideal
# fijo de config/periods.yaml. Decision explicita del usuario: un
# modelo puede publicar de verdad menos de lo que este pipeline pide
# (ej. CAMS-CSM1-0: sus SSP terminan en 2099, ESGF nunca va a tener
# 2100) y eso se acepta tal cual, no se descarta para siempre. Lo que
# SI debe fallar esta verificacion es que el propio merge/recorte no
# reproduzca fielmente lo que los chunks ya descargados prometen -- un
# mes perdido o duplicado por mergetime/selyear/regrid (ver el caso
# real de CESM2 con chunks 'gn' y 'gr' duplicando cada mes: la lista
# esperada tiene cada mes una vez, la real los traia dos veces, y la
# comparacion como texto (no como conjunto) lo detecta).
# GRID_LABEL_BY_MODEL (poblado mas abajo, junto a COMPLETE_MODELS,
# desde la misma columna 'grid_label' del catalogo que ya escribio
# 01_query_esgf_catalog.py -- la grilla que 00b eligio para ese modelo)
# se usa aca para que el merge y esta verificacion tomen SOLO los
# chunks de esa grilla, ignorando cualquier archivo de otra grilla que
# haya quedado en el mismo directorio (ver mas abajo, filtro de
# 'chunks'). Sin este filtro un chunk viejo de una grilla distinta (ej.
# CESM2: quedo un archivo 'gn' Y uno 'gr' del mismo periodo completo,
# de una descarga anterior al fix de grid_label en 02b) se mergea igual
# con el resto y duplica cada mes.
declare -A GRID_LABEL_BY_MODEL

months_match () {
    local model="$1" exp="$2" outfile="$3"
    local chunk_dir="$RAW_DIR/$model/$exp"
    local grid_label="${GRID_LABEL_BY_MODEL[$model]:-}"
    local expected actual
    expected=$(python3 scripts/pipeline_config.py expected_months "$chunk_dir" "${YEAR_START[$exp]}" "${YEAR_END[$exp]}" "$grid_label")
    actual=$(cdo -s showdate "$outfile" 2>/dev/null | tr -s ' \n' '\n' | grep -v '^$' \
             | sed -E 's/^([0-9]{4})-([0-9]{2})-.*/\1\2/' | sort -n | tr '\n' ' ')
    [ "$expected" = "${actual% }" ]
}

process_experiment () {
    local model="$1" exp="$2" weights_file="$3"
    local outfile="$OUT_DIR/tos_${model}_${exp}.nc"
    local grid_label="${GRID_LABEL_BY_MODEL[$model]:-}"

    if [ -f "$outfile" ]; then
        if months_match "$model" "$exp" "$outfile"; then
            echo "Ya procesado, se omite: $(basename "$outfile")"
            return
        fi
        echo "  $model $exp: $(basename "$outfile") existe pero no coincide con los meses de sus chunks crudos -- se descarta y se reprocesa" >&2
        echo "$(date -Iseconds) $model $exp: no coincide con los meses de los chunks crudos (salida existente, descartada)" >> "$INCOMPLETE_LOG"
        rm -f "$outfile"
    fi

    local chunk_dir="$RAW_DIR/$model/$exp"
    local chunks
    if [ -n "$grid_label" ]; then
        chunks=("$chunk_dir"/*"_${grid_label}_"*.nc)
    else
        chunks=("$chunk_dir"/*.nc)
    fi
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

    if ! months_match "$model" "$exp" "$outfile"; then
        echo "  aviso: $model $exp: el resultado no coincide con los meses de sus chunks crudos -- " \
             "revisar mergetime/selyear (mes perdido o duplicado en el proceso), se descarta el resultado" >&2
        echo "$(date -Iseconds) $model $exp: no coincide con los meses de los chunks crudos (recien generado, descartado)" >> "$INCOMPLETE_LOG"
        rm -f "$outfile"
    fi

    rm -rf "${TMPDIR:?}"/*
}

# Modelos con 'complete=True' en el catalogo (los unicos que alguna vez
# podrian quedar seleccionados en el inventario final, al tener los 3
# experimentos). Se usa para no procesar por accion carpetas de
# data/raw/cmip6/ que vienen de descargas parciales via fuentes
# alternativas (Copernicus, nodos alt de ESGF) que nunca se completaron
# -- esas a veces traen archivos con metadatos de malla incompletos
# (ej. CESM2, CMCC-CM2-HR4: falta el atributo 'coordinates' en 'tos',
# CDO aborta con 'Unsupported generic coordinates') y no tiene sentido
# ni pueden completarse sin los 3 experimentos de todos modos.
complete_models_csv () {
    python3 -c "
import csv
with open('$CATALOG_CSV', newline='') as f:
    for row in csv.DictReader(f):
        if row.get('complete') == 'True':
            print(row['model'])
"
}
COMPLETE_MODELS=" $(complete_models_csv | tr '\n' ' ') "

# Puebla GRID_LABEL_BY_MODEL (declarada arriba, junto a months_match)
# desde la misma columna 'grid_label' del catalogo -- la grilla que
# 00b_build_model_list.py eligio y que 01/02b ya usaron para buscar
# archivos, para que el merge de aca abajo filtre exactamente igual.
while IFS=$'\t' read -r m g; do
    [ -n "$m" ] && GRID_LABEL_BY_MODEL["$m"]="$g"
done < <(python3 -c "
import csv
with open('$CATALOG_CSV', newline='') as f:
    for row in csv.DictReader(f):
        print(row['model'] + '\t' + row.get('grid_label', ''))
")

for model_dir in "$RAW_DIR"/*/; do
    [ -d "$model_dir" ] || continue
    model=$(basename "$model_dir")

    # MODELS (variable de entorno opcional): lista de modelos separada
    # por espacios para restringir el procesamiento a esos, sin tocar
    # los demas -- util para procesar los modelos ya descargados
    # mientras otro sigue en curso (02 puede tardar mucho en algunos
    # modelos con muchos chunks, p.ej. AWI-CM-1-1-MR). Si no se define,
    # se procesan por defecto todos los 'complete=True' del catalogo
    # (ver COMPLETE_MODELS arriba) -- MODELS es una restriccion manual
    # explicita y tiene prioridad sobre ese filtro automatico.
    if [ -n "${MODELS:-}" ]; then
        case " $MODELS " in
            *" $model "*) ;;
            *) continue ;;
        esac
    else
        case "$COMPLETE_MODELS" in
            *" $model "*) ;;
            *)
                echo "  $model: no esta 'complete=True' en el catalogo, se omite (descarga parcial, nunca seleccionable sin los 3 experimentos)" >&2
                continue
                ;;
        esac
    fi

    echo "Preparando pesos de regrilla para $model ..."
    weights_file=$(ensure_weights "$model") || continue

    for exp in "${EXPERIMENTS[@]}"; do
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