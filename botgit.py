import yfinance as yf
import pandas as pd
import requests
import time
import os

# =========================
# SWITCH ON/OFF
# =========================
RUN_BOT = os.getenv("RUN_BOT")

print("RUN_BOT:", RUN_BOT)

if RUN_BOT != "ON":
    print("Bot OFF")
    exit()

# =========================
# CONFIG
# =========================
TOKEN = os.getenv("TOKEN")

CHAT_IDS = [
    "1280847575",
]

INTERVAL = "4h"
PERIOD = "30d"

ATR_PERIOD = 2
MULTIPLIER = 1

MIN_VALUE = 5_000_000_000  # 5M

# =========================
# TELEGRAM
# =========================
def send_telegram(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    
    for chat_id in CHAT_IDS:
        data = {
            "chat_id": chat_id,
            "text": message
        }
        try:
            res = requests.post(url, data=data)
            print(f"Telegram ke {chat_id}:", res.text)
        except Exception as e:
            print(f"Gagal kirim ke {chat_id}", e)

# =========================
# LOAD SAHAM DARI EXCEL
# =========================
def load_symbols():
    df = pd.read_excel("saham.xlsx")

    print("KOLOM TERDETEKSI:", df.columns)

    symbols = df["Kode"].tolist()
    symbols = [str(s).strip().upper() for s in symbols if str(s) != 'nan']
    symbols = [s + ".JK" for s in symbols]

    print("TOTAL SAHAM:", len(symbols))
    print(symbols[:10])

    return symbols

# =========================
# GET DATA
# =========================
def get_data(symbol):
    df = yf.download(symbol, period=PERIOD, interval=INTERVAL, progress=False)

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df.dropna(inplace=True)
    return df

# =========================
# SUPER TREND 2,1
# =========================
def compute_supertrend(df):
    df = df.copy()

    df['H-L'] = df['High'] - df['Low']
    df['H-C'] = (df['High'] - df['Close'].shift()).abs()
    df['L-C'] = (df['Low'] - df['Close'].shift()).abs()

    df['TR'] = df[['H-L','H-C','L-C']].max(axis=1)
    df['ATR'] = df['TR'].rolling(ATR_PERIOD).mean()

    hl2 = (df['High'] + df['Low']) / 2

    df['upperband'] = hl2 + MULTIPLIER * df['ATR']
    df['lowerband'] = hl2 - MULTIPLIER * df['ATR']

    df['in_uptrend'] = True

    for i in range(1, len(df)):
        if df['Close'].iloc[i] > df['upperband'].iloc[i-1]:
            df.loc[df.index[i], 'in_uptrend'] = True
        elif df['Close'].iloc[i] < df['lowerband'].iloc[i-1]:
            df.loc[df.index[i], 'in_uptrend'] = False
        else:
            df.loc[df.index[i], 'in_uptrend'] = df['in_uptrend'].iloc[i-1]

    return df

# =========================
# SCORING SYSTEM (0–100)
# =========================
def calculate_score(df):
    score = 0

    close = df['Close'].iloc[-1]
    open_ = df['Open'].iloc[-1]
    high = df['High'].iloc[-1]
    low = df['Low'].iloc[-1]

    volume_now = df['Volume'].iloc[-1]
    volume_avg = df['Volume'].rolling(20).mean().iloc[-1]

    value = close * volume_now

    current = df['in_uptrend'].iloc[-1]
    previous = df['in_uptrend'].iloc[-2]

    high_5 = df['High'].rolling(5).max().iloc[-2]
    high_10 = df['High'].rolling(10).max().iloc[-2]

    # 1. SUPER TREND
    if current and not previous:
        score += 25
    elif current:
        score += 15

    # 2. VOLUME
    ratio = volume_now / volume_avg
    if ratio > 2:
        score += 20
    elif ratio > 1.5:
        score += 15
    elif ratio > 1.2:
        score += 10

    # 3. VALUE
    if value > 20_000_000_000:
        score += 20
    elif value > 10_000_000_000:
        score += 15
    elif value > MIN_VALUE:
        score += 10

    # 4. BREAKOUT
    if close > high_10:
        score += 20
    elif close > high_5:
        score += 10

    # 5. CANDLE STRENGTH
    body = abs(close - open_)
    range_ = high - low if (high - low) != 0 else 1
    strength = body / range_

    if strength > 0.7:
        score += 15
    elif strength > 0.5:
        score += 10

    return score, value

# =========================
# MAIN BOT (RUN SEKALI)
# =========================
def run_bot():
    symbols = load_symbols()

    send_telegram("🚀 BOT AKTIF - HYBRID + SCORING 100")

    print("Scanning market...")

    results = []

    for symbol in symbols:
        try:
            df = get_data(symbol)

            if len(df) < 20:
                continue

            df = compute_supertrend(df)

            score, value = calculate_score(df)
            price = df['Close'].iloc[-1]

            if value < MIN_VALUE:
                continue

            if score >= 40:
                results.append((symbol, score, price, value))

            print(symbol, "| Score:", score)

        except Exception as e:
            print("Error:", symbol, e)

    # SORTING
    results = sorted(results, key=lambda x: x[1], reverse=True)

    # TELEGRAM OUTPUT
    if results:
        message = "🔥 RANKING SAHAM TERBAIK\n\n"

        for r in results[:10]:
            message += f"{r[0]} | Score: {r[1]} | Price: {int(r[2])}\n"

        send_telegram(message)

    else:
        send_telegram("❌ Tidak ada saham sesuai kriteria")

    print("DONE\n")

# =========================
# RUN
# =========================
if __name__ == "__main__":
    run_bot()