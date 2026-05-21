import os
import asyncio
import logging
from datetime import datetime
import pytz
from telegram import Update, Bot
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import httpx
from bs4 import BeautifulSoup

# ─── CONFIG ───────────────────────────────────────────────────────────────────
TOKEN   = os.environ["BOT_TOKEN"]
CHAT_ID = int(os.environ["CHAT_ID"])
BCN_TZ  = pytz.timezone("Europe/Madrid")

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# ─── RODALIES SANTS ───────────────────────────────────────────────────────────
async def get_trenes_sants():
    """Llegadas en tiempo real a Barcelona Sants via Rodalies Renfe."""
    url = "https://horarios.renfe.com/cer/hjcer310.jsp?NUCLEO=50&I=s&CP=NO&TIPOCONSULTA=A&Idioma=CA&Estacion=79600"
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(url, headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(r.text, "html.parser")
        rows = soup.select("table tr")[1:8]
        lines = []
        for row in rows:
            cols = [td.get_text(strip=True) for td in row.select("td")]
            if len(cols) >= 3:
                lines.append(f"🚂 {cols[0]}  {cols[1]}  ➜  {cols[2]}")
        return "\n".join(lines) if lines else "No hay datos en este momento."
    except Exception as e:
        log.error(e)
        return "❌ No se pudo obtener info de trenes ahora mismo."

# ─── VUELOS AENA ──────────────────────────────────────────────────────────────
async def get_vuelos(terminal: str):
    """Llegadas al aeropuerto El Prat — T1 o T2."""
    t = "T1" if "1" in terminal else "T2"
    url = f"https://www.aena.es/es/aeropuerto-barcelona/llegadas.html"
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(url, headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(r.text, "html.parser")
        rows = soup.select("tr.flight-row")[:8]
        lines = []
        for row in rows:
            cols = [td.get_text(strip=True) for td in row.select("td")]
            if len(cols) >= 4:
                lines.append(f"✈️ {cols[0]}  {cols[1]}  {cols[2]}  {cols[3]}")
        if lines:
            return f"*Llegadas {t} — El Prat*\n\n" + "\n".join(lines)
        return f"No hay datos de llegadas {t} en este momento."
    except Exception as e:
        log.error(e)
        return f"❌ No se pudo obtener info de vuelos {t} ahora mismo."

# ─── EVENTOS CAMP NOU ──────────────────────────────────────────────────────────
async def get_eventos_campnou():
    """Partidos y eventos hoy en el Camp Nou."""
    hoy = datetime.now(BCN_TZ).strftime("%Y-%m-%d")
    url = "https://www.fcbarcelona.es/es/calendario"
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(url, headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(r.text, "html.parser")
        eventos = []
        for item in soup.select(".match-item, .event-item, article"):
            texto = item.get_text(separator=" ", strip=True)
            if hoy in texto or "hoy" in texto.lower():
                eventos.append(texto[:120])
        return eventos[:3] if eventos else []
    except Exception as e:
        log.error(e)
        return []

# ─── EVENTOS PALAU SANT JORDI ──────────────────────────────────────────────────
async def get_eventos_palau():
    """Conciertos y eventos hoy en el Palau Sant Jordi."""
    hoy_str = datetime.now(BCN_TZ).strftime("%d/%m/%Y")
    url = "https://www.palausantjordi.cat/es/agenda"
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(url, headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(r.text, "html.parser")
        eventos = []
        for item in soup.select(".event, .agenda-item, article, li"):
            texto = item.get_text(separator=" ", strip=True)
            if hoy_str in texto or "hoy" in texto.lower():
                eventos.append(texto[:120])
        return eventos[:3] if eventos else []
    except Exception as e:
        log.error(e)
        return []

# ─── ALERTA DIARIA ────────────────────────────────────────────────────────────
async def alerta_diaria(context: ContextTypes.DEFAULT_TYPE):
    bot: Bot = context.bot
    msgs = []

    campnou = await get_eventos_campnou()
    if campnou:
        msgs.append("⚽ *Camp Nou hoy:*\n" + "\n".join(campnou))

    palau = await get_eventos_palau()
    if palau:
        msgs.append("🎵 *Palau Sant Jordi hoy:*\n" + "\n".join(palau))

    if msgs:
        texto = "🗓 *Eventos hoy en Barcelona*\n\n" + "\n\n".join(msgs)
        await bot.send_message(chat_id=CHAT_ID, text=texto, parse_mode="Markdown")
        log.info("Alerta diaria enviada.")
    else:
        log.info("Sin eventos hoy — no se envía alerta.")

# ─── HANDLERS ─────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Hola Sunni! Soy tu bot de Barcelona.\n\n"
        "📌 *Comandos disponibles:*\n"
        "• `trenes` — Llegadas a Sants ahora\n"
        "• `vuelos t1` — Llegadas Terminal 1\n"
        "• `vuelos t2` — Llegadas Terminal 2\n"
        "• `eventos` — Ver eventos de hoy\n\n"
        "⏰ Y cada mañana a las 10h te aviso si hay partido o concierto.",
        parse_mode="Markdown"
    )

async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.lower().strip()

    if "tren" in texto or "sants" in texto:
        await update.message.reply_text("🔍 Buscando trenes...")
        info = await get_trenes_sants()
        await update.message.reply_text(info)

    elif "vuelo" in texto or "prat" in texto or "aeropuerto" in texto:
        terminal = "T1" if "1" in texto else "T2" if "2" in texto else "T1"
        await update.message.reply_text(f"🔍 Buscando vuelos {terminal}...")
        info = await get_vuelos(terminal)
        await update.message.reply_text(info, parse_mode="Markdown")

    elif "evento" in texto or "hoy" in texto or "partido" in texto or "concierto" in texto:
        await update.message.reply_text("🔍 Buscando eventos hoy...")
        cn = await get_eventos_campnou()
        ps = await get_eventos_palau()
        if cn or ps:
            msg = ""
            if cn: msg += "⚽ *Camp Nou:*\n" + "\n".join(cn) + "\n\n"
            if ps: msg += "🎵 *Palau Sant Jordi:*\n" + "\n".join(ps)
            await update.message.reply_text(msg.strip(), parse_mode="Markdown")
        else:
            await update.message.reply_text("Hoy no hay eventos registrados en Camp Nou ni Palau Sant Jordi.")

    else:
        await update.message.reply_text(
            "No te entiendo 😅\nPrueba con: *trenes*, *vuelos t1*, *vuelos t2*, *eventos*",
            parse_mode="Markdown"
        )

# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Alerta diaria a las 10:00 hora Barcelona
    job_queue = app.job_queue
    now_bcn = datetime.now(BCN_TZ)
    target = now_bcn.replace(hour=10, minute=0, second=0, microsecond=0)
    if target < now_bcn:
        from datetime import timedelta
        target += timedelta(days=1)

    job_queue.run_daily(
        alerta_diaria,
        time=target.timetz(),
        days=(0, 1, 2, 3, 4, 5, 6)
    )

    log.info("Bot arrancado ✅")
    app.run_polling()

if __name__ == "__main__":
    main()
