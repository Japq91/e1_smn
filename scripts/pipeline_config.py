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
