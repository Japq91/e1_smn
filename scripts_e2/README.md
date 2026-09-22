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

Ningún script de esta carpeta debe escribir dentro de `data/` fuera de
un subdirectorio propio (p.ej. `data/processed/e2/`), ni modificar
nada bajo `scripts/` o `data/processed/masked/` -- eso es responsabilidad
exclusiva del pipeline de E1 (`run.sh`).
