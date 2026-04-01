# programaciones

Scripts de Python automatizados con cron.

## elpaisnoticiadeldia.py

Scrapa la noticia principal de [El País](https://elpais.com) y la envía por email cada hora a y 30 minutos.

### Requisitos

```bash
pip install requests beautifulsoup4
```

### Configuración

Edita las variables en la sección `CONFIGURACIÓN` del script:

- `EMAIL_ORIGEN` — tu dirección de Gmail
- `EMAIL_DESTINO` — donde quieres recibir la noticia
- `CONTRASENA` — contraseña de aplicación de Gmail ([cómo obtenerla](https://myaccount.google.com/apppasswords))

### Cron (Mac/Linux)

El script se ejecuta automáticamente cada hora a y 30 minutos (`30 * * * *`):

```
30 * * * * /usr/local/bin/python3 /Users/juanfran/Desktop/mcp/programaciones/elpaisnoticiadeldia.py >> /Users/juanfran/Desktop/mcp/programaciones/cron.log 2>&1
```

Para ver o editar el cron manualmente:
```bash
crontab -l   # ver entradas actuales
crontab -e   # editar
```
