#!/usr/bin/env python3
"""
Noticia Diaria de El País
-------------------------
Obtiene la noticia más destacada de elpais.com y la envía por email.
Configura tus datos en la sección CONFIGURACIÓN antes de ejecutar.

Requisitos:
    pip install requests beautifulsoup4

Automatización:
    Linux/Mac (cron): crontab -e  →  45 19 * * * /usr/bin/python3 /ruta/elpaisnoticiadeldia.py
    Windows: Programador de tareas → ejecutar cada día a las 8:00
"""

import smtplib
import requests
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from bs4 import BeautifulSoup

# ─────────────────────────────────────────────
# CONFIGURACIÓN — edita estos valores
# ─────────────────────────────────────────────

EMAIL_ORIGEN  = "laminarrieta@gmail.com"       # Correo desde el que envías
EMAIL_DESTINO = "laminarrieta@gmail.com"    # Correo donde recibirás la noticia
CONTRASENA    = "fnuf eewy zzkd nnfv"       # Contraseña de aplicación de Gmail*
                                            # * Ve a: myaccount.google.com/apppasswords

# ─────────────────────────────────────────────


def obtener_noticia():
    """Scrape la noticia principal de El País."""
    url = "https://elpais.com/"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    response = requests.get(url, headers=headers, timeout=15)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    # Buscar el artículo principal (cabecera)
    noticia = None
    candidatos = soup.select("article h2 a, article h3 a, .c_t a, .headline a")

    for tag in candidatos:
        titulo = tag.get_text(strip=True)
        enlace = tag.get("href", "")
        if titulo and len(titulo) > 20:
            if enlace.startswith("/"):
                enlace = "https://elpais.com" + enlace
            noticia = {"titulo": titulo, "enlace": enlace}
            break

    # Intentar obtener entradilla / descripción
    descripcion = ""
    if noticia:
        try:
            art = requests.get(noticia["enlace"], headers=headers, timeout=15)
            art_soup = BeautifulSoup(art.text, "html.parser")
            desc_tag = art_soup.select_one(
                "h2.a_st, .a_st, .article-summary, .article__summary, p.article-body__paragraph"
            )
            if desc_tag:
                descripcion = desc_tag.get_text(strip=True)
        except Exception:
            pass

    return noticia, descripcion


def construir_email(noticia, descripcion):
    """Construye el cuerpo del email en HTML."""
    hoy = date.today().strftime("%d de %B de %Y").capitalize()
    titulo  = noticia["titulo"]
    enlace  = noticia["enlace"]

    html = f"""
    <html>
    <body style="font-family: Georgia, serif; max-width: 600px; margin: auto; color: #222;">
        <div style="border-top: 4px solid #004f9f; padding-top: 16px; margin-bottom: 24px;">
            <img src="https://ep00.epimg.net/iconos/v1.x/v1.0/logos/elpais.png"
                 alt="El País" height="32" style="margin-bottom: 8px;"><br>
            <span style="color: #666; font-size: 13px;">Noticia del día · {hoy}</span>
        </div>

        <h1 style="font-size: 22px; line-height: 1.3; margin-bottom: 12px;">
            <a href="{enlace}" style="color: #004f9f; text-decoration: none;">{titulo}</a>
        </h1>

        {"<p style='font-size: 16px; color: #444; line-height: 1.6;'>" + descripcion + "</p>" if descripcion else ""}

        <p style="margin-top: 24px;">
            <a href="{enlace}"
               style="background:#004f9f; color:#fff; padding:10px 20px;
                      border-radius:4px; text-decoration:none; font-size:14px;">
                Leer noticia completa →
            </a>
        </p>

        <hr style="border:none; border-top:1px solid #ddd; margin-top:40px;">
        <p style="font-size:12px; color:#999;">
            Enviado automáticamente desde tu script de Python ·
            <a href="https://elpais.com" style="color:#999;">elpais.com</a>
        </p>
    </body>
    </html>
    """
    return html


def enviar_email(asunto, cuerpo_html):
    """Envía el email usando Gmail SMTP."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = asunto
    msg["From"]    = EMAIL_ORIGEN
    msg["To"]      = EMAIL_DESTINO
    msg.attach(MIMEText(cuerpo_html, "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as servidor:
        servidor.login(EMAIL_ORIGEN, CONTRASENA)
        servidor.sendmail(EMAIL_ORIGEN, EMAIL_DESTINO, msg.as_string())


def main():
    print("📰 Obteniendo noticia de El País...")
    noticia, descripcion = obtener_noticia()

    if not noticia:
        print("❌ No se pudo obtener ninguna noticia.")
        return

    print(f"✅ Noticia encontrada: {noticia['titulo']}")

    hoy   = date.today().strftime("%d/%m/%Y")
    asunto = f"📰 El País · Noticia del día {hoy}"
    cuerpo = construir_email(noticia, descripcion)

    print("📧 Enviando email...")
    enviar_email(asunto, cuerpo)
    print("✅ Email enviado correctamente.")


if __name__ == "__main__":
    main()
