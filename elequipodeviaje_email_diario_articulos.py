#!/usr/bin/env python3
"""
Envía por email una tabla HTML con 10 productos de https://elequipodeviaje.com/
cuyo precio sea superior a 100 €.

Dependencias mínimas:
    pip install requests beautifulsoup4

Opcional para modo residente diario:
    pip install schedule

Variables de entorno recomendadas:
    export GMAIL_APP_PASSWORD="TU_APP_PASSWORD"
    export EMAIL_FROM="laminarrieta@gmail.com"
    export EMAIL_TO="laminarrieta@gmail.com"
    export DAILY_TIME="09:00"

Uso recomendado en GitHub Actions:
    python elequipodeviaje_email_diario_articulos_fix.py --once

Uso en local en modo diario:
    python elequipodeviaje_email_diario_articulos_fix.py
"""

from __future__ import annotations

import os
import re
import sys
import time
import ssl
import smtplib
from dataclasses import dataclass
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Iterable, List, Optional, Set
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://elequipodeviaje.com/"
DOMAIN = "elequipodeviaje.com"
EMAIL_FROM = os.getenv("EMAIL_FROM", "laminarrieta@gmail.com")
EMAIL_TO = os.getenv("EMAIL_TO", "laminarrieta@gmail.com")
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")
DAILY_TIME = os.getenv("DAILY_TIME", "09:00")  # formato HH:MM
REQUEST_TIMEOUT = 25
MIN_PRICE = 100.0
MAX_PRODUCTS = 10
MAX_PRODUCT_PAGES_TO_SCAN = 250
MAX_CATEGORY_PAGES_TO_SCAN = 80
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

SEED_URLS = [
    BASE_URL,
    urljoin(BASE_URL, "101-maletas"),
    urljoin(BASE_URL, "102-maletas-maletas-y-trolleys-de-cabina"),
    urljoin(BASE_URL, "107-mochilas"),
]

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
}


@dataclass
class Product:
    name: str
    price: float
    brand: str
    ean: str
    url: str


def get_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    return session


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def is_same_domain(url: str) -> bool:
    return DOMAIN in urlparse(url).netloc


def looks_like_product_url(url: str) -> bool:
    path = urlparse(url).path
    return bool(re.search(r"/\d+-.+\.html$", path))


def looks_like_category_url(url: str) -> bool:
    path = urlparse(url).path
    if not path or path == "/":
        return True
    if path.endswith(".html"):
        return False
    return bool(re.search(r"/(\d+[-\w]+)$", path)) or "page=" in url


def absolute_links(base_url: str, soup: BeautifulSoup) -> Iterable[str]:
    for a in soup.select("a[href]"):
        href = a.get("href", "").strip()
        if not href:
            continue
        url = urljoin(base_url, href)
        if is_same_domain(url):
            yield url.split("#", 1)[0]


def fetch_html(session: requests.Session, url: str) -> Optional[str]:
    try:
        response = session.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.text
    except requests.RequestException as exc:
        print(f"[WARN] No se pudo descargar {url}: {exc}", file=sys.stderr)
        return None


_PRICE_RE = re.compile(r"(\d{1,3}(?:[\.\s]\d{3})*(?:,\d{2})?)\s*€")
_EAN_RE = re.compile(r"\bEAN\s*[:#-]?\s*(\d{8,14})\b", re.IGNORECASE)
_BRAND_RE = re.compile(r"\bMarca\s*[:#-]?\s*([^\n\r]+)", re.IGNORECASE)
_NAME_FROM_TITLE_RE = re.compile(r"^\s*(.*?)\s*(?:\||-\s*El Equipo de Viaje)?\s*$")


def parse_price(text: str) -> Optional[float]:
    match = _PRICE_RE.search(text)
    if not match:
        return None
    raw = match.group(1).replace(".", "").replace(" ", "").replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def parse_product(session: requests.Session, url: str) -> Optional[Product]:
    html = fetch_html(session, url)
    if not html:
        return None

    soup = BeautifulSoup(html, "html.parser")
    page_text = soup.get_text("\n", strip=True)

    name = ""
    h1 = soup.find("h1")
    if h1:
        name = clean_text(h1.get_text(" ", strip=True))
    if not name and soup.title and soup.title.string:
        title_match = _NAME_FROM_TITLE_RE.search(soup.title.string)
        if title_match:
            name = clean_text(title_match.group(1))

    price = None
    meta_price = soup.find("meta", attrs={"property": "product:price:amount"})
    if meta_price and meta_price.get("content"):
        try:
            price = float(meta_price["content"].replace(",", "."))
        except ValueError:
            price = None
    if price is None:
        price = parse_price(page_text)

    brand = ""
    brand_meta = soup.find("meta", attrs={"property": "product:brand"})
    if brand_meta and brand_meta.get("content"):
        brand = clean_text(brand_meta["content"])
    if not brand:
        m = _BRAND_RE.search(page_text)
        if m:
            brand = clean_text(m.group(1).split("EAN")[0])
    if not brand and name:
        brand_candidates = [
            "SAMSONITE", "TRAVELITE", "CABIN ZERO", "ROKA", "KCB", "GORJUSS",
            "BIENOTI-EV", "VERAGE", "STIVIBAGS", "AMERICAN TOURISTER"
        ]
        upper_name = name.upper()
        for candidate in brand_candidates:
            if candidate in upper_name:
                brand = candidate
                break

    ean = ""
    meta_ean = soup.find("meta", attrs={"property": "product:gtin13"})
    if meta_ean and meta_ean.get("content"):
        ean = clean_text(meta_ean["content"])
    if not ean:
        m = _EAN_RE.search(page_text)
        if m:
            ean = m.group(1)

    if not name or price is None or not ean:
        return None

    return Product(
        name=name,
        price=price,
        brand=brand or "No encontrado",
        ean=ean,
        url=url,
    )


