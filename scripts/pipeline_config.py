#!/usr/bin/env python3
"""Config global del pipeline (config/periods.yaml) -- fuente unica de
verdad de que escenarios SSP procesa el pipeline. Cualquier script
(Python o Bash, este ultimo invocando este archivo como CLI) que
necesite la lista de escenarios/experimentos debe leerla de aqui, no
tener su propia lista fija en el codigo -- ver 'escenarios' en
config/periods.yaml.

Uso desde Python:
    import pipeline_config as pc
    pc.experiments()          # ['historical', 'ssp245', 'ssp370', 'ssp585']
    pc.scenarios()            # ['ssp245', 'ssp370', 'ssp585']
    pc.experiment_year_range('ssp370')  # (2015, 2100)
    pc.cds_experiment_name('ssp370')    # 'ssp3_7_0'

Uso desde Bash:
    python3 scripts/pipeline_config.py experiments
    python3 scripts/pipeline_config.py scenarios
    python3 scripts/pipeline_config.py year_range ssp370
"""
import re
import sys
from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "periods.yaml"


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
