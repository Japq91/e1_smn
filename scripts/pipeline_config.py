#!/usr/bin/env python3
"""Config global del pipeline (config/periods.yaml) -- fuente unica de
verdad de que escenarios SSP procesa el pipeline. Cualquier script
(Python o Bash, este ultimo invocando este archivo como CLI) que
necesite la lista de escenarios/experimentos debe leerla de aqui, no
tener su propia lista fija en el codigo -- ver 'escenarios' en
config/periods.yaml.

Tambien centraliza el manejo de rate limit de ESGF (ver esgf_get() mas
abajo): todo script que consulte ESGF via requests.get(...) deberia
usar pc.esgf_get(...) en su lugar.

Uso desde Python:
    import pipeline_config as pc
    pc.experiments()          # ['historical', 'ssp245', 'ssp370', 'ssp585']
    pc.scenarios()            # ['ssp245', 'ssp370', 'ssp585']
    pc.experiment_year_range('ssp370')  # (2015, 2100)
    pc.cds_experiment_name('ssp370')    # 'ssp3_7_0'
    pc.esgf_get(url, params)  # requests.get(...) con reintentos ante 429/5xx

Uso desde Bash:
    python3 scripts/pipeline_config.py experiments
    python3 scripts/pipeline_config.py scenarios
    python3 scripts/pipeline_config.py year_range ssp370
"""
import random
import re
import sys
import time
from pathlib import Path

import requests
import yaml

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "periods.yaml"

# Nodos indice alternativos de la federacion ESGF (ademas del principal,
# LLNL, que cada script define con su propio ESGF_SEARCH_URL). Vive aca
# -- no en periods.yaml -- para que 00b_build_model_list.py y
# 02b_search_alt_esgf_nodes.py compartan una sola lista en vez de tener
# cada uno la suya. Verificar cuales estan activos al momento de usar
# esto -- la federacion cambia con el tiempo.
ALT_ESGF_SEARCH_URLS = [
    "https://esgf.ceda.ac.uk/esg-search/search",
    "https://esgf-data.dkrz.de/esg-search/search",
    "https://esgf-node.ipsl.upmc.fr/esg-search/search",
    "https://esg-dn1.nsc.liu.se/esg-search/search",
    "https://esgf.nci.org.au/esg-search/search",
    # Nodos que migraron su frontend a "Metagrid" (React): su endpoint
    # clasico '/esg-search/search' devuelve el HTML de la app en vez del
    # JSON de Solr, pero exponen el mismo protocolo Solr clasico bajo
    # '/proxy/search' (verificado a mano: mismos parametros, misma forma
    # de respuesta, 'url' con el formato 'url|mime|service'). OJO: esto
    # es especifico de cada nodo -- no asumir que todo nodo Metagrid usa
    # '/proxy/search', hay que probarlo (esgf-node.llnl.gov, el nodo
    # principal, en cambio SI sigue sirviendo JSON en su endpoint clasico,
    # verificado -- no todos migraron igual ni al mismo tiempo).
    #   - metagrid.esgf-west.org: encontrado por el usuario via la UI de
    #     busqueda en https://metagrid.esgf-west.org/search/cmip6/.
    #   - esgf-node.ornl.gov y esgf-metagrid.cloud.dkrz.de: encontrados
    #     al revisar si el mismo patron aplicaba a otros nodos conocidos
    #     de la federacion, a raiz de que el usuario pregunto por que no
    #     se usaba ORNL (aparecia seguido como data_node en los archivos
    #     encontrados, pero nunca se habia consultado como indice).
    "https://metagrid.esgf-west.org/proxy/search",
    "https://esgf-node.ornl.gov/proxy/search",
    "https://esgf-metagrid.cloud.dkrz.de/proxy/search",
]

# Reintentos ante 429 (rate limit) y errores 5xx/de red de los nodos
# ESGF -- verificado en la practica (nodo de ORNL devolviendo 429 tras
# una racha de peticiones seguidas). ESGF_MAX_RETRIES intentos en
# total, con backoff exponencial con techo ESGF_BACKOFF_CAP_S entre
# cada uno (o el valor del header 'Retry-After' si el servidor lo manda).
ESGF_MAX_RETRIES = 6
ESGF_BACKOFF_BASE_S = 5
ESGF_BACKOFF_CAP_S = 120


