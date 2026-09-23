name: Alerta RSI ETH/BTC

on:
  schedule:
    # Se ejecuta automáticamente al inicio de cada hora (ej: 10:00, 11:00, 12:00 UTC)
    - cron: '0 * * * *'
  workflow_dispatch: # Permite ejecutar la prueba manualmente en cualquier momento

jobs:
  check-rsi:
    runs-on: ubuntu-latest
    steps:
      - name: Descargar código del repositorio
        uses: actions/checkout@v4

      - name: Configurar Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.10'

      - name: Instalar librerías
        run: |
          python -m pip install --upgrade pip
          pip install requests pandas

      - name: Ejecutar script de RSI
        env:
          TELEGRAM_TOKEN: ${{ secrets.TELEGRAM_TOKEN }}
          CHAT_ID: ${{ secrets.CHAT_ID }}
        run: python rsi_alert.py
