# AlfaPro Bot

Bitget futures için otomatik al-sat robotu. Docker'sız, self-host, yapay zeka destekli.

# AlfaPro Bot

Bitget futures için otomatik al-sat robotu. Docker'sız, self-host, yapay zeka destekli.

**🎉 Aktif Seri:** `APB-FINAL-v1.0.0` — Canlı üretim sürümü

> Tüm yol haritası, seri numarası kayıt defteri ve ürün özeti için [`PROJECT.md`](PROJECT.md) dosyasına bak.

---

## Hızlı Kurulum

### 1. Gereksinimler
- Python 3.11 veya üstü
- (Linux sunucu için) `systemd`, `nginx` (Faz 5'te)

### 2. Depoyu indir, sanal ortam kur

```bash
git clone <repo>   # veya zip'i aç
cd alfapro-bot

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
alfapro-bot/
├── PROJECT.md              # Yol haritası, ilerleme takibi (proje anayasası)
├── README.md               # Bu dosya
├── requirements.txt
├── .env.example
├── app/
│   ├── main.py             # FastAPI entry
│   ├── config.py           # Ayar yükleyici
│   ├── core/               # database, security, logger
│   ├── models/             # SQLAlchemy modelleri
│   ├── schemas/            # Pydantic şemaları
│   ├── routers/            # API endpoint'leri
│   └── services/           # bitget_client, (sonra) indicators, signals
├── frontend/
│   └── index.html          # Alpine.js + Tailwind panel
├── data/                   # SQLite DB (git-ignore)
├── logs/                   # Log dosyaları (git-ignore)
└── scripts/
    └── generate_master_key.py
```

---

## Geliştirme

### Testleri çalıştır (ileride eklenecek)
```bash
pytest
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


cd C:\Users\admin\Desktop\alfapro-bot-gold\alfapro-bot-gold
venv311\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