def _backoff_seconds(attempt: int) -> float:
    return min(ESGF_BACKOFF_BASE_S * (2 ** (attempt - 1)), ESGF_BACKOFF_CAP_S) + random.uniform(0, 1)


def esgf_get(url: str, params: dict, timeout: float = 60, max_retries: int = ESGF_MAX_RETRIES) -> requests.Response:
    """GET contra un nodo ESGF con reintentos ante 429/5xx/fallos de red.
    Usar esto en vez de requests.get(...) directo para CUALQUIER consulta
    a ESGF (00b, 01, 02b, check_model_availability) -- centraliza el
    manejo de rate limit en un solo lugar en vez de que cada script
    reintente (o no) a su manera.

    Un 429/5xx en el ULTIMO intento se propaga via raise_for_status()
    (falla con un error claro); cualquier otro codigo de error (4xx que
    no sea 429) falla de inmediato, sin reintentar -- no tiene sentido
    reintentar un error de parametros."""
    last_exc: requests.RequestException | None = None
    for attempt in range(1, max_retries + 1):
        try:
            r = requests.get(url, params=params, timeout=timeout)
        except requests.RequestException as e:
            last_exc = e
            if attempt == max_retries:
                raise
            wait = _backoff_seconds(attempt)
            print(f"  fallo de red contra {url} ({e}) -- reintento {attempt}/{max_retries} en {wait:.0f}s",
                  file=sys.stderr)
            time.sleep(wait)
            continue

        if r.status_code == 429 or r.status_code >= 500:
            if attempt == max_retries:
                r.raise_for_status()
            retry_after = r.headers.get("Retry-After")
            wait = float(retry_after) if retry_after else _backoff_seconds(attempt)
            print(f"  ESGF respondio {r.status_code} en {url} -- reintento {attempt}/{max_retries} en {wait:.0f}s",
                  file=sys.stderr)
            time.sleep(wait)
            continue

        r.raise_for_status()  # 4xx que no es 429: falla ya, no tiene sentido reintentar
        return r

    raise last_exc or requests.RequestException(f"agotados los reintentos contra {url}")


