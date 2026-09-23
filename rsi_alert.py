import os
import sys
import requests
import pandas as pd

# Configuración
SYMBOL = "ETHBTC"
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

def send_telegram_message(text):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("⚠️ ALERTA: Faltan las variables TELEGRAM_TOKEN o CHAT_ID en Secrets.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}
    try:
        res = requests.post(url, json=payload, timeout=10)
        print(f"Respuesta de Telegram (Status {res.status_code}): {res.text}")
    except Exception as err:
        print(f"Error al conectar con Telegram: {err}")

def calculate_rsi(prices, period=14):
    delta = prices.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def get_klines():
    # 1. Probar API pública de Bybit (no bloquea IPs de GitHub Actions)
    try:
        url = f"https://api.bybit.com/v5/market/kline?category=spot&symbol={SYMBOL}&interval=60&limit=100"
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            data = res.json()
            raw_list = data["result"]["list"]
            raw_list.reverse()  # Ordenar de más antigua a más reciente
            closes = [float(item[4]) for item in raw_list]
            print("✅ Velas obtenidas con éxito desde Bybit.")
            return closes
    except Exception as e:
        print(f"⚠️ Error al consultar Bybit: {e}")

    # 2. Respaldo: API pública de KuCoin
    try:
        url = f"https://api.kucoin.com/api/v1/market/candles?symbol=ETH-BTC&type=1hour"
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            data = res.json()
            raw_list = data["data"]
            raw_list.reverse()
            closes = [float(item[2]) for item in raw_list]
            print("✅ Velas obtenidas con éxito desde KuCoin.")
            return closes
    except Exception as e:
        print(f"⚠️ Error al consultar KuCoin: {e}")

    raise RuntimeError("No se pudieron obtener datos de ninguna API alternativa.")

def main():
    print("--- INICIANDO VERIFICACIÓN DE RSI (ETH/BTC 1H) ---")

    closes = get_klines()
    df = pd.DataFrame({"close": closes})

    # Calcular RSI de 14 periodos
    df["rsi"] = calculate_rsi(df["close"], period=14)

    # Tomar la última vela cerrada de 1h
    last_closed_rsi = df["rsi"].iloc[-2]
    last_closed_price = df["close"].iloc[-2]

    print(f"📊 RSI ETH/BTC (Vela 1h cerrada): {last_closed_rsi:.2f} | Precio: {last_closed_price} BTC")

    RSI_OVERSOLD = 30
    RSI_OVERBOUGHT = 70

    if last_closed_rsi <= RSI_OVERSOLD:
        msg = f"📉 *ALERTA RSI SOBREVENTA (ETH/BTC 1h)*\n\nEl RSI ha bajado a *{last_closed_rsi:.2f}* (≤ {RSI_OVERSOLD}).\nPrecio: `{last_closed_price}` BTC"
        send_telegram_message(msg)
    elif last_closed_rsi >= RSI_OVERBOUGHT:
        msg = f"📈 *ALERTA RSI SOBRECOMPRA (ETH/BTC 1h)*\n\nEl RSI ha subido a *{last_closed_rsi:.2f}* (≥ {RSI_OVERBOUGHT}).\nPrecio: `{last_closed_price}` BTC"
        send_telegram_message(msg)
    else:
        print("ℹ️ El RSI se encuentra en zona neutra (30 - 70). Sin necesidad de alerta.")

if __name__ == "__main__":
    main()
