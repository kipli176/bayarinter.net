import sqlite3

DB_NAME = 'langganan.sqlite3'
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Tabel admin
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admin (
            id_admin INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            no_hp TEXT NOT NULL,
            nama TEXT NOT NULL,
            alamat TEXT,
            is_active INTEGER DEFAULT 0,
            otp_code TEXT,
            otp_expiry TEXT,
            date_created TEXT DEFAULT CURRENT_TIMESTAMP,
            last_login TEXT,
            ip_address TEXT DEFAULT NULL,
            ppp_username TEXT DEFAULT NULL,
            ppp_password TEXT DEFAULT NULL
        );
    ''')

    # Tabel petugas (turunan dari admin)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS petugas (
            id_petugas INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            nama TEXT NOT NULL,
            no_hp TEXT,
            id_admin INTEGER,
            date_created TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (id_admin) REFERENCES admin(id_admin)
        );
    ''')

    # Tabel pelanggan (relasi ke admin dan petugas)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pelanggan (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_admin INTEGER,
            id_petugas INTEGER,
            nama TEXT NOT NULL,
            alamat TEXT,
            no_hp TEXT,
            paket TEXT,
            harga_bulanan REAL,
            ppp_username TEXT,
            ppp_password TEXT,
            tgl_pasang TEXT,
            date_created TEXT DEFAULT CURRENT_TIMESTAMP,
            status TEXT CHECK(status IN ('aktif', 'tidak aktif', 'suspen')) NOT NULL DEFAULT 'aktif',
            FOREIGN KEY (id_admin) REFERENCES admin(id_admin),
            FOREIGN KEY (id_petugas) REFERENCES petugas(id_petugas)
        );
    ''')

    # Tabel tagihan (tanpa kolom petugas karena diambil dari pelanggan)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tagihan (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_pelanggan INTEGER,
            bulan TEXT,
            jumlah_tagihan REAL,
            status_pelanggan_bulan_ini TEXT CHECK(status_pelanggan_bulan_ini IN ('aktif', 'tidak aktif', 'suspen')),
            status TEXT CHECK(status IN ('belum lunas', 'cicil', 'lunas')) DEFAULT 'belum lunas',
            FOREIGN KEY (id_pelanggan) REFERENCES pelanggan(id)
        );
    ''')

    # Tabel pembayaran
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pembayaran (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_tagihan INTEGER,
            tanggal_bayar TEXT,
            jumlah_bayar REAL,
            FOREIGN KEY (id_tagihan) REFERENCES tagihan(id)
        );
    ''')

    conn.commit()
    conn.close()
    print(f"✅ Database berhasil dibuat: {DB_NAME}")

if __name__ == '__main__':
    init_db()