def esgf_get_all_docs(url: str, params: dict, timeout: float = 60,
                       max_retries: int = ESGF_MAX_RETRIES, page_size: int = 500,
                       retry_full_on_truncate: int = 0) -> list[dict]:
    """Igual que esgf_get(...).json()["response"]["docs"], pero pagina
    (offset/limit) hasta traer TODOS los docs que matchean la consulta,
    no solo los primeros 'page_size'. Usar esto en vez de un limit fijo
    para cualquier busqueda de archivos (type=File) -- un archivo puede
    estar replicado en varios nodos de datos a la vez, y ademas algunos
    modelos publican corridas extendidas mas alla del rango que pide
    este pipeline (ej. EC-Earth3-Veg ssp370: 458 registros repartidos en
    3 nodos, uno de ellos con datos hasta el 2300 en vez de 2100).

    BUG real encontrado en produccion: con un limit fijo de 200 (el
    valor que tenia antes esgf_file_search), Solr devuelve un
    subconjunto arbitrario de esos 458 registros -- ni ordenado por
    archivo ni por fecha -- y el resultado, tras deduplicar por nombre
    de archivo, quedaba faltando archivos de anios sueltos (no un
    tramo contiguo al final). El sintoma no aparecia en la busqueda
    misma (no tira error, 'se completa' con el subconjunto que le
    toco) sino recien en 06_qc_checks.py, como una serie de tiempo mas
    corta que la esperada (852 meses en vez de 1032 para
    EC-Earth3-Veg/ssp370, verificado).

    Algunos modelos publican TANTOS registros (ej. CanESM5: miles de
    datasets entre todos sus miembros/experimentos/MIPs) que la
    paginacion misma choca con un limite de "paginacion profunda" del
    lado del servidor (verificado: esgf-node.llnl.gov, a partir de
    offset=10000, responde 422 Unprocessable Content en vez de la
    pagina siguiente). Si eso pasa, se corta la paginacion ahi y se
    devuelve lo juntado hasta ese punto (con un aviso) en vez de
    propagar el error y tirar abajo el script que llamo a esto -- para
    una consulta de existencia/disponibilidad, los primeros miles de
    registros ya alcanzan de sobra para cubrir los experimentos que
    este pipeline necesita.

    BUG real encontrado en produccion (2026-09): para busquedas a nivel
    de ARCHIVO (01_query_esgf_catalog.py/02b_search_alt_esgf_nodes.py,
    donde la lista completa si importa -- a diferencia del caso de
    arriba), un corte de red transitorio a mitad de la paginacion
    (agotando ya los max_retries de esa sola pagina) se aceptaba en
    silencio como 'la lista completa de archivos', marcando el modelo
    como 'completo=True' con un merge que iba a quedar con un hueco real
    (verificado: EC-Earth3 historical encontro 107, 121 o 165 archivos
    -- el total real -- segun la corrida, sin ningun error visible).
    retry_full_on_truncate (>0 para busquedas de archivo, 0 -- default,
    sin cambio de comportamiento -- para las de solo-existencia como
    00b_build_model_list.py) reintenta la PAGINACION COMPLETA desde
    offset=0 esa cantidad de veces si la anterior se corto por error,
    ya que el corte es transitorio (una repeticion inmediata suele
    encontrar la red sana de nuevo) y no un limite real del servidor."""
    for attempt in range(retry_full_on_truncate + 1):
        docs: list[dict] = []
        offset = 0
        truncated = False
        while True:
            page_params = {**params, "limit": page_size, "offset": offset}
            try:
                r = esgf_get(url, page_params, timeout=timeout, max_retries=max_retries)
            except requests.HTTPError as e:
                print(f"  {url}: parando la paginacion en offset={offset} ({e}) -- "
                      f"se sigue con los {len(docs)} registros ya juntados", file=sys.stderr)
                truncated = True
                break
            batch = r.json()["response"]["docs"]
            docs.extend(batch)
            if len(batch) < page_size:
                break
            offset += page_size
        if not truncated or attempt == retry_full_on_truncate:
            return docs
        print(f"  {url}: paginacion incompleta, reintentando la busqueda completa "
              f"desde offset=0 (intento {attempt + 2}/{retry_full_on_truncate + 1}) ...",
              file=sys.stderr)
    return docs


HISTORICAL_EQUIVALENTS = {"historical", "hist-1950"}
# 'historical' es el experimento DECK estandar (1850-2014). 'hist-1950'
# es el equivalente de HighResMIP (1950-2014, arranca de un spinup
# propio, no del piControl estandar) -- decision explicita del usuario:
# no hace falta que arranque en 1850, 1950 en adelante sirve igual para
# el periodo de referencia de este proyecto (1981-2014). OJO: los
# modelos que solo tienen hist-1950 (no historical) nunca tienen
# ningun SSP publicado (corren 'highres-future' en su lugar, protocolo
# HighResMIP) -- verificado en la practica, no es cuestion de buscar
# mas. Esto solo afecta si "tiene historical" para fines de
# clasificacion/reporte (informe/model_availability_report.*); NO
# cambia que grilla elige 00b para el seed (pick_coarsest_grid sigue
# exigiendo 'historical' literal + los 3 SSP bajo la misma grilla para
# seleccionar un modelo -- y estos modelos igual no calificarian, por
# no tener ningun SSP).


def has_historical(experiments: set[str]) -> str | None:
    """Devuelve cual de HISTORICAL_EQUIVALENTS esta presente (prefiere
    'historical' si estan ambos), o None si no hay ninguno."""
    found = experiments & HISTORICAL_EQUIVALENTS
    if not found:
        return None
    return "historical" if "historical" in found else sorted(found)[0]


