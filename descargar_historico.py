"""
Descarga la serie histórica de precios de TODOS los productos y mercados del
SIPA / MAG (Ecuador), usando la pestaña "Consulta por Mercado" del reporte
público y su exportación a CSV.

Fuente: http://sinagap.mag.gob.ec/sina/paginasCGSIN/Rep_Pre_Prod_X_MercCGSIN.aspx

Salidas (carpeta ./datos/historico):
  - productos/<id>_<nombre>.csv : serie de cada producto (todos los mercados).
    Cada ejecución se fusiona con lo existente, sin duplicados, así que el
    mismo script sirve para la carga inicial y para la actualización diaria.
  - precios.csv                 : todos los productos consolidados.
  - catalogo_productos.csv      : productos y categorías disponibles.
  - historico.log               : bitácora.

Uso:
  python descargar_historico.py --desde 01/01/2021      (carga inicial)
  python descargar_historico.py --dias 30               (actualización)
  python descargar_historico.py --desde 01/01/2021 --solo 176   (un producto)
"""
import argparse
import csv
import html
import io
import logging
import re
import sys
import time
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

BASE_URL = "http://sinagap.mag.gob.ec"
URL = BASE_URL + "/sina/paginasCGSIN/Rep_Pre_Prod_X_MercCGSIN.aspx"
VISOR = BASE_URL + "/sina/paginasCGSIN/VisorReporte.aspx"
T3 = "ctl00$ContentPlaceHolder1$TabContainer1$TabPanel3$"
CLIENT_STATE = "ctl00_ContentPlaceHolder1_TabContainer1_ClientState"
PAUSA_SEG = 2  # pausa entre consultas para no saturar el servidor del MAG

CARPETA = Path(__file__).resolve().parent / "datos" / "historico"
PRODUCTOS = CARPETA / "productos"
COLUMNAS = ["fecha", "categoria", "producto_id", "producto", "mercado",
            "precio_kg", "precio_presentacion", "presentacion", "unidad"]
CLAVE = ("fecha", "mercado", "presentacion")


def campos_ocultos(pagina):
    datos = {}
    for tag in re.findall(r"<input[^>]*type=\"hidden\"[^>]*>", pagina):
        nombre = re.search(r'name="([^"]+)"', tag)
        valor = re.search(r'value="([^"]*)"', tag)
        if nombre:
            datos[nombre.group(1)] = html.unescape(valor.group(1)) if valor else ""
    return datos


def opciones(pagina, nombre):
    i = pagina.find(f'name="{nombre}"')
    j = pagina.find("</select>", i)
    return [(v, html.unescape(t).strip())
            for v, t in re.findall(r'<option[^>]*value="([^"]*)"[^>]*>([^<]*)', pagina[i:j])
            if v != "-1"]


def slug(texto):
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "_", t).strip("_").lower()


def numero(texto):
    return texto.replace(".", "").replace(",", ".") if texto else ""


class ClienteMAG:
    def __init__(self, desde, hasta):
        self.s = requests.Session()
        self.s.headers["User-Agent"] = "Mozilla/5.0 (descarga precios MAG)"
        self.fechas = {T3 + "Fec_IM$txtFecha": desde, T3 + "Fec_FM$txtFecha": hasta}
        self.pagina = self._texto(self.s.get(URL, timeout=120))
        self.mercados = opciones(self.pagina, T3 + "lib_M")

    @staticmethod
    def _texto(resp):
        resp.raise_for_status()
        if "PaginaError" in resp.url or resp.status_code == 302:
            raise RuntimeError("El servidor devolvió su página de error")
        return resp.content.decode("utf-8", errors="replace")

    def _post(self, extra, objetivo="", listas=()):
        d = campos_ocultos(self.pagina)
        d.update(self.fechas)
        d[CLIENT_STATE] = '{"ActiveTabIndex":1,"TabState":[true,true,true]}'
        d.update({"__EVENTTARGET": objetivo, "__EVENTARGUMENT": "", T3 + "ddl_TipoM": "-1"})
        d.update(extra)
        r = self.s.post(URL, data=list(d.items()) + list(listas), timeout=600,
                        allow_redirects=False)
        if r.status_code != 200:
            raise RuntimeError(f"Respuesta inesperada {r.status_code} {r.headers.get('Location')}")
        self.pagina = self._texto(r)

    def categorias(self):
        return opciones(self.pagina, T3 + "ddl_C")

    def productos_de(self, categoria):
        self._post({T3 + "ddl_C": categoria}, objetivo=T3 + "ddl_C")
        return opciones(self.pagina, T3 + "lib_P")

    def exportar_csv(self, categoria, producto_id):
        # El sitio exige marcar también "--TODOS--" (-1); sin él el reporte sale vacío.
        listas = ([(T3 + "lib_M", "-1")] + [(T3 + "lib_M", v) for v, _ in self.mercados]
                  + [(T3 + "lib_P", producto_id)])
        self._post({T3 + "ddl_C": categoria, T3 + "imb_PME1.x": "10",
                    T3 + "imb_PME1.y": "10"}, listas=listas)
        visor = self._texto(self.s.get(VISOR, timeout=600))
        m = re.search(r"(/SINA/Reserved\.ReportViewerWebControl\.axd\?ReportSession=[^\"']*?ReportStack=\d+)",
                      html.unescape(visor))
        if not m:
            raise RuntimeError("No se encontró el reporte en VisorReporte.aspx")
        url = (BASE_URL + m.group(1) + "&OpType=Export&FileName=precios"
               "&ContentDisposition=AlwaysAttachment&Format=CSV")
        r = self.s.get(url, timeout=900)
        r.raise_for_status()
        if not r.content.startswith(b"\xff\xfe"):
            raise RuntimeError("La exportación no devolvió un CSV")
        return r.content.decode("utf-16")


