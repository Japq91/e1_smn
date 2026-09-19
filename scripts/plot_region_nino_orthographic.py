#!/usr/bin/env python3
"""Mapa de contexto de las cajas Nino, en proyeccion Ortografica
(complementario a informe/region_nino.png, que usa PlateCarree).

A diferencia de ese mapa, el centro de la proyeccion no es un valor
fijo: se calcula a partir del propio dominio espacial de los NetCDF ya
homogeneizados en data/processed/masked/ (mismo dominio para los 48
modelos y ERSSTv5, ya que el paso 04 regrilla todo a esa misma grilla,
ver scripts/04_process_to_common_grid.sh), tomando el punto medio de
sus coordenadas lat/lon. Esto evita que el centro de la proyeccion y el
dominio realmente descargado/procesado queden desincronizados si
config/domains.yaml cambia en el futuro.

Dibuja las cuatro cajas clasicas del ENOS (Nino 4, Nino 3, Nino 3.4,
Nino 1+2); Nino 3.4 y Nino 1+2 -las dos que config/domains.yaml define
y que efectivamente usa este proyecto- se resaltan con borde solido
grueso, mientras que Nino 4 y Nino 3 (no usadas en este proyecto, solo
de referencia geografica) se dibujan con borde punteado mas fino.

Requiere cartopy (no forma parte de environment.yml del pipeline
principal; ver environment.yml para el entorno de graficos opcional).

Uso:
    python3 plot_region_nino_orthographic.py [archivo_salida.png]
"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # sin GUI -- pensado para correr en un cluster sin interfaz grafica

import cartopy.crs as ccrs  # noqa: E402
import cartopy.feature as cfeature  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import netCDF4 as nc  # noqa: E402
import numpy as np  # noqa: E402
import yaml  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent.parent
MASKED_DIR = BASE_DIR / "data/processed/masked"
DOMAINS_YAML = BASE_DIR / "config/domains.yaml"
DEFAULT_OUT = BASE_DIR / "figures/region_nino_orthographic.png"

# Cajas clasicas del ENOS, longitud en 0-360 (mismo formato que
# config/domains.yaml). Nino 4 y Nino 3 no estan en domains.yaml (este
# proyecto no las usa) y se definen aqui solo para dar contexto
# geografico, igual que en informe/region_nino.png.
NINO4 = dict(lon_min=160.0, lon_max=210.0, lat_min=-5.0, lat_max=5.0)
NINO3 = dict(lon_min=210.0, lon_max=270.0, lat_min=-5.0, lat_max=5.0)


def load_domains(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def netcdf_domain_center(masked_dir: Path) -> tuple[float, float]:
    """Punto medio (lon, lat) del dominio de los NetCDF ya procesados,
    en convencion -180/180 (la que espera cartopy en central_longitude)."""
    ersstv5 = masked_dir / "ersstv5_region.nc"
    if not ersstv5.exists():
        sys.exit(f"FALTA {ersstv5} -- corre antes el pipeline (pasos 03-05).")

    with nc.Dataset(ersstv5) as ds:
        lat = ds.variables["lat"][:]
        lon = ds.variables["lon"][:]

    lon_center_0_360 = float(lon.min() + lon.max()) / 2.0
    lat_center = float(lat.min() + lat.max()) / 2.0
    # 0-360 -> -180/180
    lon_center = ((lon_center_0_360 + 180.0) % 360.0) - 180.0
    return lon_center, lat_center


def draw_box(ax, box: dict, label: str, color: str, *, emphasize: bool) -> None:
    lon1, lon2 = box["lon_min"], box["lon_max"]
    lat1, lat2 = box["lat_min"], box["lat_max"]
    lons = [lon1, lon2, lon2, lon1, lon1]
    lats = [lat1, lat1, lat2, lat2, lat1]
    ax.plot(
        lons, lats,
        transform=ccrs.PlateCarree(),
        color=color,
        linewidth=2.2 if emphasize else 1.3,
        linestyle="-" if emphasize else "--",
        zorder=5,
    )
    lon_mid = (lon1 + lon2) / 2.0
    lat_mid = (lat1 + lat2) / 2.0
    ax.text(
        lon_mid, lat_mid, label,
        transform=ccrs.PlateCarree(),
        ha="center", va="center", fontsize=9,
        fontweight="bold" if emphasize else "normal",
        color=color, zorder=6,
        bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.75, edgecolor="none"),
    )


def main(out_path: Path) -> None:
    domains = load_domains(DOMAINS_YAML)
    central_lon, central_lat = netcdf_domain_center(MASKED_DIR)
    print(f"Centro de proyeccion (desde el dominio de los NetCDF): "
          f"lon={central_lon:.1f}, lat={central_lat:.1f}", file=sys.stderr)

    proj = ccrs.Orthographic(central_longitude=central_lon, central_latitude=central_lat)
    fig, ax = plt.subplots(figsize=(8, 8), subplot_kw={"projection": proj})
    ax.set_global()
    ax.add_feature(cfeature.LAND, facecolor="0.85", zorder=1)
    ax.add_feature(cfeature.OCEAN, facecolor="#eaf3fb", zorder=0)
    ax.add_feature(cfeature.COASTLINE, linewidth=0.6, zorder=2)
    gl = ax.gridlines(draw_labels=False, linewidth=0.4, color="gray", alpha=0.5, zorder=3)

    draw_box(ax, NINO4, "Niño 4", "tab:blue", emphasize=False)
    draw_box(ax, NINO3, "Niño 3", "tab:orange", emphasize=False)
    draw_box(ax, domains["nino34"], "Niño 3.4", "tab:red", emphasize=True)
    draw_box(ax, domains["nino12"], "Niño 1+2", "tab:purple", emphasize=True)

    ax.set_title(
        "Regiones Niño -- proyección Ortográfica\n"
        "(centrada en el dominio de los NetCDF de data/processed/masked)",
        fontsize=11,
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=100, bbox_inches="tight")
    plt.close(fig)
    print(f"Figura guardada en {out_path}", file=sys.stderr)


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    main(out)