def collect_product_urls(session: requests.Session) -> List[str]:
    to_visit = list(SEED_URLS)
    seen_pages: Set[str] = set()
    seen_product_urls: Set[str] = set()
    product_urls: List[str] = []
    scanned_category_pages = 0

    while to_visit and scanned_category_pages < MAX_CATEGORY_PAGES_TO_SCAN:
        url = to_visit.pop(0)
        if url in seen_pages:
            continue
        seen_pages.add(url)

        html = fetch_html(session, url)
        if not html:
            continue

        scanned_category_pages += 1
        soup = BeautifulSoup(html, "html.parser")

        for link in absolute_links(url, soup):
            if looks_like_product_url(link):
                if link not in seen_product_urls:
                    seen_product_urls.add(link)
                    product_urls.append(link)
            elif looks_like_category_url(link) and link not in seen_pages:
                if any(skip in link for skip in ("contact", "blog", "faq", "login", "carrito")):
                    continue
                to_visit.append(link)

        if len(product_urls) >= MAX_PRODUCT_PAGES_TO_SCAN:
            break

    return product_urls[:MAX_PRODUCT_PAGES_TO_SCAN]


def get_products() -> List[Product]:
    session = get_session()
    product_urls = collect_product_urls(session)
    products: List[Product] = []
    seen_eans: Set[str] = set()

    for url in product_urls:
        product = parse_product(session, url)
        if not product:
            continue
        if product.price <= MIN_PRICE:
            continue
        if product.ean in seen_eans:
            continue

        seen_eans.add(product.ean)
        products.append(product)

        if len(products) >= MAX_PRODUCTS:
            break

    products.sort(key=lambda p: p.price, reverse=True)
    return products[:MAX_PRODUCTS]


def build_html_table(products: List[Product]) -> str:
    today = datetime.now().strftime("%d/%m/%Y %H:%M")

    if not products:
        return f"""
        <html>
          <body style="font-family:Arial,Helvetica,sans-serif;">
            <h2>Productos de El Equipo de Viaje &gt; 100 €</h2>
            <p>Fecha de generación: {today}</p>
            <p>No se encontraron productos suficientes que cumplan el criterio.</p>
          </body>
        </html>
        """

    rows = []
    for p in products:
        rows.append(
            "<tr>"
            f"<td style='padding:8px;border:1px solid #ddd;'><a href='{p.url}'>{p.name}</a></td>"
            f"<td style='padding:8px;border:1px solid #ddd;text-align:right;'>{p.price:.2f} €</td>"
            f"<td style='padding:8px;border:1px solid #ddd;'>{p.brand}</td>"
            f"<td style='padding:8px;border:1px solid #ddd;'>{p.ean}</td>"
            "</tr>"
        )

    return f"""
    <html>
      <body style="font-family:Arial,Helvetica,sans-serif;color:#222;">
        <h2>10 productos de El Equipo de Viaje con precio superior a 100 €</h2>
        <p>Fecha de generación: {today}</p>
        <table style="border-collapse:collapse;width:100%;max-width:1100px;">
          <thead>
            <tr>
              <th style="padding:8px;border:1px solid #ddd;background:#f5f5f5;text-align:left;">Nombre del producto</th>
              <th style="padding:8px;border:1px solid #ddd;background:#f5f5f5;text-align:right;">Precio del producto</th>
              <th style="padding:8px;border:1px solid #ddd;background:#f5f5f5;text-align:left;">Marca del producto</th>
              <th style="padding:8px;border:1px solid #ddd;background:#f5f5f5;text-align:left;">EAN del producto</th>
            </tr>
          </thead>
          <tbody>
            {''.join(rows)}
          </tbody>
        </table>
      </body>
    </html>
    """


def send_email(html_body: str, count: int) -> None:
    if not GMAIL_APP_PASSWORD:
        raise RuntimeError(
            "No se ha definido GMAIL_APP_PASSWORD. "
            "Debes guardarla como secret o variable de entorno."
        )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Productos > 100 € - El Equipo de Viaje ({count})"
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context) as server:
        server.login(EMAIL_FROM, GMAIL_APP_PASSWORD)
        server.sendmail(EMAIL_FROM, [EMAIL_TO], msg.as_string())


def job() -> None:
    print(f"[{datetime.now().isoformat(timespec='seconds')}] Ejecutando tarea...")
    products = get_products()
    html = build_html_table(products)
    send_email(html, len(products))
    print(f"[{datetime.now().isoformat(timespec='seconds')}] Email enviado con {len(products)} producto(s).")


def run_daily_loop() -> None:
    try:
        import schedule  # opcional
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Falta el módulo 'schedule'. "
            "Soluciones: 1) ejecuta con --once en GitHub Actions, o 2) instala 'schedule' "
            "si quieres dejar el script residente en ejecución."
        ) from exc

    schedule.every().day.at(DAILY_TIME).do(job)
    print(f"Programado para ejecutarse cada día a las {DAILY_TIME}. Proceso en espera...")

    while True:
        schedule.run_pending()
        time.sleep(30)


def main() -> None:
    run_once = "--once" in sys.argv

    if run_once:
        job()
        return

    run_daily_loop()


if __name__ == "__main__":
    main()
