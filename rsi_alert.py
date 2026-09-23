import os
import requests
import pandas as pd

# Configuración del par y temporalidad
SYMBOL = "ETHBTC"
INTERVAL = "1h"
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

def send_telegram_message(text):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("Error: Faltan las credenciales de Telegram.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}
    response = requests.post(url, json=payload)
    print("Respuesta de Telegram:", response.status_code)

def calculate_rsi(prices, period=14):
    delta = prices.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)

    # Suavizado de Wilder (método estándar para el RSI)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def main():
    # Obtener últimas 100 velas de 1 hora de la API pública de Binance
    url = f"https://api.binance.com/api/v3/klines?symbol={SYMBOL}&interval={INTERVAL}&limit=100"
    response = requests.get(url)
    response.raise_for_status()
    data = response.json()

    df = pd.DataFrame(data, columns=["open_time", "open", "high", "low", "close", "volume", "close_time", "qav", "num_trades", "taker_base", "taker_quote", "ignore"])
    df["close"] = df["close"].astype(float)

    # Calcular RSI de 14 periodos
    df["rsi"] = calculate_rsi(df["close"], period=14)
    
    # La vela cerrada más reciente de 1h es df.iloc[-2]
    last_closed_rsi = df["rsi"].iloc[-2]
    last_closed_price = df["close"].iloc[-2]

    print(f"RSI ETH/BTC (Última vela 1h cerrada): {last_closed_rsi:.2f} | Precio: {last_closed_price}")

    # Niveles de alerta
    RSI_OVERSOLD = 30
    RSI_OVERBOUGHT = 70

    if last_closed_rsi <= RSI_OVERSOLD:
        msg = f"📉 *ALERTA RSI SOBREVENTA (ETH/BTC 1h)*\n\nEl RSI ha bajado a *{last_closed_rsi:.2f}* (≤ {RSI_OVERSOLD}).\nPrecio de cierre: `{last_closed_price}` BTC"
        send_telegram_message(msg)
    elif last_closed_rsi >= RSI_OVERBOUGHT:
        msg = f"📈 *ALERTA RSI SOBRECOMPRA (ETH/BTC 1h)*\n\nEl RSI ha subido a *{last_closed_rsi:.2f}* (≥ {RSI_OVERBOUGHT}).\nPrecio de cierre: `{last_closed_price}` BTC"
        send_telegram_message(msg)
    else:
        print("El RSI se encuentra en zona neutra (entre 30 y 70). No requiere envío de notificación.")

if __name__ == "__main__":
    main()
