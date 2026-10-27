# Precios Agro Ecuador

Dashboard web (instalable en el celular) con los precios mayoristas de productos
agrícolas en los mercados del Ecuador, para que pequeños productores tengan la
información a la mano. Los datos vienen del
[SIPA – Ministerio de Agricultura y Ganadería](http://sinagap.mag.gob.ec/sina/paginasCGSIN/Rep_Pre_Prod_X_MercCGSIN.aspx)
y se actualizan todos los días.

## Cómo funciona

| Paso | Archivo |
|---|---|
| Descarga precios de todos los productos y mercados (pestaña "Consulta por Mercado", exportación CSV) y los une con el histórico sin duplicar | `descargar_historico.py` |
| Convierte el histórico en JSON livianos para la web y descarta valores atípicos evidentes | `generar_web.py` |
| Dashboard (GitHub Pages) | `docs/` |
| Actualización diaria automática a las 12:00 (hora de Ecuador) | `.github/workflows/actualizar.yml` |

Datos: `datos/historico/productos/<id>_<producto>.csv`, desde el 01/01/2021.

## Uso local

```bash
pip install requests
python descargar_historico.py --desde 01/01/2021   # carga completa
python descargar_historico.py --dias 30            # actualización
python generar_web.py
python -m http.server 8765 --directory docs        # ver en http://localhost:8765
```

`instalar_tarea.ps1` programa la actualización diaria en Windows (alternativa a GitHub Actions).
