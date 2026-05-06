# AlfaPro Bot — Proje Yol Haritası ve İlerleme Dosyası

> Bu dosya projenin anayasasıdır. Her oturum açıldığında önce buraya bakılır, bitirilen işler işaretlenir, kaldığımız yerden devam edilir.

**Son güncelleme:** 2026-04-24
**Aktif Seri:** `APB-FINAL-v1.1.0` — GOLD (Değerli Maden Odaklı Nihai Sürüm)
**Proje kök dizini:** `alfapro-bot-gold/`
**Durum:** Tüm fazlar tamamlandı + strateji kalite güncellemeleri yapıldı. Production-ready.

---

## 1. Proje Özeti

AlfaPro Bot Gold, Bitget futures borsasında **değerli maden (XAU/XAG) odaklı** otomatik al-sat yapan, yapay zeka destekli, self-host edilebilen (Docker'sız) bir işlem robotudur.

**Ana özellikler:**
- Bitget USDT-M Futures entegrasyonu (ccxt üzerinden, v2 API)
- Sadece değerli maden kontratları: XAUUSDT (altın), XAGUSDT (gümüş), PAXG, XAUT
- MetalTrendStrategy: EMA21/50/200 hiyerarşisi + MACD zorunlu onayı + Fibonacci proximity
- Multi-Timeframe (MTF) filtresi: alt TF sinyali için üst TF trend onayı zorunlu
- ATR-bazlı Trailing Stop Loss: kazanan pozisyonlarda SL otomatik çekilir
- İndikatörler: EMA (21/50/200), RSI, MACD, ATR, Bollinger, VWAP + SMC (BOS/CHoCH/OB) + Fibonacci
- AI doğrulama: Claude/OpenAI/Gemini API ile değerli maden uzmanı perspektifli sinyal filtresi
- Risk yönetimi: Kaldıraç (1–125x), USDT/işlem miktarı, ATR tabanlı SL/TP, günlük zarar kilidi
- Duplicate position guard: aynı strateji+sembol için birden fazla pozisyon açılmaz
- Backtester (lookahead-free): Fib/SMC her N barda sliding window ile yeniden hesaplanır
- Web panel: TradingView Lightweight Charts + durum kartları + ayar sekmeleri
- Log sistemi: loguru ile dosya + panelden görüntüleme
- Şifreli API anahtarı saklama: Fernet (cryptography)
- Deployment: systemd + uvicorn (Docker yok)

---

## 1.1 Seri Numarası Kayıt Defteri

Her fazın tamamlanmasıyla yeni bir seri numarası alınır. Seri numaraları `app/__init__.py` içinde `__serial__` olarak merkezi tutulur, `/api/health` ve `/api/version` ile yayınlanır, panel header'ında görünür.

| Serial | Version | Faz | Kod Adı | Durum | Tarih |
|---|---|---|---|---|---|
| `APB-0001-FOUNDATION` | v0.1.0 | Faz 1 | FOUNDATION | ✅ tamamlandı | 2026-04-21 |
| `APB-0002-MARKETDATA` | v0.2.0 | Faz 2 | MARKETDATA | ✅ tamamlandı | 2026-04-21 |
| `APB-0003-SIGNALS` | v0.3.0 | Faz 3 | SIGNALS | ✅ tamamlandı | 2026-04-22 |
| `APB-0004-AIRISK` | v0.4.0 | Faz 4 | AIRISK | ✅ tamamlandı | 2026-04-22 |
| `APB-0005-COMMODITY` | v0.5.0 | Faz 5 | COMMODITY | ✅ tamamlandı | 2026-04-22 |
| `APB-FINAL-v1.0.0` | v1.0.0 | — | PRODUCTION | ✅ tamamlandı | 2026-04-22 |
| `APB-FINAL-v1.1.0` | v1.1.0 | — | GOLD | 🥇 AKTİF SÜRÜM | 2026-04-24 |

> Seri numaraları `app/__init__.py` içindeki `__serial__` ile merkezi olarak yönetilir. Arşivlemek için `alfapro-bot-gold-GOLD.zip` adıyla paketlenebilir.

---

## 2. Teknik Stack

| Katman | Teknoloji | Not |
|---|---|---|
| Backend framework | FastAPI | async, otomatik OpenAPI |
| ASGI server | uvicorn | systemd servisi olarak |
| Veritabanı | SQLite + SQLAlchemy 2.0 | Postgres yerine — taşınabilir |
| Exchange SDK | ccxt | Bitget v2 "certified" |
| İndikatörler | pandas-ta-classic | TA-Lib derlemesi gerektirmez |
| Şifreleme | cryptography (Fernet) | API key saklama |
| Log | loguru | Günlük rotasyon |
| Frontend | HTML + Alpine.js + Tailwind (CDN) | Basit, tek dosya başlangıcı |
| Grafik | TradingView Lightweight Charts | Bedava, hafif |
| AI API | Anthropic / OpenAI / Gemini | Konfigüre edilebilir, model başına varsayılan: claude-sonnet-4-6 / gpt-4o-mini / gemini-1.5-flash |
| Websocket | ccxt pro (opsiyonel, sonra) | V1'de REST polling yeterli |

**Python:** 3.11+
**Dist sistemi:** Ubuntu 22.04/24.04 sunucu varsayımı

---

## 3. Fazlar ve İlerleme Durumu

### ✅ Faz 0 — Hazırlık (TAMAMLANDI)
- [x] Gereksinim netleştirme
- [x] Teknoloji araştırması (ccxt Bitget v2, pandas-ta-classic, XAU/XAG perpetual'lar)
- [x] Proje adı: **AlfaPro Bot**
- [x] Proje iskeleti dizin yapısı

### ✅ Faz 1 — İskelet (TAMAMLANDI)
**Hedef:** Çalışan FastAPI + SQLite + şifreli API key saklama + Bitget bağlantı testi + panel shell

- [x] `PROJECT.md` — bu dosya
- [x] `requirements.txt`
- [x] `.env.example` + `.gitignore`
- [x] `app/config.py` — ayar yükleyici (pydantic-settings)
- [x] `app/core/database.py` — SQLite + SQLAlchemy engine + session (WAL modu)
- [x] `app/core/security.py` — Fernet şifreleme servisi
- [x] `app/core/logger.py` — loguru konfigürasyonu (günlük rotasyon, ayrı trade log)
- [x] `app/models/api_credentials.py` — API anahtar modeli (şifreli + maskeleme)
- [x] `app/schemas/credentials.py` — pydantic şemaları
- [x] `app/services/bitget_client.py` — ccxt Bitget sarmalayıcı + bağlantı testi
- [x] `app/routers/settings.py` — API key ekle/güncelle/sil/test endpoint'leri
- [x] `app/routers/health.py` — durum endpoint'i
- [x] `app/main.py` — FastAPI uygulaması
- [x] `scripts/generate_master_key.py` — Fernet master key üretici
- [x] `frontend/index.html` — sekmeli panel (Alpine.js + Tailwind, Ayarlar sekmesi tam fonksiyonel)
- [x] `README.md` — kurulum talimatları
- [x] End-to-end test: Settings → credentials round-trip (encrypt/decrypt/mask) ✓
- [x] End-to-end test: FastAPI endpoints (GET, POST, DELETE) ✓
- [x] End-to-end test: Frontend HTML serve ✓
- [x] End-to-end test: Bitget client public API kod yolu ✓

### ✅ Faz 2 — Market Data & İndikatörler (TAMAMLANDI — APB-0002-MARKETDATA)
- [x] `app/__init__.py` — serial + version sistemi (`__serial__`, `__codename__`, `__phase__`, `version_info()`)
- [x] `app/routers/health.py` — serial bilgisini `/api/health` ve `/api/version` üzerinden yayınla
- [x] `app/models/candle.py` — OHLCV cache SQLAlchemy modeli (symbol, tf, ts unique)
- [x] `app/schemas/market.py` — CandleOut, IndicatorValues/Series, FibonacciLevels, SmcAnalysis, MarketAnalysis
- [x] `app/services/market_data.py` — OHLCV fetch (ccxt), SQLite cache upsert, trim, ticker, sembol listesi
- [x] `app/services/indicators.py` — pandas-ta-classic: EMA (çoklu periyot), RSI, MACD, ATR, Bollinger, VWAP
- [x] `app/services/fibonacci.py` — swing tespiti + retracement (0.236–0.786) + extension (1.272–2.618)
- [x] `app/services/smc.py` — fractal swing detection, BOS, CHoCH, Order Blocks, trend state
- [x] `app/routers/market.py` — `/symbols`, `/ticker`, `/candles`, `/analysis` (hepsi-bir-arada)
- [x] `frontend/index.html` — TradingView Lightweight Charts v4, sembol arayıcı, timeframe butonları, durum kartları, EMA/BB overlay, Fib price lines, SMC markers, RSI + MACD alt grafikleri, oto-yenile
- [x] Birim test: indikatörler (EMA/RSI/MACD/ATR/BB), Fibonacci, SMC (BOS 10 + CHoCH 5 + OB 5) ✓
- [x] Entegrasyon test: 9 endpoint kayıtlı, frontend HTML servis ediliyor, serial bilgisi header'da görünür ✓

### ✅ Faz 3 — Sinyal Motoru & Emir Akışı (TAMAMLANDI — APB-0003-SIGNALS)
**Hedef:** Strateji motorunu, paper/live trading'i, pozisyon takibini kur.

Veri modelleri:
- [x] `app/models/signal.py` — üretilen her sinyal için DB satırı (audit)
- [x] `app/models/position.py` — paper + live pozisyon, unrealized/realized PnL
- [x] `app/models/trade.py` — her açma/kapama için log satırı
- [x] `app/models/strategy_config.py` — strateji parametre/sembol/tf persistence (JSON alanlar)
- [x] `app/models/app_state.py` — global paper/live mode

Şemalar:
- [x] `app/schemas/trading.py` — SignalCore, PositionOut, TradingMode, StrategyConfig, 12 pydantic model

Stratejiler:
- [x] `app/services/strategies/base.py` — `BaseStrategy` abstract + `StrategyContext` dataclass, ATR-based SL/TP helper, confidence clamp
- [x] `app/services/strategies/scalp_ema_rsi.py` — EMA 9/21 cross + RSI filter, confidence 0-100 (hacim + RSI sweet-spot + MACD + SMC uyumu)
- [x] `app/services/strategies/swing_smc_fib.py` — SMC trend + 0.5-0.618 Fib zone + MACD histogram flip, ATR-buffered SL, 1.618 extension TP
- [x] `app/services/strategies/registry.py` — `list_strategies()`, `get_strategy()`, `strategy_info()`

İşlem motorları:
- [x] `app/services/paper_trader.py` — simülasyon: open_from_signal, open_manual, SL/TP tick, close_position, persist_signal
- [x] `app/services/live_trader.py` — ccxt ile Bitget emir, leverage + isolated margin, reduce-only SL/TP, piyasa emirleri ile aç/kapat

Router'lar:
- [x] `app/routers/strategies.py` — list / config get-post / evaluate (on-demand)
- [x] `app/routers/trading.py` — mode get-post, positions list/open/close/tick, signals, trade log

Frontend:
- [x] Header'a paper/live mode butonu + onaylı switch dialog'u
- [x] Ana Sayfa'ya "Pozisyonlar" paneli — filtre (açık/tümü), tick butonu, manuel kapama, durum renkleri
- [x] Ana Sayfa'ya "Son Sinyaller" paneli — "Şimdi değerlendir" (tüm stratejiler × seçili sembol), reasoning gösterimi, tek tıkla pozisyon açma
- [x] Stratejiler sekmesi — her strateji için enable toggle, size/leverage, semboller, timeframes, parametreler formu, per-strategy evaluate butonu
- [x] Eval sonucu canlı gösterimi (sinyal varsa entry/SL/TP/confidence)

Testler:
- [x] Birim: Scalp + Swing stratejilerini sahte OHLCV ile çalıştır ✓
- [x] Birim: PaperTrader aç → SL tetikle → kapat, PnL matematiksel doğrula (5x long → -8.33%) ✓
- [x] Birim: PaperTrader short → TP tetikle → +%10 (3x lev) ✓
- [x] Birim: StrategyConfig JSON params/symbols/timeframes roundtrip ✓
- [x] Entegrasyon: 9 yeni endpoint kayıtlı (toplam 18 path, 22 method) ✓
- [x] Entegrasyon: Live mode onaysız reddi, credential'sız reddi ✓
- [x] Entegrasyon: Config otomatik oluşturma + POST ile güncelleme ✓
- [x] Frontend: Faz 3'e özgü 14 kritik element HTML'de ✓

### ✅ Faz 4 — AI Doğrulama & Risk Yönetimi (TAMAMLANDI — APB-0004-AIRISK)
**Hedef:** AI destekli sinyal filtresi, risk kapısı, otomatik scheduler, Telegram bildirimleri.

Veri modelleri:
- [x] `app/models/app_state.py` — risk limitleri (max_open_positions, daily_loss_limit), circuit breaker state, AI ayarları, scheduler ayarları, telegram ayarları
- [x] `app/models/signal.py` — `ai_confidence` alanı eklendi
- [x] `app/core/database.py` — `_migrate_app_state()` + `_migrate_signals()` migration helper'ları (SQLite ALTER TABLE)

Servisler:
- [x] `app/services/risk_manager.py` — günlük PnL hesabı, circuit breaker trip/reset, max pos kontrolü, Kelly Criterion (half-kelly), açma kapısı (`evaluate_open`)
- [x] `app/services/ai_validator.py` — Anthropic Claude API entegrasyonu, JSON prompt, response parser, key/package yoksa graceful fallback
- [x] `app/services/telegram_notifier.py` — 4 bildirim türü (signal, position opened, position closed, circuit breaker), disabled ise no-op
- [x] `app/services/scheduler.py` — asyncio arka plan task: AppState tick kontrolü, paper pozisyon SL/TP tarama, aktif strateji eval → sinyal → AI → risk → pozisyon zinciri

Şemalar & Router:
- [x] `app/schemas/risk.py` — AppStateOut/Update, RiskStatusOut, TelegramTestResult, AiTestRequest/Result
- [x] `app/routers/risk.py` — 6 endpoint: GET/POST `/risk/state`, GET `/risk/status`, POST `/risk/circuit-breaker/reset`, POST `/risk/telegram/test`, POST `/risk/ai/test`
- [x] `app/main.py` — lifespan içinde scheduler start/stop

Frontend:
- [x] Yeni "Risk & AI" sekmesi
- [x] Canlı durum kartları (mod, günlük PnL, açık pozisyon sayısı, breaker durumu) + CB reset butonu
- [x] Risk limitleri formu (max pos, günlük zarar limiti)
- [x] AI toggle + min confidence slider + dummy sinyal test butonu
- [x] Scheduler toggle + interval slider (15sn-10dk)
- [x] Telegram toggle + token (maskeli) + chat ID + test butonu

Testler:
- [x] RiskManager: boş PnL, kümülatif PnL, breaker trip/reset, max pos limiti, Kelly (WR=60% R=2 → 200 USDT half-kelly), negatif edge → 0
- [x] AiValidator: key yok → onay fallback, disabled → otomatik onay, JSON parser (iyi + bozuk yanıt)
- [x] TelegramNotifier: token yok → no-op
- [x] Entegrasyon: 5 yeni endpoint kayıtlı, state GET/POST patch, token maskeleme, AI test disabled ret
- [x] Frontend: 19 kritik Faz 4 elementi doğrulandı (tab, state, 7 fn, durum kartları, tüm toggle'lar/sliderlar/formlar)
- [x] Toplam: 23 path, 28 HTTP method, 80 KB frontend

### ✅ Faz 5 — Emtia + Panel Bitirme + Deploy (TAMAMLANDI — APB-0005-COMMODITY)
**Hedef:** Emtia sembol katalogu, log paneli, işlem istatistikleri, live auto-trading güvenlik katmanı, deployment dosyaları.

Backend:
- [x] `app/services/commodity_catalog.py` — sembol kategorize (crypto/metal/energy/index/stock), `group_markets()` → kategoriye göre sözlük
- [x] `app/services/log_reader.py` — `read_tail()` dosyadan son N satır, level + contains filtre, chunked tail okuma (256KB), loguru format regex
- [x] `app/services/trade_stats.py` — WR, PF, expectancy, avg win/loss, largest win/loss, net PnL, by-strategy breakdown
- [x] `app/routers/market.py` — `/symbols/grouped` endpoint (emtia seçimi için)
- [x] `app/routers/logs.py` — `/logs/files`, `/logs/tail`, `/stats/summary` (3 endpoint)
- [x] `app/models/app_state.py` — `live_auto_trading_enabled` güvenlik flag'i
- [x] `app/core/database.py` — migration'a yeni alan eklendi
- [x] `app/services/scheduler.py` — Live mod: flag kapalı iken sinyal loglanır + Telegram'a gönderilir ama pozisyon açılmaz. Flag açık + live mod + scheduler açık olunca gerçek emir akışı devreye girer
- [x] `app/schemas/risk.py` + `app/routers/risk.py` — `live_auto_trading_enabled` patch + gösterim

Frontend:
- [x] Loglar sekmesi tam uygulama — dosya seçici (alfapro/trades), level filtresi (DEBUG/INFO/WARN/ERROR), içerik araması (400ms debounce), limit seçici (50/200/500/1000), renkli seviye etiketleri, oto-yenile (10sn), dosya meta bilgisi
- [x] İşlem İstatistikleri paneli (Loglar sekmesi altında) — Paper/Live/Tümü filtresi, 8 metrik kartı (toplam, WR, net PnL, PF, avg win/loss, largest), strateji bazında breakdown satırları
- [x] Risk & AI sekmesinde Live Auto-Trading güvenlik toggle'ı — confirm dialog, paper mod uyarı banner'ı, live+scheduler+flag üçlüsü aktifken kırmızı tehlike banner'ı

Deployment:
- [x] `deploy/alfapro-bot.service` — systemd unit (güvenlik sertleştirmesi, kaynak limiti, journal log, tek worker)
- [x] `deploy/nginx.conf.example` — TLS + güvenlik başlıkları + opsiyonel htpasswd + Let's Encrypt ACME path
- [x] `install.sh` — tek komut kurulum: python venv, bağımlılıklar, master key üretimi, systemd servis kayıt ve başlatma

Testler:
- [x] commodity_catalog: 8 kategori eşleşmesi doğrulandı, fake markets ile grouping
- [x] trade_stats: 5 pozisyonlu senaryo — WR=60%, PF=2.048, net=$22, by_strategy breakdown doğru
- [x] log_reader: regex düzeltildi, 4 satırlık log dosyasından level + contains filtre çalışıyor
- [x] live_auto_trading_enabled: DB migration + GET/POST /risk/state round-trip
- [x] Frontend: 16 kritik Faz 5 elementi doğrulandı
- [x] Toplam: 27 path, 32 HTTP method, 94 KB frontend

---

## 4. Kritik Tasarım Kararları

### 4.1 Neden Docker değil?
Kullanıcı tercihi. systemd + venv + uvicorn tek sunucuda yeterli. Yedekleme: SQLite dosyası + `.env` + log dizini kopyalanarak yapılır.

### 4.2 Neden SQLite (Postgres değil)?
Tek kullanıcılı self-host bot için write kilidi problem değil. WAL modu ile eşzamanlı okumalar hızlı. Yedekleme tek dosya. Geçiş gerekirse SQLAlchemy sayesinde engine URL değiştirmek yeterli.

### 4.3 Neden pandas-ta-classic (pandas-ta değil)?
Orijinal pandas-ta paketi "discontinuation risk" uyarısı ile bakımda. pandas-ta-classic topluluk fork'u aktif, API uyumlu, TA-Lib derlemesi ZORUNLU değil — Docker'sız Linux kurulumunda büyük kolaylık.

### 4.4 Neden Alpine.js + HTML (React değil)?
V1'de hız öncelik. Alpine.js CDN + Tailwind CDN = build adımı yok, tek HTML dosyası. React'e geçiş gerekirse Faz 5'te yapılabilir.

### 4.5 API Key Güvenliği
- Fernet ile şifreli SQLite'ta saklanır
- Master key `.env` dosyasında `ALFAPRO_MASTER_KEY`
- `.env` dosya izni 600, git'e kesinlikle girmez
- Bitget'te sadece "Read" + "Trade" yetkisi ile API key oluşturulmalı, "Withdraw" ASLA
- Bitget API'de IP whitelist zorunlu önerisi

### 4.6 Strateji Seçimi
Tüm strateji sınıfları kaldırılarak tek uzman strateji (`MetalTrendStrategy`) bırakıldı:
- EMA21/50/200 hiyerarşisi ile trend teyidi + MACD zorunlu onayı + Fibonacci proximity scoring
- Önerilen timeframe'ler: 15m, 1h, 4h — MTF filtresi sayesinde her TF kendi üst TF'i ile çapraz teyit alır
- Mevcut Bot'a strateji eklemek için `app/services/strategies/` dizininde `BaseStrategy` alt sınıfı yeterli

---

## 5. Sembol Eşleştirme (Bitget)

| Kullanıcı adı | ccxt sembol | Bitget raw symbol |
|---|---|---|
| BTC | `BTC/USDT:USDT` | `BTCUSDT` |
| ETH | `ETH/USDT:USDT` | `ETHUSDT` |
| Altın | `XAU/USDT:USDT` | `XAUUSDT` |
| Gümüş | `XAG/USDT:USDT` | `XAGUSDT` |
| Pax Gold | `PAXG/USDT:USDT` | `PAXGUSDT` |
| Petrol | `CRUDE/USDT:USDT` | `CRUDEUSDT` (Bitget'te mevcutsa) |

> Bot yalnızca değerli maden kontratlarına (XAUUSDT, XAGUSDT) odaklanacak şekilde tasarlanmıştır. Diğer semboller `commodity_catalog` üzerinden otomatik keşfedilir.

---

## 6. Dizin Yapısı

```
alfapro-bot-gold/
├── PROJECT.md              # Bu dosya
├── README.md               # Kurulum
├── .env.example            # Örnek env
├── .gitignore
├── requirements.txt
├── app/
│   ├── main.py             # FastAPI entry
│   ├── config.py           # Settings loader
│   ├── core/
│   │   ├── database.py     # SQLAlchemy setup
│   │   ├── security.py     # Fernet encryption
│   │   └── logger.py       # Loguru
│   ├── models/             # SQLAlchemy modelleri
│   ├── schemas/            # Pydantic şemaları
│   ├── routers/            # API endpoint'leri
│   └── services/           # İş mantığı (bitget_client, indicators, signals...)
├── frontend/
│   └── index.html          # Panel (sekmeli)
├── data/                   # SQLite DB (git-ignore)
├── logs/                   # Log dosyaları (git-ignore)
└── scripts/
    └── generate_master_key.py
```

---

## 7. Final Ürün Özeti (APB-FINAL-v1.1.0 — GOLD)

### Ürün Kapasitesi

**Bitget USDT-M Futures**
- 300+ perpetual sembol (kripto) + emtia (XAU altın, XAG gümüş, PAXG, XAUT)
- Stok ve endeks perpetual'ları (varsa erişilebilir) kategorize olarak listelenir
- Kaldıraç 1-125x, isolated margin, reduce-only SL/TP emirleri

**Çoklu Timeframe**
- 1m, 5m, 15m, 1h, 4h, 1d (6 TF)

**Teknik Analiz**
- 6 indikatör: EMA (çoklu periyot), RSI, MACD, ATR, Bollinger, VWAP (pandas-ta-classic)
- Fibonacci retracement + extension (otomatik swing tespiti)
- SMC: BOS, CHoCH, Order Blocks, trend state (fractal swing)
- Tümü tek endpoint'te (`/market/analysis`) birleştirilmiş

**Sinyal Motoru**
- 1 strateji: MetalTrendStrategy — sadece değerli maden odaklı
  - EMA21 (pullback tetikleyici) + EMA50 (kısa trend) + EMA200 (ana trend filtresi)
  - MACD histogram zorunlu yön onayı
  - Fibonacci 0.382/0.5/0.618 proximity confidence bonusu
  - SMC piyasa yapısı uyum bonusu/penaltisi
  - RSI momentum bölgesi kontrolü (long: 42-68, short: 32-58)
  - ATR-bazlı Trailing Stop Loss (ATR × 1.5, otomatik SL takibi)
  - Multi-Timeframe filtresi (15m → 1h, 1h → 4h, 4h → 1d trend doğrulama)
- 0-100 confidence scoring, minimum 60 eşiği
- Genişletilebilir `BaseStrategy` + registry pattern

**AI Doğrulama (Claude / OpenAI / Gemini)**
- Anthropic Claude, OpenAI GPT, Google Gemini — yapılandırılabilir
- Değerli maden uzmanı perspektifli prompt (altın/emtia özelinde kriterler)
- Sinyal + indikatör özeti + son mumlar → JSON prompt → 0-100 skor + not
- Confidence eşiği ile veto mekanizması
- API key yoksa graceful fallback (her zaman onay)

**Risk Yönetimi**
- Circuit breaker (günlük zarar limiti)
- Max açık pozisyon limiti
- Kelly Criterion (half-kelly) pozisyon boyutu yardımcısı
- Manual reset endpoint + panel butonu

**Otomasyon**
- Asyncio arka plan scheduler
- Aktif stratejileri sembol × timeframe grid'inde değerlendirir
- Sinyal → AI gate → risk gate → pozisyon açma zinciri
- Duplicate guard: aynı strateji+sembol için açık pozisyon varsa değerlendirme atlanır
- Paper mode: her zaman aktif. Live mode: `live_auto_trading_enabled=True` zorunlu.

**Bildirim**
- Telegram: sinyal, pozisyon açma/kapama, circuit breaker
- Markdown formatlı mesajlar
- Token maskeleme

**Web Panel (Single-Page)**
- 5 sekme: Ana Sayfa, Ayarlar, Stratejiler, Risk & AI, Loglar
- TradingView Lightweight Charts (mumlar + EMA + BB + Fib çizgileri + SMC markerleri)
- RSI ve MACD alt grafikleri
- Canlı pozisyon + sinyal panelleri
- Paper/Live mode toggle (onay dialogu ile)
- Log viewer + level/contains filtreleri + oto-yenile
- İşlem istatistikleri (WR, PF, by-strategy)

**Güvenlik**
- Fernet ile şifrelenmiş API anahtarları (SQLite içinde)
- Master key `.env` içinde (chmod 600)
- SQLite WAL mode
- nginx TLS + HTTP Basic Auth örneği
- systemd güvenlik sertleştirmesi (NoNewPrivileges, ProtectSystem, ReadWritePaths)

### Deployment

- `install.sh` tek komut kurulum (Ubuntu 22.04/24.04)
- systemd servis (tek worker — scheduler singleton için)
- Nginx reverse proxy + Let's Encrypt örneği
- Docker **yok** (tasarım kararı)

### API Metrikleri

- 27 path, 32 HTTP method
- 19 Python modülü (`app/`)
- 7 router
- 12 servis
- 7 DB modeli (positions tablosuna `trailing_stop_atr` sütunu eklendi)
- Tek HTML dosyası frontend (~94 KB)

### Test Kapsamı

Her faz sonunda end-to-end doğrulandı:
- Fernet encrypt/decrypt round-trip
- İndikatör hesaplamaları (EMA/RSI/MACD/ATR/BB/VWAP)
- Fibonacci swing tespiti
- SMC BOS/CHoCH/OB algoritması
- Stratejilerin sinyal üretimi
- PaperTrader SL/TP tetikleme + PnL doğruluğu
- Risk manager: breaker trip/reset, max pos, Kelly
- AI validator: JSON parser, graceful fallback
- Trade stats: WR, PF, expectancy, by-strategy
- Log reader: tail + filter
- FastAPI endpoint registration (27 path)
- Frontend element doğrulama (60+ kritik ref)

---

## 8. Çalıştırma Notları (Faz 1 sonrası)

```bash
# İlk kurulum
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python scripts/generate_master_key.py   # .env'e koy

# Geliştirme
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Panel: http://localhost:8000
```

---

## 9. Değişiklik Günlüğü

| Tarih | Değişiklik |
|---|---|
| 2026-04-21 | Proje başladı. Faz 0 tamamlandı, Faz 1 başladı. Dizin yapısı ve PROJECT.md oluşturuldu. |
| 2026-04-21 | Faz 1 tamamlandı (`APB-0001-FOUNDATION`, v0.1.0). Config, DB (SQLite+WAL), Fernet şifreleme, loguru, ApiCredentials modeli, Bitget ccxt sarmalayıcı, settings & health router'ları, FastAPI uygulaması, Alpine.js + Tailwind panel iskeleti. End-to-end testler geçti. |
| 2026-04-21 | Seri numarası sistemi tanıtıldı. `app/__init__.py` içinde `__serial__`, `__codename__`, `__phase__` merkezi olarak tutuluyor; `/api/health` ve `/api/version` ile yayınlanıyor; panel header'da görünür. |
| 2026-04-21 | Faz 2 tamamlandı (`APB-0002-MARKETDATA`, v0.2.0). Candle SQLAlchemy modeli + cache, pandas-ta-classic indikatör motoru (EMA/RSI/MACD/ATR/BB/VWAP), Fibonacci swing + retracement/extension, SMC (fractal swing → BOS/CHoCH/Order Block + trend state), 4 market endpoint'i (symbols/ticker/candles/analysis), TradingView Lightweight Charts v4 ile tam panel. |
| 2026-04-22 | Faz 3 tamamlandı (`APB-0003-SIGNALS`, v0.3.0). 5 yeni DB modeli (Signal, Position, Trade, StrategyConfig, AppState), `BaseStrategy` + 2 somut strateji (scalp EMA/RSI + swing SMC/Fib), 0-100 confidence scoring, PaperTrader ve LiveTrader (ccxt üzerinden Bitget market + reduce-only SL/TP), 9 yeni endpoint (strategies + trading). Frontend: header'da paper/live mode toggle + onay dialogu, Ana Sayfa'ya Pozisyonlar + Sinyaller panelleri, Stratejiler sekmesi tam UI (enable/size/leverage/symbols/timeframes/params). Birim + entegrasyon testleri geçti (22 endpoint, 14 frontend elementi doğrulandı). |
| 2026-04-22 | Faz 4 tamamlandı (`APB-0004-AIRISK`, v0.4.0). AppState genişletildi (risk limitleri, AI ayarları, scheduler ayarları, Telegram). SQLite migration helper'ları eklendi. 4 yeni servis: RiskManager (günlük PnL + circuit breaker + Kelly + açma kapısı), AiValidator (Claude API + JSON prompt/parser + graceful fallback), TelegramNotifier (4 bildirim türü), Scheduler (asyncio arka plan + strateji eval zinciri AI→risk→paper open). 6 yeni endpoint (/risk/state, /status, /circuit-breaker/reset, /telegram/test, /ai/test). Frontend'e Risk & AI sekmesi: canlı durum kartları + CB reset butonu, risk limitleri formu, AI toggle + min confidence slider + dummy test, Scheduler toggle + interval slider (15sn-10dk), Telegram formu (token maskeli) + test butonu. Toplam 23 path / 28 method / 80 KB frontend. Backend + frontend tüm testler geçti. |
| 2026-04-22 | Faz 5 tamamlandı (`APB-0005-COMMODITY`, v0.5.0). commodity_catalog (crypto/metal/energy/index/stock kategorizasyonu), log_reader (tail+level+contains filtre), trade_stats (WR/PF/expectancy + by-strategy), AppState.live_auto_trading_enabled güvenlik flag'i, scheduler live-mode akışı. 4 yeni endpoint (/symbols/grouped, /logs/files, /logs/tail, /stats/summary). Frontend: Loglar sekmesi tam uygulama (filtre + renkli seviye + oto-yenile) + İşlem İstatistikleri paneli (8 metrik + by-strategy breakdown), Risk & AI sekmesine Live Auto-Trading onaylı toggle. Deploy paketi: systemd unit (güvenlik sertleştirme), nginx TLS şablonu, tek komut install.sh. Toplam 27 path / 32 method / 94 KB frontend. Faz bitti — FINAL dönüşüm için hazır. |
| 2026-04-22 | 🎉 **APB-FINAL-v1.0.0** — Canlı ürün sürümü. Seri `APB-FINAL-v1.0.0`, versiyon 1.0.0, kod adı PRODUCTION. `app/__init__.py` içinde `__serial__`, `__version__`, `__codename__` güncellendi; `/api/health` `is_final: true` döndürüyor. Tüm 5 faz tamamlandı. 27 path, 32 method, 94 KB frontend, 58 dosya. Ürün production-ready: `install.sh` ile tek komutluk kurulum, systemd + nginx + TLS şablonları, docker-bağımsız. |
| 2026-04-23 | Altın işlem kalitesi iyileştirmeleri: MetalTrendStrategy tamamen yeniden yazıldı (EMA21/50/200 hiyerarşi + MACD zorunlu + Fibonacci scoring). Eski `scalp_ema_rsi` ve `swing_smc_fib` stratejileri kaldırıldı. Konfigürasyon DB temizlendi: sembol=XAU/USDT:USDT, size_usdt=5.0, max_open_positions=1. EMA200 zaten hesaplanıyordu ama strateji hiç kullanmıyordu — düzeltildi. |
| 2026-04-24 | 🥇 **APB-FINAL-v1.1.0 (GOLD)** — 5 strateji kalitesi geliştirmesi: (1) Backtester lookahead bias düzeltildi — Fib/SMC her 20 barda sliding window ile yeniden hesaplanıyor; (2) ATR-bazlı Trailing Stop Loss eklendi — kazanan pozisyonlarda SL otomatik çekilir, positions tablosuna `trailing_stop_atr` migration ile eklendi; (3) Multi-Timeframe filtresi eklendi — 15m→1h, 1h→4h, 4h→1d üst TF EMA50/200 trend onayı; (4) AI Validator prompt güncellendi — "kripto futures" yerine "değerli maden/emtia uzmanı" perspektifi; (5) Duplicate position guard eklendi — scheduler aynı strateji+sembol için açık pozisyon varsa tüm timeframe değerlendirmeleri atlar. Versiyon 1.1.0, seri APB-FINAL-v1.1.0. |
