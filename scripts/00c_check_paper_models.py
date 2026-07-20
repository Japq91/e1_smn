#!/usr/bin/env python3
"""Verifica si los modelos CMIP6 citados en los papers/tesis de
files_MD/ estan presentes en config/models_seed_cmip6.csv (paso 00c
-- diagnostico. NO forma parte de la secuencia principal del
pipeline; se corre a mano cuando se agregan papers nuevos o se
regenera el seed CSV).

Escanea los .md en busca de nombres de source_id conocidos de CMIP6
(lista embebida abajo, no exhaustiva de las ~100+ variantes del
vocabulario CMIP6 completo, pero cubre los que efectivamente aparecen
citados en el corpus de este proyecto) y compara contra el CSV
generado por 00b_build_model_list.py.

Los modelos que aparecen en algun paper pero NO en el seed CSV se
escriben en config/models_missing_from_esgf.csv -- son los candidatos
a buscar por una via alternativa (ver 02b_search_alt_esgf_nodes.py y
02c_download_copernicus_cds.py).

Uso:
    python3 00c_check_paper_models.py ../files_MD ../config/models_seed_cmip6.csv ../config/models_missing_from_esgf.csv
"""
import csv
import re
import sys
from pathlib import Path

# Lista de source_id de CMIP6 conocidos por este proyecto. Ampliar esta
# lista si se agregan papers nuevos que citen modelos no incluidos aqui.
KNOWN_SOURCE_IDS = [
    "ACCESS-CM2", "ACCESS-ESM1-5", "AWI-CM-1-1-MR", "AWI-ESM-1-1-LR",
    "BCC-CSM2-MR", "BCC-ESM1", "CAMS-CSM1-0", "CAS-ESM2-0",
    "CESM2", "CESM2-FV2", "CESM2-WACCM", "CESM2-WACCM-FV2", "CIESM",
    "CMCC-CM2-HR4", "CMCC-CM2-SR5", "CMCC-ESM2",
    "CNRM-CM6-1", "CNRM-CM6-1-HR", "CNRM-ESM2-1",
    "CanESM5", "CanESM5-1", "CanESM5-CanOE",
    "E3SM-1-0", "E3SM-1-1", "E3SM-1-1-ECA", "E3SM-2-0",
    "EC-Earth3", "EC-Earth3-AerChem", "EC-Earth3-CC", "EC-Earth3-Veg", "EC-Earth3-Veg-LR",
    "FGOALS-f3-L", "FGOALS-g3", "FIO-ESM-2-0",
    "GFDL-CM4", "GFDL-ESM4",
    "GISS-E2-1-G", "GISS-E2-1-G-CC", "GISS-E2-1-H", "GISS-E2-2-G", "GISS-E2-2-H",
    "HadGEM3-GC31-LL", "HadGEM3-GC31-MM",
    "IITM-ESM", "INM-CM4-8", "INM-CM5-0",
    "IPSL-CM5A2-INCA", "IPSL-CM6A-LR",
    "KACE-1-0-G", "KIOST-ESM", "MCM-UA-1-0",
    "MIROC-ES2H", "MIROC-ES2L", "MIROC6",
    "MPI-ESM-1-2-HAM", "MPI-ESM1-2-HR", "MPI-ESM1-2-LR",
    "MRI-ESM2-0", "NESM3", "NorCPM1", "NorESM2-LM", "NorESM2-MM",
    "SAM0-UNICON", "TaiESM1", "UKESM1-0-LL", "UKESM1-1-LL",
]

_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_-])("
    + "|".join(re.escape(m) for m in sorted(KNOWN_SOURCE_IDS, key=len, reverse=True))
    + r")(?![A-Za-z0-9_-])"
)


def scan_papers(md_dir: str) -> dict[str, set[str]]:
    """Devuelve {modelo: {archivos .md donde aparece}}."""
    mentioned: dict[str, set[str]] = {}
    for f in sorted(Path(md_dir).glob("*.md")):
        text = f.read_text(errors="ignore")
        for m in set(_PATTERN.findall(text)):
            mentioned.setdefault(m, set()).add(f.name)
    return mentioned


def main(md_dir: str, seed_csv: str, out_missing_csv: str) -> None:
    mentioned = scan_papers(md_dir)

    with open(seed_csv, newline="") as f:
        seed_models = {row["model"] for row in csv.DictReader(f)}

    paper_models = set(mentioned)
    missing = sorted(paper_models - seed_models)
    extra = sorted(seed_models - paper_models)

    print(f"Modelos mencionados en {md_dir}/: {len(paper_models)}", file=sys.stderr)
    print(f"Modelos en {seed_csv}: {len(seed_models)}", file=sys.stderr)
    print(f"\nFaltan en el seed CSV (candidatos a fuente alternativa): {len(missing)}", file=sys.stderr)
    for m in missing:
        print(f"  {m} <- {', '.join(sorted(mentioned[m]))}", file=sys.stderr)
    print(f"\nEn el seed CSV pero ningun paper los menciona: {len(extra)}", file=sys.stderr)
    for m in extra:
        print(f"  {m}", file=sys.stderr)

    Path(out_missing_csv).parent.mkdir(parents=True, exist_ok=True)
    with open(out_missing_csv, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["model", "mentioned_in_papers"])
        for m in missing:
            writer.writerow([m, ";".join(sorted(mentioned[m]))])

    print(f"\nLista de candidatos escrita en {out_missing_csv}", file=sys.stderr)


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit("uso: 00c_check_paper_models.py <files_MD_dir> <models_seed_cmip6.csv> <out_missing.csv>")
    main(sys.argv[1], sys.argv[2], sys.argv[3])
