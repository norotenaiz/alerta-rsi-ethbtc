"""
Bot de alertas RSI multi-par y multi-temporalidad.

Analiza el RSI de:
    - ETH/BTC  (fuente: KuCoin, con fallback a OKX)
    - XAU/XAG  (fuente: Yahoo Finance, ratio oro/plata)

En dos temporalidades: velas de 1 hora y velas de 15 minutos.

Cuando el RSI de cualquier combinación par+temporalidad supera los umbrales
de sobrecompra/sobreventa, se envía una alerta por Telegram.

Requisitos (requirements.txt):
    requests
    pandas
    yfinance
"""

import os
import sys
import traceback
from dataclasses import dataclass
from typing import Optional

import requests
import pandas as pd

# ---------------------------------------------------------
# Configuración y Constantes
# ---------------------------------------------------------
RSI_PERIOD = 14
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30

# .strip() elimina automáticamente cualquier espacio o salto de línea (\n) accidental
TELEGRAM_TOKEN = (os.getenv("TELEGRAM_TOKEN") or "").strip()
CHAT_ID = (os.getenv("CHAT_ID") or "").strip()

# Cada timeframe define cómo pedir esas velas a cada proveedor de datos.
TIMEFRAMES = [
    {
        "label": "1h",
        "kucoin_type": "1hour",
        "okx_bar": "1H",
        "yf_interval": "60m",
        "yf_period": "1mo",   # ventana de histórico a descargar en Yahoo Finance
    },
    {
        "label": "15m",
        "kucoin_type": "15min",
        "okx_bar": "15m",
        "yf_interval": "15m",
        "yf_period": "5d",    # Yahoo solo da intradía de 15m para los últimos ~60 días
    },
]

# Cada par define su tipo ("crypto" o "metals") y los símbolos que necesita cada fuente.
PAIRS = [
    {
        "name": "ETH/BTC",
        "type": "crypto",
        "kucoin_symbol": "ETH-BTC",
        "okx_symbol": "ETH-BTC",
    },
    {
        "name": "XAU/XAG",
        "type": "metals",
        "xau_ticker": "XAUUSD=X",
        "xag_ticker": "XAGUSD=X",
    },
]


