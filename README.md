# 💳 Billing Mikrotik - Flask + Docker Edition

Sistem billing sederhana untuk pelanggan internet berbasis Mikrotik, dibangun menggunakan Flask dan dikemas dengan Docker. Sistem ini menyediakan manajemen pelanggan, tagihan bulanan otomatis, integrasi Mikrotik RouterOS API, dan tampilan berbasis web.

---

## 🚀 Fitur Utama

* Otentikasi: Login, register, reset password dengan verifikasi
* Dashboard Admin & Petugas
* Manajemen pelanggan: tambah/edit/hapus
* Sinkronisasi dan autentikasi dengan Mikrotik (RouterOS API)
* Pembuatan tagihan otomatis bulanan
* Riwayat pembayaran dan cetak struk
* Template HTML dengan Flask Jinja2
* Cron job terintegrasi untuk proses tagihan
* Siap dipakai dengan Docker dan Docker Compose

---

## 🧱 Struktur Proyek

```
billing-mikrotik/
├── app.py                  # Entry point aplikasi
├── billing-init.py         # Inisialisasi database SQLite
├── billing-cron.py         # Cron job untuk membuat tagihan bulanan
├── db.py                   # Utility database
├── mikrotik_helper.py      # Fungsi koneksi ke Router Mikrotik
├── routes/                 # Routing modul Flask
├── templates/              # Template HTML Jinja2
├── langganan.sqlite3       # File database SQLite (jika sudah dibuat)
├── requirements.txt        # Dependensi Python
├── Dockerfile              # Image Docker
├── docker-compose.yml      # Komposisi layanan Docker (opsional)
├── .env.example            # Contoh environment variabel
├── .dockerignore           # File/folder yang diabaikan saat build Docker
└── README.md               # Dokumentasi proyek
```

---

## ⚙️ Instalasi & Setup

### 💻 Jalankan Secara Manual (opsional)

1. Clone repository ini
2. Buat virtual environment
3. Install dependensi
4. Jalankan `python app.py`

### 🐳 Jalankan dengan Docker

1. Buat file `.env` berdasarkan `.env.example`
2. Build dan jalankan container:

   ```bash
   docker build -t billing-mikrotik .
   docker run -p 5001:5001 --env-file .env billing-mikrotik
   ```

### 🔁 Gunakan docker-compose (jika tersedia)

```bash
docker-compose up --build
```

---

## 🔄 Cron Job Penagihan Bulanan

Untuk menjalankan sistem penagihan otomatis:

1. Tambahkan entri cron di server Linux:

   ```cron
   1 0 1 * * /usr/bin/python3 /app/billing-cron.py >> /var/log/billing-cron.log 2>&1
   ```

2. Pastikan semua dependensi dan database tersedia saat cron berjalan.

---

## 🌐 Koneksi Mikrotik & WhatsApp API

### Koneksi Mikrotik (atur di `.env`):

```env
MIKROTIK_HOST=192.168.88.1
MIKROTIK_USER=admin
MIKROTIK_PASS=password
MIKROTIK_PORT=8728
```

### WhatsApp API

```env
WA_API_URL=http://your-wa-api/send-message
```

---

## 📦 Contoh `.env.example`

```env
SECRET_KEY=supersecretkey
WA_API_URL=http://your-wa-api/send-message
MIKROTIK_HOST=192.168.88.1
MIKROTIK_USER=admin
MIKROTIK_PASS=password
MIKROTIK_PORT=8728
```

---

## 📂 .dockerignore

```
__pycache__/
*.pyc
*.sqlite3
.env
*.log
```

---

## 🔐 Keamanan

* Jangan push `.env` ke GitHub
* Gunakan `.env.example` untuk referensi
* Backup rutin database SQLite
* Gunakan HTTPS untuk produksi

---

## 📞 Kontak & Lisensi

Untuk saran atau kontribusi:

> 📧 [info@bayarinter.net](mailto:info@bayarinter.net)

**Lisensi: MIT License**