def parsear(texto_csv, producto_id):
    filas = []
    lector = csv.reader(io.StringIO(texto_csv))
    next(lector, None)  # encabezado del reporte
    for c in lector:
        if len(c) < 8 or not c[3]:
            continue
        try:
            fecha = datetime.strptime(c[3].split()[0], "%d/%m/%Y").date().isoformat()
        except ValueError:
            continue
        filas.append({
            "fecha": fecha,
            "categoria": re.sub(r"\s+", " ", c[1]).strip(),
            "producto_id": producto_id,
            "producto": c[2].strip(),
            "mercado": re.sub(r"\s+", " ", c[0]).strip(),
            "precio_kg": numero(c[6]),
            "precio_presentacion": numero(c[4]),
            "presentacion": re.sub(r"\s+", " ", c[5]).strip(),
            "unidad": c[7].strip(),
        })
    return filas


def leer(ruta):
    if not ruta.exists():
        return []
    with ruta.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def escribir(ruta, filas):
    tmp = ruta.with_suffix(".tmp")
    with tmp.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNAS)
        w.writeheader()
        w.writerows(filas)
    tmp.replace(ruta)


def fusionar(ruta, nuevas):
    """Une lo existente con lo nuevo; ante la misma clave gana lo nuevo."""
    todas = {tuple(r[k] for k in CLAVE): r for r in leer(ruta)}
    antes = len(todas)
    for r in nuevas:
        todas[tuple(r[k] for k in CLAVE)] = r
    filas = sorted(todas.values(), key=lambda r: (r["mercado"], r["fecha"], r["presentacion"]))
    escribir(ruta, filas)
    return len(filas) - antes


def consolidar():
    filas = []
    for ruta in sorted(PRODUCTOS.glob("*.csv")):
        filas.extend(leer(ruta))
    filas.sort(key=lambda r: (r["producto"], r["mercado"], r["fecha"]))
    escribir(CARPETA / "precios.csv", filas)
    return len(filas)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--desde", help="fecha inicial dd/mm/aaaa")
    ap.add_argument("--dias", type=int, default=30,
                    help="si no se da --desde, días hacia atrás (por defecto 30)")
    ap.add_argument("--solo", nargs="*", help="ids de producto a descargar (por defecto todos)")
    args = ap.parse_args()

    hoy = date.today()
    desde = args.desde or (hoy - timedelta(days=args.dias)).strftime("%d/%m/%Y")
    hasta = hoy.strftime("%d/%m/%Y")

    PRODUCTOS.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(CARPETA / "historico.log", encoding="utf-8"),
                  logging.StreamHandler(sys.stdout)])
    logging.info("Inicio: %s a %s", desde, hasta)

    cli = ClienteMAG(desde, hasta)
    logging.info("%d mercados disponibles", len(cli.mercados))

    catalogo = []
    for cat_id, cat in cli.categorias():
        for prod_id, prod in cli.productos_de(cat_id):
            catalogo.append((cat_id, re.sub(r"\s+", " ", cat), prod_id, prod))
        time.sleep(PAUSA_SEG)
    with (CARPETA / "catalogo_productos.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["categoria_id", "categoria", "producto_id", "producto"])
        w.writerows(catalogo)
    logging.info("%d productos en el catálogo", len(catalogo))

    if args.solo:
        catalogo = [c for c in catalogo if c[2] in args.solo]

    errores = 0
    for n, (cat_id, cat, prod_id, prod) in enumerate(catalogo, 1):
        ruta = PRODUCTOS / f"{prod_id}_{slug(prod)}.csv"
        for intento in range(1, 4):
            try:
                cli.productos_de(cat_id)  # deja el formulario en la categoría correcta
                filas = parsear(cli.exportar_csv(cat_id, prod_id), prod_id)
                nuevas = fusionar(ruta, filas) if filas else 0
                logging.info("[%d/%d] %s: %d registros descargados, %d nuevos",
                             n, len(catalogo), prod, len(filas), nuevas)
                break
            except Exception as e:
                logging.warning("[%d/%d] %s: intento %d falló (%s)", n, len(catalogo), prod, intento, e)
                time.sleep(PAUSA_SEG * 5 * intento)
                cli = ClienteMAG(desde, hasta)  # sesión nueva
        else:
            errores += 1
            logging.error("[%d/%d] %s: no se pudo descargar", n, len(catalogo), prod)
        time.sleep(PAUSA_SEG)

    total = consolidar()
    logging.info("Fin: %d registros en precios.csv, %d productos con error", total, errores)
    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main())
