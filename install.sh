#!/usr/bin/env bash
# AlfaPro Bot — Tek komut kurulum scripti
#
# Ubuntu 22.04 / 24.04 üzerinde test edilmiştir.
# Kullanım:
#   chmod +x install.sh
#   sudo ./install.sh

set -euo pipefail

# ---- Ayarlar ----
INSTALL_DIR="${INSTALL_DIR:-/opt/alfapro-bot}"
SERVICE_USER="${SERVICE_USER:-alfapro}"
PYTHON_VERSION="${PYTHON_VERSION:-python3.11}"

# ---- Renkli çıktı ----
BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${BLUE}[*]${NC} $*"; }
ok()    { echo -e "${GREEN}[✓]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
error() { echo -e "${RED}[✗]${NC} $*" >&2; }

# ---- Root kontrol ----
if [[ $EUID -ne 0 ]]; then
    error "Bu scripti sudo ile çalıştır: sudo ./install.sh"
    exit 1
fi

# ---- OS kontrol ----
if ! command -v apt-get &> /dev/null; then
    error "Bu script Debian/Ubuntu bazlı sistemler için. Diğer dağıtımlarda manuel kurulum gerekli."
    exit 1
fi

# ---- 1. Sistem paketleri ----
info "Sistem paketleri kuruluyor..."
apt-get update -qq
apt-get install -y -qq \
    "$PYTHON_VERSION" "$PYTHON_VERSION-venv" "$PYTHON_VERSION-dev" \
    python3-pip \
    build-essential \
    git \
    curl

ok "Sistem paketleri hazır."

# ---- 2. Kullanıcı ----
if id "$SERVICE_USER" &>/dev/null; then
    ok "Kullanıcı '$SERVICE_USER' zaten var."
else
    info "'$SERVICE_USER' kullanıcısı oluşturuluyor..."
    useradd --system --home-dir "$INSTALL_DIR" --shell /bin/bash "$SERVICE_USER"
    ok "Kullanıcı oluşturuldu."
fi

# ---- 3. Dizinler ----
info "Dizinler hazırlanıyor: $INSTALL_DIR"
mkdir -p "$INSTALL_DIR"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Eğer script proje dizini içinden çalıştırıldıysa dosyaları kopyala
if [[ "$SCRIPT_DIR" != "$INSTALL_DIR" ]]; then
    info "Proje dosyaları $INSTALL_DIR'e kopyalanıyor..."
    # Kaynak ve hedef farklıysa, senkronize et
    rsync -a --delete \
        --exclude='venv' --exclude='data' --exclude='logs' \
        --exclude='__pycache__' --exclude='.git' \
        "$SCRIPT_DIR/" "$INSTALL_DIR/"
fi

mkdir -p "$INSTALL_DIR/data" "$INSTALL_DIR/logs"

# ---- 4. venv ----
info "Python sanal ortamı kuruluyor..."
cd "$INSTALL_DIR"
if [[ ! -d venv ]]; then
    "$PYTHON_VERSION" -m venv venv
fi
./venv/bin/pip install --quiet --upgrade pip setuptools wheel
./venv/bin/pip install --quiet -r requirements.txt
ok "Python bağımlılıkları kuruldu."

# ---- 5. .env ----
if [[ ! -f .env ]]; then
    info ".env dosyası oluşturuluyor..."
    cp .env.example .env
    MASTER_KEY=$(./venv/bin/python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
    sed -i "s|^ALFAPRO_MASTER_KEY=.*|ALFAPRO_MASTER_KEY=$MASTER_KEY|" .env
    chmod 600 .env
    ok "Yeni master key üretildi ve .env dosyasına yazıldı."
    warn "ÖNEMLİ: .env dosyasındaki master key'i yedekle (parola yöneticisi)."
    warn "Kaybedilirse şifreli API anahtarların geri alınamaz."
else
    warn ".env zaten var, değiştirilmedi."
fi

# ---- 6. Sahiplik ----
info "İzinler ayarlanıyor..."
chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"
chmod 600 "$INSTALL_DIR/.env"
ok "İzinler OK."

# ---- 7. systemd ----
if [[ -f "$INSTALL_DIR/deploy/alfapro-bot.service" ]]; then
    info "systemd servisi kuruluyor..."

    # Servis dosyasında yolları güncelle
    sed -e "s|/opt/alfapro-bot|$INSTALL_DIR|g" \
        -e "s|^User=alfapro|User=$SERVICE_USER|" \
        -e "s|^Group=alfapro|Group=$SERVICE_USER|" \
        "$INSTALL_DIR/deploy/alfapro-bot.service" \
        > /etc/systemd/system/alfapro-bot.service

    systemctl daemon-reload
    systemctl enable alfapro-bot >/dev/null 2>&1

    # Zaten çalışıyorsa yeniden başlat
    if systemctl is-active --quiet alfapro-bot; then
        systemctl restart alfapro-bot
        ok "Servis yeniden başlatıldı."
    else
        systemctl start alfapro-bot
        ok "Servis başlatıldı."
    fi
fi

# ---- 8. Durum ----
echo
echo "═══════════════════════════════════════════════"
echo " ✓ AlfaPro Bot kurulumu tamamlandı"
echo "═══════════════════════════════════════════════"
echo
echo " Kurulum dizini : $INSTALL_DIR"
echo " Servis kullanıcı: $SERVICE_USER"
echo " Panel URL       : http://localhost:8000"
echo
echo " Kontrol komutları:"
echo "   sudo systemctl status alfapro-bot"
echo "   sudo journalctl -u alfapro-bot -f"
echo
echo " Sonraki adımlar:"
echo "   1. Panel'e Bitget API anahtarını ekle"
echo "   2. (Opsiyonel) Risk & AI sekmesinden scheduler'ı yapılandır"
echo "   3. (Opsiyonel) Nginx reverse proxy: deploy/nginx.conf.example"
echo "   4. (Opsiyonel) Anthropic API key: .env dosyasına ekle"
echo
