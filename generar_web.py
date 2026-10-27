"""
Convierte el histórico descargado (datos/historico/productos/*.csv) en los
archivos JSON livianos que usa el dashboard web (docs/data).

  docs/data/catalogo.json  : productos, categorías, mercados y fecha de corte.
  docs/data/p/<id>.json    : serie de precios por mercado de cada producto.

Se descartan valores atípicos evidentes (más de 4 veces o menos de la cuarta
parte de la mediana del producto), que suelen ser errores de digitación.

Uso:  python generar_web.py
"""
import csv
import json
import statistics
from collections import defaultdict
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parent
ORIGEN = BASE / "datos" / "historico" / "productos"
DESTINO = BASE / "docs" / "data"
FACTOR_ATIPICO = 4


def main():
    (DESTINO / "p").mkdir(parents=True, exist_ok=True)
    productos, mercados, ultima_global, descartados = [], set(), "", 0

    for ruta in sorted(ORIGEN.glob("*.csv")):
        with ruta.open(newline="", encoding="utf-8-sig") as f:
            filas = list(csv.DictReader(f))
        if not filas:
            continue
        mediana = statistics.median(float(r["precio_kg"]) for r in filas)
        series = defaultdict(list)
        for r in filas:
            p = float(r["precio_kg"])
            if p > mediana * FACTOR_ATIPICO or p < mediana / FACTOR_ATIPICO:
                descartados += 1
                continue
            series[r["mercado"]].append([r["fecha"], round(p, 3)])
        for s in series.values():
            s.sort()
        pid, nombre, categoria = filas[0]["producto_id"], filas[0]["producto"], filas[0]["categoria"]
        ultima = max(s[-1][0] for s in series.values())
        ultima_global = max(ultima_global, ultima)
        mercados.update(series)
        with (DESTINO / "p" / f"{pid}.json").open("w", encoding="utf-8") as f:
            json.dump({"id": pid, "nombre": nombre, "categoria": categoria,
                       "presentacion": filas[-1]["presentacion"],
                       "mercados": series}, f, ensure_ascii=False, separators=(",", ":"))
        productos.append({"id": pid, "nombre": nombre, "categoria": categoria,
                          "registros": sum(len(s) for s in series.values()),
                          "ultima_fecha": ultima})

    productos.sort(key=lambda p: (p["categoria"], p["nombre"]))
    with (DESTINO / "catalogo.json").open("w", encoding="utf-8") as f:
        json.dump({"generado": date.today().isoformat(), "ultima_fecha": ultima_global,
                   "fuente": "SIPA - Ministerio de Agricultura y Ganadería del Ecuador",
                   "productos": productos, "mercados": sorted(mercados)},
                  f, ensure_ascii=False, indent=1)
    print(f"{len(productos)} productos, {len(mercados)} mercados, "
          f"{descartados} valores atípicos descartados, última fecha {ultima_global}")


if __name__ == "__main__":
    main()
