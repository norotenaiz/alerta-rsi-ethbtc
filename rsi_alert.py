import os
import requests
import pandas as pd

# ---------------------------------------------------------
# Configuración y Constantes
# ---------------------------------------------------------
SYMBOL_BINANCE = "ETHBTC"
SYMBOL_KUCOIN = "ETH-BTC"
PERIOD = 14
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")


def send_telegram_message(message: str) -> bool:
    """Envía un mensaje formateado a través de Telegram API."""
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("⚠️ Advertencia: No se han configurado TELEGRAM_TOKEN o CHAT_ID en Secrets.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        print("✅ Mensaje enviado a Telegram correctamente.")
        return True
    except Exception as e:
        print(f"❌ Error al enviar mensaje a Telegram: {e}")
        return False


def fetch_klines_binance(symbol="ETHBTC", interval="1h", limit=100):
    """Obtiene velas de 1 hora desde la API pública de Binance Spot."""
    url = "https://api.binance.com/api/v3/klines"
    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": limit
    }

    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        raw_klines = resp.json()

        # Estructura Binance: [Open Time, Open, High, Low, Close, Volume, ...]
        df = pd.DataFrame(
            raw_klines,
            columns=["timestamp", "open", "high", "low", "close", "volume", 
                     "close_time", "qav", "num_trades", "tbb", "tbq", "ignore"]
        )
        df["close"] = df["close"].astype(float)
        return df
    except Exception as e:
        print(f"⚠️ Error al consultar Binance: {e}")
    return None


def fetch_klines_kucoin(symbol="ETH-BTC", type_kline="1hour"):
    """Respaldo: obtiene velas desde la API pública de KuCoin."""
    url = "https://api.kucoin.com/api/v1/market/candles"
    params = {
        "symbol": symbol,
        "type": type_kline
    }

    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") == "200000":
            df = pd.DataFrame(
                data["data"],
                columns=["time", "open", "close", "high", "low", "volume", "turnover"]
            )
            # KuCoin entrega de reciente a antiguo, invertimos el orden
            df = df.iloc[::-1].reset_index(drop=True)
            df["close"] = df["close"].astype(float)
            return df
    except Exception as e:
        print(f"⚠️ Error al consultar KuCoin: {e}")
    return None


def calculate_rsi(df: pd.DataFrame, period=14) -> pd.DataFrame:
    """Calcula el RSI utilizando suavizado exponencial de Wilder."""
    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss
    df["rsi"] = 100 - (100 / (1 + rs))
    return df


def main():
    print("🔍 Obteniendo datos de mercado para ETH/BTC (Velas 1H)...")

    # Intentar primero Binance
    df = fetch_klines_binance(symbol=SYMBOL_BINANCE, interval="1h", limit=100)

    # Si falla Binance, intentar KuCoin
    if df is None or df.empty:
        print("🔄 Intentando proveedor secundario (KuCoin)...")
        df = fetch_klines_kucoin(symbol=SYMBOL_KUCOIN, type_kline="1hour")

    if df is None or df.empty:
        print("❌ No se pudieron obtener velas de ningún Exchange.")
        return

    # Calcular RSI
    df = calculate_rsi(df, period=PERIOD)

    # Evaluar la vela más reciente
    current_candle = df.iloc[-1]
    current_rsi = round(float(current_candle["rsi"]), 2)
    current_price = float(current_candle["close"])

    print(f"📊 Precio ETH/BTC actual: {current_price:.6f} BTC")
    print(f"📈 RSI actual (Vela 1H): {current_rsi}")

    # Verificar umbrales de alerta
    if current_rsi <= RSI_OVERSOLD:
        msg = (
            f"🚨 *ALERTA RSI: SOBREVENTA*\n\n"
            f"• *Par:* ETH/BTC\n"
            f"• *Temporalidad:* 1 hora\n"
            f"• *RSI Actual:* `{current_rsi}` (<= {RSI_OVERSOLD})\n"
            f"• *Precio Actual:* `{current_price:.6f}` BTC"
        )
        send_telegram_message(msg)
    elif current_rsi >= RSI_OVERBOUGHT:
        msg = (
            f"🚨 *ALERTA RSI: SOBRECOMPRA*\n\n"
            f"• *Par:* ETH/BTC\n"
            f"• *Temporalidad:* 1 hora\n"
            f"• *RSI Actual:* `{current_rsi}` (>= {RSI_OVERBOUGHT})\n"
            f"• *Precio Actual:* `{current_price:.6f}` BTC"
        )
        send_telegram_message(msg)
    else:
        print(f"ℹ️ RSI en zona neutral ({RSI_OVERSOLD} < {current_rsi} < {RSI_OVERBOUGHT}). Sin notificación.")


if __name__ == "__main__":
    main()
