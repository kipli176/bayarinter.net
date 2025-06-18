from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from db import get_db
from datetime import datetime, date, timedelta
from utils import kirim_tagihan
from functools import wraps

tagihan_bp = Blueprint('tagihan', __name__)

# Dekorator login admin
def admin_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_id' not in session:
            flash('Silakan login terlebih dahulu.', 'error')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

@tagihan_bp.route('/tagihan')
@admin_login_required
def tagihan():
    bulan = request.args.get('bulan', date.today().replace(day=1).strftime('%Y-%m-%d'))
    id_admin = session['admin_id']

    bulan_options = [
        (date.today().replace(day=1) - timedelta(days=30 * i)).strftime('%Y-%m-01')
        for i in range(12)
    ]

    conn = get_db()
    c = conn.cursor()
    c.execute('''
        SELECT 
            p.id AS id_pelanggan,
            p.nama,
            p.paket,
            p.status AS status_pelanggan_terkini,
            t.id AS id_tagihan,
            t.jumlah_tagihan,
            t.status AS status_tagihan,
            IFNULL((SELECT SUM(jumlah_bayar) FROM pembayaran pb WHERE pb.id_tagihan = t.id), 0) AS total_bayar,
            (t.jumlah_tagihan - IFNULL((SELECT SUM(jumlah_bayar) FROM pembayaran pb WHERE pb.id_tagihan = t.id), 0)) AS sisa_tagihan,
            t.petugas
        FROM pelanggan p
        LEFT JOIN tagihan t ON p.id = t.id_pelanggan AND t.bulan = ?
        WHERE p.id_admin = ?
        ORDER BY p.nama
    ''', (bulan, id_admin))
    rows = c.fetchall()
    conn.close()

    data = []
    for row in rows:
        item = dict(row)
        if item['id_tagihan'] is None:
            item['status_pembayaran'] = 'tidak ada tagihan'
            item['sisa_tagihan'] = 0
        else:
            bayar = item['total_bayar']
            total = item['jumlah_tagihan']
            if bayar == 0:
                item['status_pembayaran'] = 'belum lunas'
            elif bayar < total:
                item['status_pembayaran'] = 'cicil'
            else:
                item['status_pembayaran'] = 'lunas'
        data.append(item)

    return render_template('tagihan.html', data=data, bulan=bulan, bulan_options=bulan_options)

@tagihan_bp.route('/tagihan/bayar/<int:id_tagihan>', methods=['POST'])
@admin_login_required
def bayar(id_tagihan):
    conn = get_db()
    c = conn.cursor()

    c.execute('''
        SELECT t.id, t.jumlah_tagihan, t.status, p.nama
        FROM tagihan t
        JOIN pelanggan p ON t.id_pelanggan = p.id
        WHERE t.id = ?
    ''', (id_tagihan,))
    tagihan = c.fetchone()

    if not tagihan:
        conn.close()
        flash('Tagihan tidak ditemukan.', 'error')
        return redirect(url_for('tagihan.tagihan'))

    try:
        jumlah_bayar = float(request.form['jumlah_bayar'])
        if jumlah_bayar <= 0:
            flash('Jumlah bayar harus lebih dari 0.', 'error')
            return redirect(url_for('tagihan.tagihan'))

        tanggal_bayar = datetime.now().strftime('%Y-%m-%d')

        c.execute('''
            INSERT INTO pembayaran (id_tagihan, tanggal_bayar, jumlah_bayar)
            VALUES (?, ?, ?)
        ''', (id_tagihan, tanggal_bayar, jumlah_bayar))

        c.execute('''
            SELECT SUM(jumlah_bayar) as total_bayar
            FROM pembayaran
            WHERE id_tagihan = ?
        ''', (id_tagihan,))
        total_bayar = c.fetchone()['total_bayar'] or 0

        status_bayar = 'belum lunas'
        if total_bayar >= tagihan['jumlah_tagihan']:
            status_bayar = 'lunas'
        elif total_bayar > 0:
            status_bayar = 'cicil'

        c.execute('UPDATE tagihan SET status = ? WHERE id = ?', (status_bayar, id_tagihan))
        conn.commit()
        flash(f'Pembayaran berhasil dicatat. Status tagihan: {status_bayar}', 'success')

    except Exception as e:
        flash(f'Gagal memproses pembayaran: {e}', 'error')

    finally:
        conn.close()

    return redirect(url_for('tagihan.tagihan'))


@tagihan_bp.route('/tagihan/cetak/<int:id_tagihan>')
@admin_login_required
def cetak_pembayaran(id_tagihan):
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        SELECT 
            p.nama, p.alamat, p.no_hp, p.petugas,
            t.bulan, t.jumlah_tagihan, t.status,
            (SELECT SUM(jumlah_bayar) FROM pembayaran WHERE id_tagihan = t.id) AS total_bayar,
            t.petugas
        FROM tagihan t
        JOIN pelanggan p ON t.id_pelanggan = p.id
        WHERE t.id = ? AND p.id_admin = ?
    ''', (id_tagihan, session['admin_id']))
    data = c.fetchone()

    if not data:
        flash('Data pembayaran tidak ditemukan atau bukan milik Anda.', 'error')
        return redirect(url_for('tagihan.tagihan'))

    c.execute('''
        SELECT tanggal_bayar, jumlah_bayar 
        FROM pembayaran 
        WHERE id_tagihan = ? 
        ORDER BY tanggal_bayar
    ''', (id_tagihan,))
    riwayat = c.fetchall()
    conn.close()

    return render_template('cetak_struk.html', data=data, riwayat=riwayat)

@tagihan_bp.route('/tagihan/kirim-notifikasi', methods=['POST'])
@admin_login_required
def kirim_notifikasi():
    id_tagihan = request.form.get("id_tagihan")
    conn = get_db()

    tagihan = conn.execute('''
        SELECT 
            t.id AS id_tagihan, t.jumlah_tagihan, t.bulan,
            p.nama, p.no_hp
        FROM tagihan t
        JOIN pelanggan p ON p.id = t.id_pelanggan
        WHERE t.id = ?
    ''', (id_tagihan,)).fetchone()

    if not tagihan:
        flash("❌ Data tagihan tidak ditemukan", "error")
        return redirect(url_for("tagihan.tagihan"))

    if not tagihan["no_hp"]:
        flash("❌ Nomor HP pelanggan tidak tersedia", "error")
        return redirect(url_for("tagihan.tagihan"))

    if not tagihan["jumlah_tagihan"] or tagihan["jumlah_tagihan"] <= 0:
        flash("❌ Tidak ada jumlah tagihan yang valid untuk dikirim", "error")
        return redirect(url_for("tagihan.tagihan"))

    try:
        bulan_format = datetime.strptime(tagihan["bulan"], "%Y-%m-%d").strftime("%B %Y")
        success = kirim_tagihan(
            no_hp=tagihan["no_hp"],
            nama=tagihan["nama"],
            jumlah_tagihan=tagihan["jumlah_tagihan"],
            bulan=bulan_format
        )
        if success:
            flash(f"✅ Notifikasi berhasil dikirim ke {tagihan['nama']}", "success")
        else:
            flash(f"❌ Gagal mengirim notifikasi ke {tagihan['nama']}", "error")
    except Exception as e:
        flash(f"⚠️ Terjadi kesalahan: {e}", "error")

    return redirect(url_for("tagihan.tagihan", bulan=tagihan["bulan"]))