#!/usr/bin/env python3
"""Mapa de contexto: cajas Nino + area de datos procesados (ventana
real de descarga), en proyeccion Robinson centrada en el punto medio
de la caja Niño 3.4 (config/domains.yaml) -- no en un valor fijo, para
que la region de interes del proyecto quede siempre al medio del mapa.

Reescrito para que coincida con graficos_exploratorios.ipynb (GRAFICO
5) -- la version anterior de este script usaba una proyeccion
Ortografica con centro calculado a partir del dominio de los NetCDF, no
dibujaba la ventana de descarga, y guardaba en
figures/region_nino_orthographic.png, un nombre que ningun informe
referencia. informe/informe_e1_smn(v2).tex esperan
figuras/region_nino_proj.png -- este script ahora escribe
figures/region_nino_proj.png (misma convencion de carpeta que el resto
de scripts/plot_*.py; la carpeta "figuras/" del .tex es responsabilidad
de quien arma el PDF, no de este pipeline).

Dibuja las cuatro cajas clasicas del ENOS (Nino 4, Nino 3, Nino 3.4,
Nino 1+2) mas la ventana de descarga real (config/domains.yaml,
'download_window') como rectangulo relleno -- Nino 3.4 y Nino 1+2 (las
que efectivamente usa este proyecto) se resaltan con doble borde.

Igual que el resto de scripts/plot_*.py: si la figura no existe
todavia, se genera sin preguntar; si ya existe, pregunta (15s, por
defecto NO) si se quiere regenerar -- ver should_regenerate() mas
abajo (duplicada de plot_common.should_regenerate en vez de importar
ese modulo, a proposito: este script se mantiene independiente del
resto, no depende de datos descargados ni del resto del pipeline).

Requiere cartopy -- SI forma parte de environment.yml (agregado ahi,
ver ese archivo).

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
import yaml  # noqa: E402
from cartopy.mpl.gridliner import LATITUDE_FORMATTER, LONGITUDE_FORMATTER  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402
from matplotlib.ticker import MultipleLocator  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent.parent
DOMAINS_YAML = BASE_DIR / "config/domains.yaml"
DEFAULT_OUT = BASE_DIR / "figures/region_nino_proj.png"

# Cajas de referencia geografica (no usadas por el proyecto, solo dan
# contexto): no estan en config/domains.yaml a proposito.
NINO4 = dict(lon_min=160.0, lon_max=210.0, lat_min=-5.0, lat_max=5.0)
NINO3 = dict(lon_min=210.0, lon_max=270.0, lat_min=-5.0, lat_max=5.0)


def should_regenerate(out_path: Path) -> bool:
    """Ver plot_common.should_regenerate -- misma logica, duplicada aca
    para no acoplar este script (deliberadamente independiente) al
    resto del pipeline."""
    if not out_path.exists():
        return True
    if not sys.stdin.isatty():
        print(f"{out_path.name} ya existe, se omite (sin terminal interactiva para preguntar).", file=sys.stderr)
        return False
    import select
    print(f"{out_path.name} ya existe. Regenerar? [s/N, 15s, por defecto N] ", end="", file=sys.stderr, flush=True)
    rlist, _, _ = select.select([sys.stdin], [], [], 15)
    if not rlist:
        print("", file=sys.stderr)
        print("(sin respuesta en 15s, se mantiene la figura existente)", file=sys.stderr)
        return False
    return sys.stdin.readline().strip().lower().startswith("s")


def load_domains(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def nino34_center(domains: dict) -> tuple[float, float]:
    """Centro (lon, lat) de la caja Niño 3.4 (config/domains.yaml), en
    convencion -180/180 -- el mapa se centra ahi en vez de un valor
    fijo, para que la region de interes del proyecto quede al medio."""
    box = domains["nino34"]
    lon_center_0_360 = (box["lon_min"] + box["lon_max"]) / 2.0
    lat_center = (box["lat_min"] + box["lat_max"]) / 2.0
    lon_center = ((lon_center_0_360 + 180.0) % 360.0) - 180.0
    return lon_center, lat_center


def draw_box(ax, box: dict, color: str, *, double_border: bool = False) -> None:
    lon1, lon2 = box["lon_min"], box["lon_max"]
    lat1, lat2 = box["lat_min"], box["lat_max"]
    lons = [lon1, lon2, lon2, lon1, lon1]
    lats = [lat1, lat1, lat2, lat2, lat1]
    ax.plot(lons, lats, transform=ccrs.PlateCarree(), color=color,
             linewidth=1.4 if double_border else 1.0, zorder=5)
    if double_border:
        ax.plot(lons, lats, transform=ccrs.PlateCarree(), color="k",
                 linewidth=0.5, alpha=0.6, zorder=6)


def draw_rect(ax, lon_a: float, lon_b: float, lat_a: float, lat_b: float,
              alpha: float = 0.4, color: str = "green") -> None:
    lons = [lon_a, lon_b, lon_b, lon_a, lon_a]
    lats = [lat_a, lat_a, lat_b, lat_b, lat_a]
    ax.fill(lons, lats, transform=ccrs.PlateCarree(), color=color, alpha=alpha,
             zorder=4, edgecolor="none")


def draw_download_window(ax, domains: dict, color: str) -> None:
    """Ventana real de descarga (config/domains.yaml, download_window),
    en convencion -180/180. Maneja el cruce del antimeridiano
    partiendo el rectangulo en dos si hace falta."""
    dw = domains["download_window"]
    lat1, lat2 = dw["lat_min"], dw["lat_max"]
    if dw["lon_max"] - dw["lon_min"] >= 360.0:
        # Ventana global en longitud (lon_min=0, lon_max=360, Entregable 2):
        # no hay antimeridiano que cruzar -- lon2 = lon_max - 360.0 daria
        # 0.0, igual a lon1, y el rectangulo quedaria con ancho cero.
        draw_rect(ax, -180.0, 180.0, lat1, lat2, alpha=0.35, color=color)
        return
    lon1 = dw["lon_min"]
    lon2 = dw["lon_max"] - 360.0
    if lon1 > lon2:
        draw_rect(ax, lon1, 180.0, lat1, lat2, alpha=0.35, color=color)
        draw_rect(ax, -180.0, lon2, lat1, lat2, alpha=0.35, color=color)
    else:
        draw_rect(ax, lon1, lon2, lat1, lat2, alpha=0.35, color=color)


def main(out_path: Path) -> None:
    if not should_regenerate(out_path):
        return
    domains = load_domains(DOMAINS_YAML)
    central_lon, central_lat = nino34_center(domains)
    print(f"Centro de proyeccion (Niño 3.4): lon={central_lon:.1f}, lat={central_lat:.1f}", file=sys.stderr)

    proj = ccrs.Robinson(central_longitude=central_lon)
    fig, ax = plt.subplots(figsize=(10, 6), subplot_kw={"projection": proj})
    ax.add_feature(cfeature.LAND, facecolor="0.1", alpha=0.8, zorder=1)
    ax.add_feature(cfeature.OCEAN, alpha=0.5, zorder=0)
    ax.add_feature(cfeature.COASTLINE, linewidth=0.9, edgecolor="0.95", zorder=2)

    gl = ax.gridlines(draw_labels=True, linewidth=0.4, color="0.5", alpha=0.5, zorder=3,
                       xlocs=MultipleLocator(20), ylocs=MultipleLocator(10))
    gl.top_labels = False
    gl.right_labels = False
    gl.xformatter = LONGITUDE_FORMATTER
    gl.yformatter = LATITUDE_FORMATTER

    download_color = "tab:green"
    draw_download_window(ax, domains, download_color)
    draw_box(ax, NINO4, "tab:blue")
    draw_box(ax, NINO3, "tab:purple")
    draw_box(ax, domains["nino34"], "tab:red", double_border=True)
    draw_box(ax, domains["nino12"], "tab:red", double_border=True)

    # Leyenda consolidada en un solo bloque, en vez de un texto flotante
    # por caja sobre el mapa (asi era antes: 5 etiquetas sueltas
    # compitiendo con la costa/grilla por espacio).
    legend_elements = [
        Line2D([0], [0], color="tab:blue", lw=1.4, label="Niño 4"),
        Line2D([0], [0], color="tab:purple", lw=1.4, label="Niño 3"),
        Line2D([0], [0], color="tab:red", lw=1.4, label="Niño 3.4 y Niño 1+2"),
        Patch(facecolor=download_color, alpha=0.3, edgecolor="none",
              label="Área de datos procesados"),
    ]
    ax.legend(handles=legend_elements, loc="lower center", bbox_to_anchor=(0.5, -0.32),
               ncol=2, frameon=False, fontsize=8)

    ax.set_title("Regiones Niño y área de datos procesados", fontsize=11)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=100, bbox_inches="tight")
    plt.close(fig)
    print(f"Figura guardada en {out_path}", file=sys.stderr)


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    main(out)