_FILE_YEAR_RANGE_RE = re.compile(r"_(\d{4})\d{2}-(\d{4})\d{2}\.nc$")


def file_overlaps_range(filename: str, year_start: int, year_end: int) -> bool:
    """True si el archivo (por su nombre, convencion CMOR de CMIP6:
    '..._YYYYMM-YYYYMM.nc') cae al menos parcialmente dentro del rango
    de anios que este pipeline necesita para ese experimento (ver
    experiment_year_range). Si el nombre no trae un rango de fechas
    reconocible, se conserva (mejor no descartarlo a ciegas).

    Filtra de entrada corridas extendidas mas alla de lo pedido (caso
    real: EC-Earth3-Veg publica ssp370/ssp245/ssp585 hasta el anio 2300
    en el nodo esgf-data04.diasjp.net, pero el pipeline solo usa hasta
    2100) -- sin este filtro, esgf_file_search igual encontraba esos
    archivos, gastaba una verificacion HEAD por cada uno y imprimia un
    aviso 'se descarta' para los que ya no tenian mirror vivo, aunque
    de todas formas nunca se iban a descargar."""
    m = _FILE_YEAR_RANGE_RE.search(filename)
    if not m:
        return True
    f_start, f_end = int(m.group(1)), int(m.group(2))
    return f_start <= year_end and f_end >= year_start


def _file_year_span(filename: str) -> tuple[int, int] | None:
    m = _FILE_YEAR_RANGE_RE.search(filename)
    return (int(m.group(1)), int(m.group(2))) if m else None


_FILE_YEARMONTH_RANGE_RE = re.compile(r"_(\d{6})-(\d{6})\.nc$")


def expected_months_from_chunks(chunk_dir, year_start: int, year_end: int,
                                 grid_label: str | None = None) -> set[int]:
    """Meses (como entero YYYYMM) que DEBERIAN quedar en el merge+recorte
    de 04_process_to_common_grid.sh, derivados de los rangos de fecha en
    los nombres de los chunks CRUDOS que 01/02b ya encontraron y 02 ya
    descargo (fuente de verdad: lo que hay en disco), recortados al
    rango configurado (year_start/year_end) igual que 'cdo selyear'.

    grid_label (si se pasa) filtra el glob a solo los archivos de esa
    grilla ('*_<grid_label>_*.nc') -- debe ser LA MISMA grilla que
    selecciono 00b_build_model_list.py para ese modelo (ver
    config/models_seed_cmip6.csv / la columna grid_label del catalogo),
    para que "lo que se espera" coincida con lo que 04 realmente va a
    mergear (ver GRID_LABEL_BY_MODEL en 04_process_to_common_grid.sh).
    Sin este filtro, un chunk de una grilla vieja que quedo en disco de
    una descarga anterior (ej. CESM2: un archivo 'gn' y uno 'gr' del
    mismo periodo completo, de antes de que 02b filtrara por grid_label)
    se cuenta igual para "lo esperado", aunque nunca deberia haberse
    mergeado con el resto.

    A proposito esto NO es un conteo ideal fijo de config/periods.yaml:
    un modelo puede publicar de verdad menos de lo que este pipeline
    pide (ej. CAMS-CSM1-0: sus escenarios SSP terminan en 2099, ESGF
    nunca va a tener 2100 -- decision explicita del usuario: aceptarlo
    tal cual, no excluirlo) y esa limitacion es real, no un hueco para
    reintentar. Lo unico que debe fallar la verificacion de 04 es que
    el propio merge/recorte no reproduzca fielmente lo que los chunks
    ya descargados (de la grilla correcta) prometen -- un mes perdido o
    duplicado por el proceso de mergetime/selyear/regrid. Que la
    busqueda (01/02b) haya encontrado TODOS los archivos que existen de
    verdad en ESGF es responsabilidad de esa etapa (ver
    esgf_get_all_docs), no de esta."""
    pattern = f"*_{grid_label}_*.nc" if grid_label else "*.nc"
    months: set[int] = set()
    for f in sorted(Path(chunk_dir).glob(pattern)):
        m = _FILE_YEARMONTH_RANGE_RE.search(f.name)
        if not m:
            continue
        f_start, f_end = int(m.group(1)), int(m.group(2))
        y, mo = divmod(f_start, 100)
        end_y, end_mo = divmod(f_end, 100)
        while (y, mo) <= (end_y, end_mo):
            if year_start <= y <= year_end:
                months.add(y * 100 + mo)
            mo += 1
            if mo > 12:
                mo, y = 1, y + 1
    return months


