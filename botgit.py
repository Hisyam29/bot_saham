import yfinance as yf
import pandas as pd
import requests
import time
import os

# =========================
# SWITCH ON/OFF
# =========================
RUN_BOT = os.getenv("RUN_BOT", "ON") # Default ke ON jika env belum diset saat testing

print("RUN_BOT:", RUN_BOT)

if RUN_BOT != "ON":
    print("Bot OFF")
    exit()

# =========================
# CONFIG
# =========================
TOKEN = os.getenv("TOKEN")
print("DEBUG TOKEN:", TOKEN)

CHAT_IDS = [
    "1280847575",
]

INTERVAL = "1d"
PERIOD = "60d"

ATR_PERIOD = 2
MULTIPLIER = 1

MIN_VALUE = 5_000_000_000  # 5M (Minimum Transaksi Saham)

# =========================
# TELEGRAM WITH MARKDOWN
# =========================
def send_telegram(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

    for chat_id in CHAT_IDS:
        data = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown" # Diaktifkan agar teks bot lebih rapi (tebal/miring)
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
# SUPER TREND 2,1 (RULE 1: AKUM/UPTREND)
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
# EVALUASI LOGIKA 3 RULES (MURNI HARD FILTER)
# =========================
def check_trend_following_rules(df):
    # Ambil data candle terakhir (hari ini/sesi ini) dan sebelumnya
    close_now = df['Close'].iloc[-1]
    volume_now = df['Volume'].iloc[-1]
    
    # Hitung nilai transaksi candle terakhir
    value = close_now * volume_now

    # --- RULE 1: UPTREND / AKUMULASI ---
    # Memastikan indikator SuperTrend berada di zona Bullish (True)
    rule_uptrend = df['in_uptrend'].iloc[-1] == True

    # --- RULE 2: MOMENTUM (MACD) ---
    # Hitung MACD Line & Signal Line secara manual
    ema12 = df['Close'].ewm(span=12, adjust=False).mean()
    ema26 = df['Close'].ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()

    # Momentum valid jika MACD Line berada di atas Signal Line (Golden Cross/Bullish Zone)
    rule_momentum = macd_line.iloc[-1] > signal_line.iloc[-1]

    # --- RULE 3: VOLUME MELEDAK ---
    # Hitung rata-rata volume 20 candle terakhir
    volume_avg = df['Volume'].rolling(20).mean().iloc[-1]
    
    # Kriteria volume meledak: Volume saat ini harus minimal 1.5x lipat dari rata-rata volume 20 hari
    rule_volume = volume_now >= (1.5 * volume_avg)
    
    # Hitung rasio ledakan volume untuk ditampilkan di notifikasi nanti
    vol_ratio = round(volume_now / volume_avg, 2) if volume_avg != 0 else 0

    # KESIMPULAN KAKU: Harus Lolos Ketiganya!
    if rule_uptrend and rule_momentum and rule_volume:
        return True, value, vol_ratio
    
    return False, value, vol_ratio

# =========================
# MAIN BOT (RUN SEKALI)
# =========================
def run_bot():
    symbols = load_symbols()

    send_telegram("🚀 *BOT TREND FOLLOWING AKTIF*\n_Memulai pemindaian pasar berbasis 3 Rules..._")

    print("Scanning market...")

    results = []

    for symbol in symbols:
        try:
            df = get_data(symbol)

            # Validasi minimal data agar indikator MA20 & MACD bisa dihitung
            if len(df) < 26:
                continue

            # Jalankan SuperTrend
            df = compute_supertrend(df)

            # Jalankan Cek 3 Rules & Ambil Data Transaksi
            is_valid, value, vol_ratio = check_trend_following_rules(df)
            price = df['Close'].iloc[-1]

            # Filter tambahan: likuiditas nilai transaksi harian/sesi
            if value < MIN_VALUE:
                continue

            # Jika lolos ketiga aturan, masukkan ke list hasil
            if is_valid:
                clean_symbol = symbol.replace(".JK", "") # Bersihkan teks .JK agar rapi di Telegram
                results.append((clean_symbol, price, vol_ratio))
                print(f"✅ {clean_symbol} LOLOS FILTER!")

        except Exception as e:
            print("Error:", symbol, e)

    # TELEGRAM OUTPUT
    if results:
        message = "🔥 *SAHAM LOLOS FILTER TREND FOLLOWING*\n"
        message += "⚡ _Kriteria: SuperTrend Uptrend + MACD Bullish + Volume > 1.5x MA20_\n\n"

        for r in results:
            message += f"📌 *{r[0]}*\n"
            message += f"├─ Harga: Rp {int(r[1])}\n"
            message += f"└─ Lonjakan Volume: *{r[2]}x* lipat rata-rata\n\n"

        send_telegram(message)
    else:
        send_telegram("❌ *Hasil Pemindaian:* Tidak ada saham yang memenuhi ketiga kriteria saat ini.")

    print("DONE\n")

# =========================
# RUN
# =========================
if __name__ == "__main__":
    run_bot()