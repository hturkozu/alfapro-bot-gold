# AlfaPro Bot

Bitget USDT-M futures için otomatik al-sat botu. Docker'sız, self-host, AI sinyal validasyonu destekli.

**Aktif sürüm:** `APB-FINAL-v1.0.0` — canlı üretim
**Repo:** `git@github.com:hturkozu/alfapro-bot-gold.git` (private)

> Yol haritası, seri kayıt defteri ve ürün özeti için [`PROJECT.md`](PROJECT.md).

---

## Hızlı Kurulum

### 1. Gereksinimler
- Python 3.11 veya üstü
- (Linux sunucu için) `systemd`, `nginx` (Faz 5'te)

### 2. Depoyu indir, sanal ortam kur

```bash
git clone git@github.com:hturkozu/alfapro-bot-gold.git
cd alfapro-bot-gold

python3.11 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Master key üret

```bash
python scripts/generate_master_key.py
```

Çıktıyı kopyala.

### 4. `.env` dosyası oluştur

```bash
cp .env.example .env
```

`.env` dosyasını aç ve `ALFAPRO_MASTER_KEY=` satırına üretilen key'i yapıştır.

**Güvenlik:** `.env` dosyasının izinlerini sıkılaştır:
```bash
chmod 600 .env
```

### 5. Çalıştır

```bash
uvicorn app.main:app --reload
```

Paneli aç: <http://localhost:8000>

API dokümantasyonu: <http://localhost:8000/docs>

---

## İlk Kullanım

1. Bitget hesabına gir → **API Management** → yeni API oluştur.
2. Yetkiler: **Read + Futures Trade** (ASLA withdraw açma).
3. Mümkünse IP whitelist ekle.
4. API key, secret ve passphrase'i kopyala.
5. Panel → **Ayarlar** sekmesi → form doldur → **Kaydet** → **Bağlantıyı Test Et**.

Test başarılıysa USDT bakiyen gösterilir.

---

## Proje Yapısı

```
alfapro-bot-gold/
├── PROJECT.md              # Yol haritası, ilerleme takibi
├── README.md               # Bu dosya
├── requirements.txt
├── .env.example
├── app/
│   ├── main.py             # FastAPI entry + lifespan
│   ├── config.py           # Settings (pydantic-settings)
│   ├── core/               # database, security (Fernet), logger
│   ├── models/             # SQLAlchemy ORM modelleri
│   ├── schemas/            # Pydantic şemaları
│   ├── routers/            # health, settings, market, strategies, trading, risk, logs, backtest, ws
│   └── services/
│       ├── bitget_client.py, market_data.py, indicators.py, fibonacci.py, smc.py
│       ├── ai_validator.py, risk_manager.py, scheduler.py
│       ├── paper_trader.py, live_trader.py, backtester.py
│       ├── telegram_notifier.py, log_reader.py, trade_stats.py, commodity_catalog.py
│       └── strategies/     # base, registry + scalp_ema_rsi, scalp_sweep_momentum, swing_smc_fib
├── frontend/
│   └── index.html          # Alpine.js + Tailwind tek-sayfa panel
├── scripts/
│   ├── generate_master_key.py
│   └── test_paper_improvements.py
├── data/                   # SQLite DB (git-ignore)
└── logs/                   # Log dosyaları (git-ignore)
```

---

## Paper Trading Davranışı

Paper modu artık üç katmanlı bir realizm/risk yönetimi içerir; hepsi `.env` üzerinden yapılandırılır.

### 1. Komisyon modeli
Açılış ve kapanışta taker fee otomatik düşülür; `Position.pnl_usdt` net PnL gösterir, `Trade` kayıtlarında `fee_usdt` doludur.

```
PAPER_TAKER_FEE_PCT=0.06    # Bitget USDT-M default
```

### 2. Wick-bazlı SL/TP
Scheduler her açık pozisyon için 1m mum yüksek/düşüğünü çekip `check_sl_tp`'ye geçirir; tick'ler arası wick'ler kaçırılmaz. Aynı barda hem SL hem TP varsa konservatif şekilde **SL öncelikli**.

### 3. Break-even & trailing stop
`apply_trailing` her tick'te SL'i sadece **lehte yönde** sıkıştırır (asla geriletmez). BE eşiği = TP mesafesinin %X'i; trailing = peak × (1 ± y/100). İkisi aynı anda aktif olabilir, en sıkı olan kazanır, SL TP'yi geçemez.

```
PAPER_BREAKEVEN_TRIGGER_PCT=50    # 0 = kapalı; 50 = TP'nin yarısına gelince BE
PAPER_BREAKEVEN_OFFSET_PCT=0.06   # entry üstü/altı tampon (fee karşılığı)
PAPER_TRAILING_PCT=0.4            # 0 = kapalı; %0.4 trailing
```

Default'lar üretimde **kapalı** (BE/trailing 0). `.env.example` referans alınabilir.

---

## Geliştirme

### Testleri çalıştır
```bash
# Paper trading geliştirmeleri (fee, wick, BE/trailing) — 24 test
PYTHONUTF8=1 ./alfapro-bot-gold/venv311/Scripts/python.exe scripts/test_paper_improvements.py
```

### Veritabanını sıfırla
```bash
rm data/alfapro.db
```

Uygulama yeniden başladığında tablolar otomatik oluşturulur.

### Logları izle
```bash
tail -f logs/alfapro.log
tail -f logs/trades.log
```

---

## Üretim Deployment

### Tek komutluk kurulum (Ubuntu 22.04/24.04)

```bash
sudo ./install.sh
```

Bu script:
- Python 3.11 + bağımlılıklar
- `alfapro` sistem kullanıcısı
- `/opt/alfapro-bot` dizini (isteğe bağlı: `INSTALL_DIR=...` ile değiştir)
- Fernet master key üretimi + `.env` dosyası
- systemd servis kaydı + başlatma

yapar. Detaylar: [`install.sh`](install.sh)

### systemd servisi

```bash
# Durum
sudo systemctl status alfapro-bot

# Canlı log
sudo journalctl -u alfapro-bot -f

# Yeniden başlat
sudo systemctl restart alfapro-bot
```

### Nginx + HTTPS

```bash
sudo cp deploy/nginx.conf.example /etc/nginx/sites-available/alfapro
sudo nano /etc/nginx/sites-available/alfapro      # Domain'i değiştir
sudo ln -s /etc/nginx/sites-available/alfapro /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# Let's Encrypt
sudo certbot --nginx -d alfapro.example.com
```

Nginx config'inde **HTTP Basic Auth** örneği açıklamalı olarak var — panelin arkasına bir şifre katmanı koymak şiddetle önerilir.

---

## Güvenlik Notları

- API anahtarları SQLite'a **Fernet ile şifrelenmiş** olarak yazılır.
- Master key `.env` dosyasındadır. **Kaybedilirse şifreli veriler geri dönmez.**
- Master key'i parola yöneticisinde yedekle.
- `.env` ve `data/*.db` dosyaları **asla** git'e girmemeli (`.gitignore` içinde).
- Sunucuda `chmod 600 .env`.

---

## Yol Haritası

Detaylar için [`PROJECT.md`](PROJECT.md).

- ✅ **Faz 1** — `APB-0001-FOUNDATION` (v0.1.0) — FastAPI + SQLite + API key yönetimi + Bitget bağlantı testi
- ✅ **Faz 2** — `APB-0002-MARKETDATA` (v0.2.0) — Market data, indikatörler, Fibonacci, SMC, dashboard grafikleri
- ✅ **Faz 3** — `APB-0003-SIGNALS` (v0.3.0) — Sinyal motoru, 2 strateji, paper + live trader, pozisyon takibi
- ✅ **Faz 4** — `APB-0004-AIRISK` (v0.4.0) — Risk yönetimi, Claude AI doğrulama, scheduler, Telegram
- ✅ **Faz 5** — `APB-0005-COMMODITY` (v0.5.0) — Emtia, loglar paneli, istatistik, live güvenlik, deploy paketi
- 🎉 **FINAL** — `APB-FINAL-v1.0.0` — **Canlı üretim sürümü** ✓

---

## Lisans

Özel proje.

---

## Yerel Geliştirme — Hızlı Başlat (Windows)

```powershell
cd C:\Users\admin\Desktop\alfapro-bot-gold
.\alfapro-bot-gold\venv311\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

veya:

```powershell
.\start-dev.bat
```