def verify_files_by_boundary_sample(by_filename: dict[str, list[str]], experiment: str,
                                     year_start: int, year_end: int, timeout: float = 10) -> dict[str, list[str]]:
    """Decision explicita del usuario (no verificar cada chunk uno por
    uno, es demasiado lento para modelos con muchos archivos por
    experimento -- ver EC-Earth3-Veg, 165 archivos solo de historical):
    en vez de hacer un HEAD por archivo, verifica UN SOLO archivo -- el
    que cubre el anio de empalme entre historical y los SSP (el ultimo
    anio de historical, o el primer anio de cada SSP) -- y si ese
    responde, confia en que el resto de archivos del mismo
    experimento/publicacion tambien va a responder, sin verificarlos.

    Riesgo aceptado conscientemente: si un proveedor retracto solo
    ALGUNOS anios (no el archivo de empalme), esto no lo detecta aca --
    recien se veria como serie corta en 06_qc_checks.py, igual que
    antes de que existiera esta verificacion de link vivo. Si el
    archivo de empalme no responde, el experimento entero se da por no
    encontrado (no se reintenta verificando todo uno por uno)."""
    if not by_filename:
        return {}

    boundary_year = year_end if experiment == "historical" else year_start

    covering = [fn for fn in by_filename if (span := _file_year_span(fn)) and span[0] <= boundary_year <= span[1]]
    if covering:
        boundary_filename = covering[0]
    else:
        def _distance(fn: str) -> float:
            span = _file_year_span(fn)
            if span is None:
                return float("inf")
            f_start, f_end = span
            if boundary_year < f_start:
                return f_start - boundary_year
            if boundary_year > f_end:
                return boundary_year - f_end
            return 0
        boundary_filename = min(by_filename, key=_distance)

    live = pick_first_live_url(by_filename[boundary_filename], timeout=timeout)
    if not live:
        return {}

    verified = {boundary_filename: live}
    for fn, urls in by_filename.items():
        if fn != boundary_filename:
            verified[fn] = urls  # sin verificar -- ver docstring
    return verified


def url_is_alive(url: str, timeout: float = 10, attempts: int = 3) -> bool:
    """HEAD rapido (sin bajar el archivo) para confirmar que un link de
    descarga responde de verdad. ESGF a veces indexa un archivo cuyo
    link ya no esta vivo (nodo reorganizado, replica caida, etc.) --
    confiar solo en que el buscador lo devolvio no garantiza que se
    pueda descargar.

    Reintenta (hasta 'attempts' veces, con una pausa corta) solo ante
    fallos que pueden ser transitorios: timeout, error de conexion, 429
    o 5xx. Un 4xx real (404, 403, ...) se da por muerto de inmediato,
    sin reintentar -- eso si es una respuesta definitiva del servidor,
    no un hipo de red. BUG evitado: antes esto era un solo intento sin
    reintento, asi que un timeout puntual (nodo lento, no caido) bastaba
    para descartar un archivo -- y de ahi, si le pasaba a la mayoria de
    los archivos de un modelo, el modelo entero quedaba marcado como no
    disponible por una falla momentanea, no por falta real de datos."""
    for attempt in range(attempts):
        try:
            r = requests.head(url, timeout=timeout, allow_redirects=True)
        except requests.RequestException:
            pass
        else:
            if r.status_code < 400:
                return True
            if r.status_code != 429 and r.status_code < 500:
                return False  # 4xx real (404, 403, ...): no reintenta
        if attempt < attempts - 1:
            time.sleep(2 * (attempt + 1))
    return False


