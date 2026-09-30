import json, os, sys
from pathlib import Path
import requests

URL = "https://omni-client-api.prod.ap-northeast-1.variational.io/metadata/stats"
TARGET = 30.0   # alerta al llegar a este PNL
REARM = 25.0    # se vuelve a armar cuando baja de aquí

POSITIONS = {
    "XAU": {"side": -1, "qty": 1.16996, "entry": 4190.03},  # SHORT
    "XAG": {"side": +1, "qty": 80.468,  "entry": 60.9271},  # LONG
}

STATE = Path("state/state.json")
STATE.parent.mkdir(exist_ok=True)


def load_state():
    try:
        return json.loads(STATE.read_text())
    except Exception:
        return {"alerted": False}


def telegram(text):
    token = os.environ["TELEGRAM_TOKEN"].strip()
    chat_id = os.environ["CHAT_ID"].strip()
    r = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data={"chat_id": chat_id, "text": text},
        timeout=20,
    )
    r.raise_for_status()


def main():
    r = requests.get(URL, timeout=20)
    r.raise_for_status()
    listings = {l["ticker"].upper(): l for l in r.json().get("listings", [])}

    marks = {}
    for t in POSITIONS:
        try:
            m = float(listings[t]["mark_price"])
            assert m > 0
            marks[t] = m
        except Exception:
            near = [k for k in listings if "XA" in k or "GOLD" in k or "SILVER" in k]
            print(f"Mark price no válido para {t}. Tickers parecidos: {near}")
            sys.exit(1)  # no alertar con datos dudosos

    pnl, lines = {}, []
    for t, p in POSITIONS.items():
        pnl[t] = p["side"] * (marks[t] - p["entry"]) * p["qty"]
        lado = "SHORT" if p["side"] < 0 else "LONG"
        lines.append(
            f"{t} {lado}\nEntry: ${p['entry']:,.4f}\nMark: ${marks[t]:,.4f}\nUPNL: {pnl[t]:+,.2f}$\n"
        )
    total = sum(pnl.values())
    print(f"XAU {pnl['XAU']:+.2f} | XAG {pnl['XAG']:+.2f} | TOTAL {total:+.2f}")

    state = load_state()
    if total >= TARGET and not state["alerted"]:
        telegram(
            "🔔 VARIATIONAL PNL\n\n" + "\n".join(lines)
            + f"━━━━━━━━━━━━\nTOTAL: {total:+,.2f}$\n🎯 Objetivo ${TARGET:.0f} alcanzado"
        )
        state["alerted"] = True
    elif total < REARM:
        state["alerted"] = False

    STATE.write_text(json.dumps(state))


if __name__ == "__main__":
    main()
