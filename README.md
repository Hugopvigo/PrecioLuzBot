# ⚡ PrecioLuz Bot

[![Licencia: CC BY-NC-SA 4.0](https://img.shields.io/badge/Licencia-CC%20BY--NC--SA%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by-nc-sa/4.0/)

Bot de Telegram que notifica diariamente el precio de la luz en España (tarifa PVPC) a las 20:15h, con los precios del día siguiente publicados por REE.

## ¿Qué hace?

- Notifica a las 20:15h (Europe/Madrid) con los precios PVPC del día siguiente
- Consulta manual con `/precio` (hoy o mañana según la hora)
- Resumen visual: hora más barata, más cara, media y barras proporcionales por hora
- Soporte para múltiples suscriptores

## Requisitos previos

1. **Token de Telegram** — Crea un bot con [@BotFather](https://t.me/BotFather) y obtén el token
2. **Token de ESIOS** — Solicita tu token en `api_token@ree.es` (API oficial de REE)

## Instalación rápida

```bash
# 1. Clona el repo
git clone https://github.com/tu-usuario/PrecioLuz.git
cd PrecioLuz

# 2. Configura las variables
cp .env.example .env
# Edita .env con tus tokens

# 3. Arranca
docker compose up -d
```

## Variables de entorno

| Variable | Descripción | Por defecto |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Token del bot de @BotFather | *(obligatoria)* |
| `ESIOS_API_TOKEN` | Token de la API ESIOS de REE | *(obligatoria)* |
| `TZ` | Zona horaria | `Europe/Madrid` |
| `NOTIFY_HOUR` | Hora de notificación diaria | `20` |
| `NOTIFY_MINUTE` | Minuto de notificación diaria | `15` |
| `LOG_LEVEL` | Nivel de logging | `INFO` |

## Comandos del bot

| Comando | Descripción |
|---|---|
| `/start` | Suscribirse a notificaciones diarias |
| `/stop` | Darse de baja |
| `/precio` | Consulta manual del precio de hoy o mañana |
| `/ayuda` | Muestra los comandos disponibles |

**Lógica de `/precio`:** de 00:00 a 19:59 muestra los precios de hoy; de 20:00 a 23:59 muestra los de mañana (si ya están publicados).

## Ejemplo de notificación

```
⚡ Precio de la luz — Jueves 29 mayo

🟢 Más barata: 03:00h → 0,0821 €/kWh
🔴 Más cara: 19:00h → 0,2341 €/kWh
📊 Media del día: 0,1456 €/kWh

━━━━━━━━━━━━━━━━━━━━
🟢💰 00h 0,0923 ░░░░░
🟢💰 01h 0,0874 ░░░░
🟢💰 02h 0,0821 ░░░░ ← más barata
🟡  03h 0,1050 ░░░░░░
...
🔴💀 19h 0,2341 ████████████ ← más cara
━━━━━━━━━━━━━━━━━━━━
Datos: REE ESIOS · /ayuda
```

## Datos

Los precios se obtienen de la [API oficial ESIOS de Red Eléctrica](https://api.esios.ree.es). Los valores se muestran en €/kWh (la API devuelve €/MWh, se divide entre 1000).

## Licencia

[Creative Commons BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) — Uso libre con atribución, no comercial, obras derivadas bajo la misma licencia.