def pick_first_live_url(urls: list[str], timeout: float = 10) -> list[str] | None:
    """Prueba los mirrors de un archivo uno por uno (HEAD) y devuelve la
    lista reordenada con el primero que responde al frente -- o None si
    ninguno responde. Para en el primero vivo, no revisa el resto."""
    for i, u in enumerate(urls):
        if url_is_alive(u, timeout=timeout):
            return [u] + urls[:i] + urls[i + 1:]
    return None


def load() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text())


def scenarios() -> list[str]:
    """Escenarios SSP futuros (sin 'historical'), en el orden de config/periods.yaml."""
    return list(load()["escenarios"])


def experiments() -> list[str]:
    """'historical' + escenarios, en ese orden -- lista completa de
    experimentos que el pipeline debe descargar/procesar."""
    return ["historical", *scenarios()]


def row_is_complete(row: dict) -> bool:
    """True solo si la fila del catalogo (models_catalog_status.csv)
    tiene 'True' explicito para TODOS los experimentos actualmente
    requeridos por config/periods.yaml -- no confia en la columna
    'complete' ya escrita en el CSV, que puede haber quedado
    desactualizada. Caso real observado: filas resueltas cuando el
    config todavia tenia 2 escenarios SSP quedan con 'complete=True'
    pero con la celda del escenario agregado despues (p.ej. ssp370)
    vacia en vez de 'False' -- sin este chequeo, 02_download_cmip6_chunks.sh
    las trataba como completas e intentaba (sin exito, en cada corrida)
    descargar un escenario que ese modelo nunca tuvo publicado."""
    return all(row.get(exp) == "True" for exp in experiments())


def experiment_year_range(exp: str) -> tuple[int, int]:
    """(anio_inicio, anio_fin), ambos inclusive, de descarga/recorte
    temporal para un experimento. 'historical' va de
    descarga_temporal.inicio a referencia_historica.fin; cualquier
    escenario SSP va del anio siguiente a referencia_historica.fin
    hasta descarga_temporal.fin (mismo rango para todos los SSP,
    estandar de ScenarioMIP: 2015-2100)."""
    cfg = load()
    hist_end = cfg["referencia_historica"]["fin"]
    if exp == "historical":
        return cfg["descarga_temporal"]["inicio"], hist_end
    return hist_end + 1, cfg["descarga_temporal"]["fin"]


def cds_experiment_name(exp: str) -> str:
    """Nombre de experimento en el formato que usa Copernicus CDS:
    'historical' se mantiene igual; 'sspXYZ' se transforma en
    'sspX_Y_Z' (verificado contra el archivo de restricciones del
    dataset 'projections-cmip6': los SSP usan guion bajo entre
    digitos, no el nombre corto de ESGF)."""
    if exp == "historical":
        return exp
    m = re.match(r"ssp(\d)(\d)(\d)$", exp)
    if not m:
        raise ValueError(f"formato de escenario SSP no reconocido: {exp!r}")
    return f"ssp{'_'.join(m.groups())}"


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("uso: pipeline_config.py {experiments|scenarios|year_range <exp>|expected_months <chunk_dir> <year_start> <year_end>}")
    cmd = sys.argv[1]
    if cmd == "experiments":
        print(" ".join(experiments()))
    elif cmd == "scenarios":
        print(" ".join(scenarios()))
    elif cmd == "year_range":
        if len(sys.argv) != 3:
            sys.exit("uso: pipeline_config.py year_range <experimento>")
        start, end = experiment_year_range(sys.argv[2])
        print(f"{start} {end}")
    elif cmd == "expected_months":
        if len(sys.argv) not in (5, 6):
            sys.exit("uso: pipeline_config.py expected_months <chunk_dir> <year_start> <year_end> [grid_label]")
        grid_label = sys.argv[5] if len(sys.argv) == 6 else None
        months = expected_months_from_chunks(sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), grid_label)
        print(" ".join(str(m) for m in sorted(months)))
    else:
        sys.exit(f"comando desconocido: {cmd!r}")
