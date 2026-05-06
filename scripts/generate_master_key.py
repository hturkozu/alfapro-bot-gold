"""
Fernet master key üretici.

Kullanım:
    python scripts/generate_master_key.py

Çıktı bir Fernet key'dir. Bu key'i `.env` dosyasındaki
`ALFAPRO_MASTER_KEY=` değişkenine yapıştır.

UYARI: Bu key'i kaybedersen şifreli olarak saklanmış tüm API
anahtarların geri alınamaz şekilde kaybolur. Güvenli bir yerde
yedekle (ör. bir parola yöneticisi).
"""
from cryptography.fernet import Fernet


def main() -> None:
    key = Fernet.generate_key().decode()
    print()
    print("=" * 60)
    print("AlfaPro Bot — Master Key")
    print("=" * 60)
    print()
    print(f"ALFAPRO_MASTER_KEY={key}")
    print()
    print("Yukarıdaki satırı .env dosyana kopyala.")
    print("Bu key'i KAYBETME. Yedekle.")
    print("=" * 60)


if __name__ == "__main__":
    main()
