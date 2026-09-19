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
    # Frontend "Metagrid" (React) de la nueva infraestructura ESGF2 --
    # esgf-node.llnl.gov/esg-search/search y esgf-node.ornl.gov/esg-search/search
    # ya no sirven el JSON clasico (devuelven el HTML de la app), pero el
    # proxy interno de metagrid si habla el mismo protocolo Solr
    # (verificado a mano: mismos parametros, misma forma de respuesta,
    # 'url' con el formato 'url|mime|service'). Encontrado por el usuario
    # via la UI de busqueda en https://metagrid.esgf-west.org/search/cmip6/.
    "https://metagrid.esgf-west.org/proxy/search",
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
                       max_retries: int = ESGF_MAX_RETRIES, page_size: int = 500) -> list[dict]:
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
    EC-Earth3-Veg/ssp370, verificado)."""
    docs: list[dict] = []
    offset = 0
    while True:
        page_params = {**params, "limit": page_size, "offset": offset}
        r = esgf_get(url, page_params, timeout=timeout, max_retries=max_retries)
        batch = r.json()["response"]["docs"]
        docs.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
    return docs


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


def url_is_alive(url: str, timeout: float = 10) -> bool:
    """HEAD rapido (sin bajar el archivo) para confirmar que un link de
    descarga responde de verdad. ESGF a veces indexa un archivo cuyo
    link ya no esta vivo (nodo reorganizado, replica caida, etc.) --
    confiar solo en que el buscador lo devolvio no garantiza que se
    pueda descargar. Un solo intento, sin reintentos: si este mirror no
    responde, el llamador prueba el siguiente (ver pick_first_live_url)."""
    try:
        r = requests.head(url, timeout=timeout, allow_redirects=True)
        return r.status_code < 400
    except requests.RequestException:
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
        sys.exit("uso: pipeline_config.py {experiments|scenarios|year_range <exp>}")
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
    else:
        sys.exit(f"comando desconocido: {cmd!r}")