# ---------------------------------------------------------
# Telegram
# ---------------------------------------------------------
def send_telegram_message(message: str) -> bool:
    """Envía un mensaje formateado a través de Telegram API."""
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("⚠️ Advertencia: No se han configurado TELEGRAM_TOKEN o CHAT_ID en Secrets.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        print("✅ Mensaje enviado a Telegram correctamente.")
        return True
    except Exception as e:
        print(f"❌ Error al enviar mensaje a Telegram: {e}")
        return False


# ---------------------------------------------------------
# Fuentes de datos: Cripto (KuCoin / OKX)
# ---------------------------------------------------------
def fetch_klines_kucoin(symbol: str, type_kline: str) -> Optional[pd.DataFrame]:
    """Fuente Primaria (cripto): obtiene velas desde la API pública de KuCoin."""
    url = "https://api.kucoin.com/api/v1/market/candles"
    params = {"symbol": symbol, "type": type_kline}

    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") == "200000" and data.get("data"):
            df = pd.DataFrame(
                data["data"],
                columns=["time", "open", "close", "high", "low", "volume", "turnover"],
            )
            # KuCoin entrega las velas de reciente a antiguo; invertimos el orden
            df = df.iloc[::-1].reset_index(drop=True)
            df["close"] = df["close"].astype(float)
            return df[["close"]]
    except Exception as e:
        print(f"⚠️ Error al consultar KuCoin ({symbol}, {type_kline}): {e}")
    return None


def fetch_klines_okx(symbol: str, bar: str) -> Optional[pd.DataFrame]:
    """Fuente Secundaria (cripto): obtiene velas desde la API pública de OKX."""
    url = "https://www.okx.com/api/v5/market/candles"
    params = {"instId": symbol, "bar": bar, "limit": "150"}

    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") == "0" and data.get("data"):
            df = pd.DataFrame(
                data["data"],
                columns=["ts", "open", "high", "low", "close", "vol", "volCcy", "volCcyQuote", "confirm"],
            )
            df = df.iloc[::-1].reset_index(drop=True)
            df["close"] = df["close"].astype(float)
            return df[["close"]]
    except Exception as e:
        print(f"⚠️ Error al consultar OKX ({symbol}, {bar}): {e}")
    return None


def fetch_crypto_closes(pair: dict, tf: dict) -> Optional[pd.DataFrame]:
    """Obtiene el cierre de velas para un par cripto, con fallback KuCoin -> OKX."""
    df = fetch_klines_kucoin(pair["kucoin_symbol"], tf["kucoin_type"])
    if df is None or df.empty:
        print(f"🔄 [{pair['name']} {tf['label']}] KuCoin falló, probando OKX...")
        df = fetch_klines_okx(pair["okx_symbol"], tf["okx_bar"])
    return df


# ---------------------------------------------------------
# Fuente de datos: Metales (XAU/XAG vía Yahoo Finance)
# ---------------------------------------------------------
def fetch_metals_ratio_closes(pair: dict, tf: dict) -> Optional[pd.DataFrame]:
    """
    Obtiene el ratio XAU/XAG (oro/plata) usando velas intradía de Yahoo Finance.
    Se descargan las series de XAUUSD=X y XAGUSD=X por separado y se calcula
    el ratio de cierre vela a vela (mismo enfoque que un par-trading de cripto).
    """
    try:
        import yfinance as yf
    except ImportError:
        print("❌ Falta la librería 'yfinance'. Añádela a requirements.txt (pip install yfinance).")
        return None

    try:
        xau = yf.download(
            pair["xau_ticker"], interval=tf["yf_interval"], period=tf["yf_period"],
            progress=False, auto_adjust=True,
        )
        xag = yf.download(
            pair["xag_ticker"], interval=tf["yf_interval"], period=tf["yf_period"],
            progress=False, auto_adjust=True,
        )

        if xau is None or xag is None or xau.empty or xag.empty:
            print(f"⚠️ Yahoo Finance no devolvió datos para {pair['name']} ({tf['label']}).")
            return None

        merged = pd.merge(
            xau[["Close"]], xag[["Close"]],
            left_index=True, right_index=True,
            suffixes=("_xau", "_xag"),
        ).dropna()

        if merged.empty:
            print(f"⚠️ No se pudieron alinear las velas de XAU y XAG ({tf['label']}).")
            return None

        merged["close"] = merged["Close_xau"] / merged["Close_xag"]
        return merged[["close"]].reset_index(drop=True)
    except Exception as e:
        print(f"⚠️ Error al consultar Yahoo Finance ({pair['name']}, {tf['label']}): {e}")
        return None


# ---------------------------------------------------------
# Cálculo de RSI
# ---------------------------------------------------------
def calculate_rsi(df: pd.DataFrame, period: int = RSI_PERIOD) -> pd.DataFrame:
    """Calcula el RSI utilizando suavizado exponencial de Wilder."""
    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss
    df["rsi"] = 100 - (100 / (1 + rs))
    return df


# ---------------------------------------------------------
# Evaluación y alerta por combinación par + temporalidad
# ---------------------------------------------------------
@dataclass
class AnalysisResult:
    pair_name: str
    timeframe: str
    price: float
    rsi: float
    alert: Optional[str]  # "sobrecompra", "sobreventa" o None


def analyze_pair_timeframe(pair: dict, tf: dict) -> Optional[AnalysisResult]:
    """Descarga velas, calcula RSI y determina si hay que alertar para un par+timeframe."""
    if pair["type"] == "crypto":
        df = fetch_crypto_closes(pair, tf)
    elif pair["type"] == "metals":
        df = fetch_metals_ratio_closes(pair, tf)
    else:
        print(f"❌ Tipo de par desconocido: {pair['type']}")
        return None

    if df is None or df.empty or len(df) < RSI_PERIOD + 1:
        print(f"❌ Datos insuficientes para {pair['name']} ({tf['label']}).")
        return None

    df = calculate_rsi(df, period=RSI_PERIOD)
    last = df.iloc[-1]

    if pd.isna(last["rsi"]):
        print(f"❌ RSI no calculable todavía para {pair['name']} ({tf['label']}).")
        return None

    rsi_value = round(float(last["rsi"]), 2)
    price = float(last["close"])

    alert = None
    if rsi_value <= RSI_OVERSOLD:
        alert = "sobreventa"
    elif rsi_value >= RSI_OVERBOUGHT:
        alert = "sobrecompra"

    print(f"📊 [{pair['name']} | {tf['label']}] Precio/Ratio: {price:.6f} — RSI: {rsi_value}")

    return AnalysisResult(pair_name=pair["name"], timeframe=tf["label"], price=price, rsi=rsi_value, alert=alert)


def build_alert_message(result: AnalysisResult) -> str:
    titulo = "SOBRECOMPRA" if result.alert == "sobrecompra" else "SOBREVENTA"
    umbral = RSI_OVERBOUGHT if result.alert == "sobrecompra" else RSI_OVERSOLD
    comparador = ">=" if result.alert == "sobrecompra" else "<="

    return (
        f"🚨 *ALERTA RSI: {titulo}*\n\n"
        f"• *Par:* {result.pair_name}\n"
        f"• *Temporalidad:* {result.timeframe}\n"
        f"• *RSI Actual:* `{result.rsi}` ({comparador} {umbral})\n"
        f"• *Precio/Ratio Actual:* `{result.price:.6f}`"
    )


# ---------------------------------------------------------
# Main
# ---------------------------------------------------------
def main():
    print("🔍 Iniciando análisis de RSI multi-par / multi-temporalidad...\n")

    any_error = False

    for pair in PAIRS:
        for tf in TIMEFRAMES:
            try:
                result = analyze_pair_timeframe(pair, tf)
            except Exception:
                any_error = True
                print(f"❌ Error inesperado analizando {pair['name']} ({tf['label']}):")
                traceback.print_exc()
                continue

            if result is None:
                any_error = True
                continue

            if result.alert:
                send_telegram_message(build_alert_message(result))
            else:
                print(
                    f"ℹ️ [{pair['name']} | {tf['label']}] RSI en zona neutral "
                    f"({RSI_OVERSOLD} < {result.rsi} < {RSI_OVERBOUGHT}). Sin notificación."
                )

    print("\n✅ Análisis finalizado.")
    # Salir con código distinto de 0 si algo falló, útil para detectar fallos en GitHub Actions
    if any_error:
        sys.exit(1)


if __name__ == "__main__":
    main()
