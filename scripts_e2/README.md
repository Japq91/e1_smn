# scripts_e2/

Código del Entregable 2 (climatología, sesgos, diagrama de Taylor,
Índices C/E -- ver `informe/informe_e1_smnv3.tex`, sección "Entregable
2: próximos pasos").

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
