# informe/figuras/e2/

Symlinks curados a `figures/e2/*.png`, mismo criterio que
`informe/figuras/` para el Entregable 1: solo los archivos que el
futuro `informe/informe_e2.tex` referencie de verdad (`figuras/e2/<archivo>.png`
en el `.tex`), no todo `figures/e2/`. Agregar un symlink nuevo con:

```
ln -sf ../../../figures/e2/<archivo>.png informe/figuras/e2/<archivo>.png
```
