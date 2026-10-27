"""
Descarga los precios de "Papa Súper Chola" del SIPA / MAG (Ecuador).

Fuente: http://sinagap.mag.gob.ec/sina/paginasCGSIN/Rep_Pre_Prod_X_MercCGSIN.aspx
(pestaña "Consulta por Producto", la misma información de precios que
InfoProductor, pero de acceso público sin cédula).

Salidas (carpeta ./datos):
  - papa_super_chola_historico.csv : un registro por mercado y fecha de toma,
    se va acumulando día a día sin duplicados.
  - papa_super_chola_ultimo.csv    : foto completa de la última consulta.
  - descarga.log                   : bitácora de ejecuciones.

Uso:  python descargar_papa.py [--dias 15]
"""
import argparse
import csv
import html
import logging
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

URL = "http://sinagap.mag.gob.ec/sina/paginasCGSIN/Rep_Pre_Prod_X_MercCGSIN.aspx"
PRODUCTO_ID = "176"  # Papa Súper Chola
PRODUCTO = "Papa Súper Chola"
P = "ctl00$ContentPlaceHolder1$TabContainer1$TabPanel1$"
TABLA_ID = "ctl00_ContentPlaceHolder1_TabContainer1_TabPanel1_gvi_R"

BASE = Path(__file__).resolve().parent
DATOS = BASE / "datos"
HISTORICO = DATOS / "papa_super_chola_historico.csv"
ULTIMO = DATOS / "papa_super_chola_ultimo.csv"

COLUMNAS = [
    "fecha_descarga", "producto", "mercado",
    "fecha_ultimo_precio", "ultimo_precio_usd_kg",
    "fecha_penultimo_precio", "penultimo_precio_usd_kg",
    "precio_minimo", "precio_promedio", "precio_maximo",
    "tendencia", "variacion_pct",
]


def campos_ocultos(pagina):
    datos = {}
    for tag in re.findall(r"<input[^>]*type=\"hidden\"[^>]*>", pagina):
        nombre = re.search(r'name="([^"]+)"', tag)
        valor = re.search(r'value="([^"]*)"', tag)
        if nombre:
            datos[nombre.group(1)] = html.unescape(valor.group(1)) if valor else ""
    return datos


def texto(celda):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", celda))).strip()


def precio_y_fecha(celda):
    """Las celdas de último/penúltimo precio traen 'precio fecha'."""
    partes = texto(celda).split()
    precio = partes[0] if partes else ""
    fecha = partes[1] if len(partes) > 1 else ""
    return precio, fecha


def a_iso(fecha_ddmmyyyy):
    try:
        return datetime.strptime(fecha_ddmmyyyy, "%d/%m/%Y").date().isoformat()
    except ValueError:
        return ""


def descargar(dias):
    hoy = date.today()
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (descarga precios MAG)"

    r = s.get(URL, timeout=90)
    r.raise_for_status()
    form = campos_ocultos(r.content.decode("utf-8", errors="replace"))
    form.update({
        "__EVENTTARGET": P + "DropDownList1",
        "__EVENTARGUMENT": "",
        P + "DropDownList1": PRODUCTO_ID,
        P + "ddl_F": "1",
        P + "Fec_I$txtFecha": (hoy - timedelta(days=dias)).strftime("%d/%m/%Y"),
        P + "Fec_F$txtFecha": hoy.strftime("%d/%m/%Y"),
    })
    r = s.post(URL, data=form, timeout=120)
    r.raise_for_status()
    pagina = r.content.decode("utf-8", errors="replace")

    i = pagina.find(f'id="{TABLA_ID}"')
    if i < 0:
        raise RuntimeError("No se encontró la tabla de precios en la respuesta")
    tabla = pagina[i:pagina.find("</table>", i)]

    filas = []
    for fila in re.findall(r"<tr[^>]*>(.*?)</tr>", tabla, re.S)[1:]:
        celdas = re.findall(r"<td[^>]*>(.*?)</td>", fila, re.S)
        if len(celdas) < 8:
            continue
        ult_p, ult_f = precio_y_fecha(celdas[5])
        pen_p, pen_f = precio_y_fecha(celdas[4])
        filas.append({
            "fecha_descarga": hoy.isoformat(),
            "producto": PRODUCTO,
            "mercado": texto(celdas[0]),
            "fecha_ultimo_precio": a_iso(ult_f),
            "ultimo_precio_usd_kg": ult_p,
            "fecha_penultimo_precio": a_iso(pen_f),
            "penultimo_precio_usd_kg": pen_p,
            "precio_minimo": texto(celdas[1]),
            "precio_promedio": texto(celdas[2]),
            "precio_maximo": texto(celdas[3]),
            "tendencia": texto(celdas[6]),
            "variacion_pct": texto(celdas[7]),
        })
    return filas


def guardar(filas):
    DATOS.mkdir(exist_ok=True)

    with ULTIMO.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNAS)
        w.writeheader()
        w.writerows(filas)

    existentes = set()
    if HISTORICO.exists():
        with HISTORICO.open(newline="", encoding="utf-8-sig") as f:
            existentes = {(r["mercado"], r["fecha_ultimo_precio"]) for r in csv.DictReader(f)}

    nuevas = [r for r in filas if (r["mercado"], r["fecha_ultimo_precio"]) not in existentes]
    escribir_encabezado = not HISTORICO.exists()
    with HISTORICO.open("a", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNAS)
        if escribir_encabezado:
            w.writeheader()
        w.writerows(nuevas)
    return len(nuevas)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dias", type=int, default=15,
                    help="días hacia atrás que abarca la consulta (por defecto 15)")
    args = ap.parse_args()

    DATOS.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(DATOS / "descarga.log", encoding="utf-8"),
                  logging.StreamHandler(sys.stdout)],
    )
    try:
        filas = descargar(args.dias)
        if not filas:
            logging.warning("La consulta no devolvió precios para %s", PRODUCTO)
            return 1
        nuevas = guardar(filas)
        logging.info("%d mercados descargados, %d registros nuevos en el histórico",
                     len(filas), nuevas)
        for r in filas:
            logging.info("  %-40s %s  $%s/kg", r["mercado"],
                         r["fecha_ultimo_precio"], r["ultimo_precio_usd_kg"])
        return 0
    except PermissionError as e:
        logging.error("No se pudo escribir %s: el archivo está abierto (¿en Excel?). "
                      "Ciérrelo; la próxima ejecución completará los datos faltantes.",
                      e.filename)
        return 1
    except Exception:
        logging.exception("Fallo la descarga")
        return 1


if __name__ == "__main__":
    sys.exit(main())
