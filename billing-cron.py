#1 0 1 * * /usr/bin/python3 /path/to/generate_tagihan_bulanan.py >> /path/to/log_generate_tagihan.log 2>&1

import sqlite3
import sys
from datetime import datetime, timedelta
from mikrotik_helper import connect_remote 
import time
from datetime import datetime
from utils import kirim_tagihan
from db import get_db

DB_NAME = 'langganan.sqlite3'

def get_bulan_sebelumnya(bulan_str):
    bulan = datetime.strptime(bulan_str, '%Y-%m-%d')
    bulan_lalu = bulan.replace(day=1) - timedelta(days=1)
    return bulan_lalu.strftime('%Y-%m-01')

def generate_tagihan_bulanan(bulan=None, petugas='Admin'):
    if bulan is None:
        bulan = datetime.now().strftime('%Y-%m-01')

    bulan_lalu = get_bulan_sebelumnya(bulan)

    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # Ambil semua pelanggan
    c.execute("SELECT * FROM pelanggan")
    pelanggan_list = c.fetchall()

    jumlah_dibuat = 0

    for p in pelanggan_list:
        id_pelanggan = p['id']
        harga = p['harga_bulanan']
        status_pelanggan = p['status'].lower()  # aktif, tidak aktif, suspen

        if status_pelanggan != 'aktif':
            print(f"Pelanggan ID {id_pelanggan} status '{status_pelanggan}', tidak dibuatkan tagihan bulan {bulan}")
            continue

        # Cek apakah tagihan bulan ini sudah dibuat
        c.execute('''
            SELECT COUNT(*) as jml FROM tagihan
            WHERE id_pelanggan = ? AND bulan = ?
        ''', (id_pelanggan, bulan))
        if c.fetchone()['jml'] > 0:
            continue  # Skip jika sudah ada

        # Cari sisa tagihan bulan sebelumnya
        c.execute('''
            SELECT t.id, t.jumlah_tagihan, IFNULL(SUM(p.jumlah_bayar), 0) AS total_bayar
            FROM tagihan t
            LEFT JOIN pembayaran p ON p.id_tagihan = t.id
            WHERE t.id_pelanggan = ? AND t.bulan = ?
            GROUP BY t.id
        ''', (id_pelanggan, bulan_lalu))

        row_lalu = c.fetchone()
        sisa_lalu = 0
        if row_lalu:
            sisa_lalu = row_lalu['jumlah_tagihan'] - row_lalu['total_bayar']
            if sisa_lalu < 0:
                sisa_lalu = 0  # prevent error from overpayment

        # Hitung total tagihan bulan ini
        jumlah_tagihan = harga + sisa_lalu

        # Buat tagihan baru
        c.execute('''
            INSERT INTO tagihan (
                id_pelanggan,
                bulan,
                jumlah_tagihan,
                status_pelanggan_bulan_ini,
                status,
                petugas
            ) VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            id_pelanggan,
            bulan,
            jumlah_tagihan,
            status_pelanggan,
            'belum lunas',
            petugas
        ))

        jumlah_dibuat += 1

    conn.commit()
    conn.close()
    print(f"✅ {jumlah_dibuat} tagihan berhasil dibuat untuk bulan {bulan}.")

def suspen_otomatis_berdasarkan_tunggakan():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    hari_ini = datetime.now()
    bulan_ini = hari_ini.strftime('%Y-%m-01')

    # Ambil pelanggan aktif
    c.execute('''
        SELECT p.*, a.ip_address, a.ppp_username AS admin_user, a.ppp_password AS admin_pass
        FROM pelanggan p
        JOIN admin a ON a.id_admin = p.id_admin
        WHERE p.status = 'aktif'
    ''')
    pelanggan_list = c.fetchall()

    for p in pelanggan_list:
        try:
            # Cek tagihan bulan ini
            c.execute("SELECT status FROM tagihan WHERE id_pelanggan = ? AND bulan = ?", (p['id'], bulan_ini))
            tagihan = c.fetchone()
            if not tagihan or tagihan['status'] == 'lunas':
                continue  # Tidak perlu disuspen

            # Cek apakah sudah lewat tgl_pasang
            tgl_pasang = datetime.strptime(p['tgl_pasang'], '%Y-%m-%d')
            if hari_ini.day < tgl_pasang.day:
                continue  # Belum jatuh tempo

            # Koneksi ke Mikrotik dan ubah profil ke isolir
            api = connect_remote(p['ip_address'], p['admin_user'], p['admin_pass'])
            ppp = api.get_resource('/ppp/secret')
            s = ppp.get(name=p['ppp_username'])

            for item in s:
                id_key = item.get('.id') or item.get('id')
                if id_key:
                    ppp.set(id=id_key, profile='isolir')

            # Putuskan koneksi aktif
            active = api.get_resource('/ppp/active')
            actives = active.get(name=p['ppp_username'])
            for a in actives:
                aid = a.get('.id') or a.get('id')
                if aid:
                    active.remove(id=aid)

            # Update status pelanggan
            c.execute("UPDATE pelanggan SET status = 'suspen' WHERE id = ?", (p['id'],))
            conn.commit()

            print(f"🔒 Pelanggan {p['nama']} disuspen otomatis.")

        except Exception as e:
            print(f"❌ Gagal menyuspen {p['nama']}: {e}")

    conn.close()
def kirim_notifikasi_massal_tagihan():
    today = datetime.today()

    if today.day != 1:
        print("[INFO] Hari ini bukan tanggal 1. Notifikasi tagihan tidak dikirim.")
        return

    bulan = today.replace(day=1).strftime('%Y-%m-%d')  # format untuk kolom `bulan`

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            t.id AS id_tagihan,
            t.jumlah_tagihan,
            t.bulan,
            p.nama,
            p.no_hp
        FROM pelanggan p
        JOIN tagihan t ON p.id = t.id_pelanggan AND t.bulan = ?
        WHERE p.no_hp IS NOT NULL AND t.jumlah_tagihan > 0
    """, (bulan,))

    
    tagihan_list = cursor.fetchall()
    total_dikirim = 0
    gagal_dikirim = 0

    for tagihan in tagihan_list:
        if not tagihan["no_hp"] or not tagihan["jumlah_tagihan"]:
            print(f"[SKIP] {tagihan['nama']} - nomor HP/tagihan tidak valid")
            continue

        try:
            # Format bulan
            bulan_obj = datetime.strptime(tagihan["bulan"], "%Y-%m-%d")
            bulan_format = bulan_obj.strftime("%B %Y")  # contoh: "Juni 2025"

            success = kirim_tagihan(
                no_hp=tagihan["no_hp"],
                nama=tagihan["nama"],
                jumlah_tagihan=tagihan["jumlah_tagihan"],
                bulan=bulan_format
            )

            if success:
                print(f"[✅] Notifikasi terkirim ke {tagihan['nama']} ({tagihan['no_hp']})")
                total_dikirim += 1
            else:
                print(f"[❌] Gagal kirim ke {tagihan['nama']}")
                gagal_dikirim += 1

            time.sleep(3)  # ⏱️ jeda 3 detik antar pengiriman

        except Exception as e:
            print(f"[⚠️ ERROR] {tagihan['nama']}: {e}")
            gagal_dikirim += 1

    print(f"\n[📋 Rangkuman]")
    print(f"✅ Berhasil dikirim: {total_dikirim}")
    print(f"❌ Gagal dikirim: {gagal_dikirim}")

if __name__ == '__main__':
    bulan_arg = sys.argv[1] if len(sys.argv) > 1 else None
    generate_tagihan_bulanan(bulan=bulan_arg)
    suspen_otomatis_berdasarkan_tunggakan()
    kirim_notifikasi_massal_tagihan()
