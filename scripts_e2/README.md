# scripts_e2/

Código del Entregable 2: climatología, sesgo, ONI/RONI (Niño 3.4) e
ICEN (Niño 1+2), diagrama de Taylor -- ver
`informe/borradores/marco_teorico_e2.txt` para las ecuaciones/citas y
`informe/informe_e1_smnv3.tex`, sección "Próximos pasos", `tab:roadmap`,
para lo que exige el TdR. No se usan Índices C/E (Takahashi et al.,
2011): decisión del usuario, reemplazados por ONI/RONI/ICEN.

**Sin corrección Linear Scaling (LS)**: se probó y se descartó -- LS es
una resta constante por mes calendario, y cualquier anomalía (que es
todo lo que se calcula acá: ONI, RONI, ICEN, variabilidad, correlación,
Taylor) la cancela algebraicamente sola. Los índices se calculan
directamente como anomalía respecto a la climatología **propia** de
cada dataset (ERSSTv5 con la suya, cada modelo con la suya) -- mismo
criterio con el que se calcula ONI en la práctica real, sin mezclar
climatologías entre fuentes. El sesgo (`C_m^modelo - C_m^obs`) se sigue
reportando como diagnóstico independiente (lo pide el TdR), pero ya no
alimenta ningún cálculo posterior.

Contrato de entrada, fijo y de solo lectura, producido por el
Entregable 1 (`scripts/`, `run.sh`):

- `data/processed/models_inventory_final.csv` -- filtrar por
  `selected == "True"` para saber qué modelos usar (los mismos 40 que
  documenta el informe de E1).
- `data/processed/masked/tos_<modelo>_<experimento>.nc` -- SST ya
  homogeneizada (grilla, calendario, unidades, máscara océano-tierra
  compartidas con ERSSTv5).
- `data/processed/masked/ersstv5_region.nc` -- referencia
  observacional.

Salidas propias del Entregable 2, todas anidadas bajo el mismo
directorio raíz por tipo de contenido que usa E1 (en vez de carpetas
sueltas `data_e2/`/`figuras_e2/` en la raíz del repo -- E3 y E4 del
mismo TdR van a necesitar el mismo patrón):

- `data/processed/e2/` -- datos procesados propios de E2.
- `figures/e2/` -- figuras generadas por estos scripts.
- `informe/figuras/e2/` -- symlinks curados hacia `figures/e2/` para
  el futuro `informe/informe_e2.tex` (mismo criterio que
  `informe/figuras/` para E1, ver su README).

Ningún script de esta carpeta debe escribir fuera de esos tres
subdirectorios, ni modificar nada bajo `scripts/`, `run.sh` o
`data/processed/masked/` -- eso es responsabilidad exclusiva del
pipeline de E1.

## Convenciones de datos de E2

Documentadas en `data/processed/e2/README.md` (numeración de modelos
`M01..M40`, formato del CSV de índices, y el recorte a la ventana
temporal común a los 40 modelos por la disponibilidad de IITM-ESM) --
no se duplican acá.
