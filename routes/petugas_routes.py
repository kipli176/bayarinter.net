from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from db import get_db
from functools import wraps
from datetime import date, timedelta, datetime
from utils import kirim_tagihan
from werkzeug.security import check_password_hash
import locale
locale.setlocale(locale.LC_TIME, 'id_ID.UTF-8')

petugas_bp = Blueprint('petugas', __name__, url_prefix='/petugas')

# Dekorator login petugas
def petugas_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'petugas_id' not in session:
            flash('Silakan login sebagai petugas.', 'error')
            return redirect(url_for('petugas.login'))
        return f(*args, **kwargs)
    return decorated_function

# Login petugas
@petugas_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM petugas WHERE username = ?", (username,))
        petugas = c.fetchone()
        conn.close()

        if not petugas:
            flash('Akun tidak ditemukan.', 'error')
            return redirect(url_for('petugas.login'))

        if not check_password_hash(petugas['password_hash'], password):
            flash('Password salah.', 'error')
            return redirect(url_for('petugas.login'))

        session['petugas_id'] = petugas['id_petugas']
        session['petugas_nama'] = petugas['nama']
        flash('Login berhasil.', 'success')
        return redirect(url_for('petugas.dashboard'))

    return render_template('petugas_login.html')

# Dashboard petugas
@petugas_bp.route('/dashboard')
@petugas_login_required
def dashboard():
    bulan = request.args.get('bulan', date.today().replace(day=1).strftime('%Y-%m-01'))
    id_petugas = session['petugas_id']

    conn = get_db()
    c = conn.cursor()

    # Jumlah pelanggan yang ditangani petugas
    c.execute("SELECT COUNT(*) FROM pelanggan WHERE id_petugas = ?", (id_petugas,))
    jumlah_pelanggan = c.fetchone()[0]

    # Daftar id pelanggan yang ditangani petugas
    c.execute("SELECT id FROM pelanggan WHERE id_petugas = ?", (id_petugas,))
    id_pelanggan_list = [row['id'] for row in c.fetchall()]
    if not id_pelanggan_list:
        id_pelanggan_list = [0]  # untuk mencegah error IN () kosong

    # Jumlah & total tagihan bulan ini
    placeholders = ','.join(['?'] * len(id_pelanggan_list))
    c.execute(f"""
        SELECT COUNT(*), IFNULL(SUM(jumlah_tagihan), 0)
        FROM tagihan
        WHERE bulan = ? AND id_pelanggan IN ({placeholders})
    """, [bulan] + id_pelanggan_list)
    row = c.fetchone()
    jumlah_tagihan_bulan_ini = row[0]
    total_tagihan_bulan_ini = row[1]

    # Lunas & belum lunas
    c.execute(f"""
        SELECT status, COUNT(*) as jumlah
        FROM tagihan
        WHERE bulan = ? AND id_pelanggan IN ({placeholders})
        GROUP BY status
    """, [bulan] + id_pelanggan_list)
    status_dict = {r['status']: r['jumlah'] for r in c.fetchall()}
    jumlah_lunas = status_dict.get('lunas', 0)
    jumlah_belum_lunas = status_dict.get('belum lunas', 0) + status_dict.get('cicil', 0)

    jumlah_tagihan_lunas = 0
    if status_dict.get('lunas'):
        c.execute(f"""
            SELECT SUM(jumlah_tagihan)
            FROM tagihan
            WHERE bulan = ? AND status = 'lunas' AND id_pelanggan IN ({placeholders})
        """, [bulan] + id_pelanggan_list)
        jumlah_tagihan_lunas = c.fetchone()[0] or 0

    # Data tagihan pelanggan (tabel bawah)
    c.execute(f"""
        SELECT 
            p.id AS id_pelanggan,
            p.nama,
            p.paket,
            p.status AS status_pelanggan_terkini,
            t.id AS id_tagihan,
            t.jumlah_tagihan,
            t.status AS status_tagihan,
            IFNULL((SELECT SUM(jumlah_bayar) FROM pembayaran WHERE id_tagihan = t.id), 0) AS total_bayar,
            (t.jumlah_tagihan - IFNULL((SELECT SUM(jumlah_bayar) FROM pembayaran WHERE id_tagihan = t.id), 0)) AS sisa_tagihan
        FROM pelanggan p
        LEFT JOIN tagihan t ON p.id = t.id_pelanggan AND t.bulan = ?
        WHERE p.id_petugas = ?
        ORDER BY p.nama
    """, (bulan, id_petugas))
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

    # ✅ Bulan options (letakkan setelah loop, BUKAN di dalamnya)
    nama_bulan = {
        1: "Januari", 2: "Februari", 3: "Maret", 4: "April",
        5: "Mei", 6: "Juni", 7: "Juli", 8: "Agustus",
        9: "September", 10: "Oktober", 11: "November", 12: "Desember"
    }

    bulan_options = []
    for i in range(12):
        dt = date.today().replace(day=1) - timedelta(days=30 * i)
        kode = dt.strftime('%Y-%m-01')
        label = f"{nama_bulan[dt.month]} {dt.year}"
        bulan_options.append((kode, label))

    # ✅ Akhirnya return setelah semuanya diproses
    return render_template(
        'petugas_dashboard.html',
        data=data,
        bulan=bulan,
        bulan_options=bulan_options,
        jumlah_pelanggan=jumlah_pelanggan,
        jumlah_tagihan_bulan_ini=jumlah_tagihan_bulan_ini,
        total_tagihan_bulan_ini=total_tagihan_bulan_ini,
        jumlah_lunas=jumlah_lunas,
        jumlah_belum_lunas=jumlah_belum_lunas,
        jumlah_tagihan_lunas=jumlah_tagihan_lunas
    )


# Bayar tagihan oleh petugas
@petugas_bp.route('/bayar/<int:id_tagihan>', methods=['POST'])
@petugas_login_required
def bayar(id_tagihan):
    conn = get_db()
    c = conn.cursor()

    # Ambil tagihan yang valid milik pelanggan yang ditangani petugas
    c.execute("""
        SELECT t.*, p.id_petugas
        FROM tagihan t
        JOIN pelanggan p ON t.id_pelanggan = p.id
        WHERE t.id = ? AND p.id_petugas = ?
    """, (id_tagihan, session['petugas_id']))
    tagihan = c.fetchone()

    if not tagihan:
        conn.close()
        flash('Tagihan tidak ditemukan atau bukan wewenang Anda.', 'error')
        return redirect(url_for('petugas.dashboard'))

    try:
        jumlah_bayar = float(request.form['jumlah_bayar'])
        if jumlah_bayar <= 0:
            raise ValueError("Nominal tidak valid")

        # Insert pembayaran
        c.execute("""
            INSERT INTO pembayaran (id_tagihan, jumlah_bayar, tanggal_bayar)
            VALUES (?, ?, DATE('now'))
        """, (id_tagihan, jumlah_bayar))

        # Hitung total pembayaran terkini
        c.execute("""
            SELECT SUM(jumlah_bayar) FROM pembayaran WHERE id_tagihan = ?
        """, (id_tagihan,))
        total_bayar = c.fetchone()[0] or 0

        # Update status tagihan
        if total_bayar >= tagihan['jumlah_tagihan']:
            status_baru = 'lunas'
        elif total_bayar > 0:
            status_baru = 'cicil'
        else:
            status_baru = 'belum lunas'

        c.execute("""
            UPDATE tagihan SET status = ? WHERE id = ?
        """, (status_baru, id_tagihan))

        conn.commit()
        flash('Pembayaran berhasil dicatat.', 'success')
    except Exception as e:
        conn.rollback()
        flash(f'Gagal melakukan pembayaran: {e}', 'error')
    finally:
        conn.close()

    return redirect(url_for('petugas.dashboard'))

@petugas_bp.route('/cetak/<int:id_tagihan>')
@petugas_login_required
def cetak(id_tagihan):
    conn = get_db()
    c = conn.cursor()

    # Ambil data tagihan + pelanggan + petugas, pastikan petugas yang berwenang
    c.execute("""
        SELECT t.*, 
               p.nama AS nama, 
               p.no_hp,
               p.paket,
               t.bulan,
               t.status AS status_tagihan,
               pt.nama AS petugas
        FROM tagihan t
        JOIN pelanggan p ON p.id = t.id_pelanggan
        JOIN petugas pt ON p.id_petugas = pt.id_petugas
        WHERE t.id = ? AND p.id_petugas = ?
    """, (id_tagihan, session['petugas_id']))
    data = c.fetchone()

    if not data:
        conn.close()
        flash("Tagihan tidak ditemukan atau bukan wewenang Anda.", "error")
        return redirect(url_for('petugas.dashboard'))

    # Ambil riwayat pembayaran
    c.execute("SELECT * FROM pembayaran WHERE id_tagihan = ? ORDER BY tanggal_bayar", (id_tagihan,))
    riwayat = c.fetchall()

    # Hitung total bayar
    total_bayar = sum(r['jumlah_bayar'] for r in riwayat)
    conn.close()

    # Lengkapi data dict dengan properti tambahan untuk struk
    data = dict(data)
    data['total_bayar'] = total_bayar
    data['status'] = data['status_tagihan']

    return render_template("cetak_struk.html", data=data, riwayat=riwayat)


# Kirim notifikasi tagihan 
@petugas_bp.route('/kirim/<int:id_tagihan>', methods=['POST'])
@petugas_login_required
def kirim_tagihan_ke_pelanggan(id_tagihan):  
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

    return redirect(url_for("petugas.dashboard", bulan=tagihan["bulan"]))

# Suspend pelanggan
@petugas_bp.route('/suspen/<int:id_tagihan>', methods=['POST'])
@petugas_login_required
def suspen(id_tagihan):
    conn = get_db()
    c = conn.cursor()

    # Pastikan tagihan milik pelanggan yang ditangani petugas
    c.execute("""
        SELECT p.id AS id_pelanggan
        FROM tagihan t
        JOIN pelanggan p ON t.id_pelanggan = p.id
        WHERE t.id = ? AND p.id_petugas = ?
    """, (id_tagihan, session['petugas_id']))
    row = c.fetchone()

    if not row:
        conn.close()
        flash("Tidak dapat menyuspen. Tagihan bukan wewenang Anda.", "error")
        return redirect(url_for('petugas.dashboard'))

    id_pelanggan = row['id_pelanggan']

    try:
        c.execute("UPDATE pelanggan SET status = 'suspen' WHERE id = ?", (id_pelanggan,))
        conn.commit()
        flash("Pelanggan berhasil disuspen.", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Gagal menyuspen pelanggan: {e}", "error")
    finally:
        conn.close()

    return redirect(url_for('petugas.dashboard'))


# Logout
@petugas_bp.route('/logout')
def logout():
    session.pop('petugas_id', None)
    session.pop('petugas_nama', None)
    flash('Logout berhasil.', 'success')
    return redirect(url_for('petugas.login'))

@petugas_bp.route('/aktifkan/<int:id_pelanggan>', methods=['POST'])
@petugas_login_required
def aktifkan_pelanggan_petugas(id_pelanggan):
    conn = get_db()
    c = conn.cursor()

    # Cek pelanggan yang ditangani oleh petugas ini
    c.execute("""
        SELECT p.*, a.ip_address, a.ppp_username, a.ppp_password
        FROM pelanggan p
        JOIN admin a ON a.id_admin = p.id_admin
        WHERE p.id = ? AND p.id_petugas = ?
    """, (id_pelanggan, session['petugas_id']))
    pelanggan = c.fetchone()

    if not pelanggan:
        flash("❌ Pelanggan tidak ditemukan atau bukan tanggung jawab Anda.", "error")
        conn.close()
        return redirect(url_for('petugas.dashboard'))

    if not pelanggan['ip_address']:
        flash("❌ Mikrotik belum dikonfigurasi untuk pelanggan ini.", "error")
        conn.close()
        return redirect(url_for('petugas.dashboard'))

    try:
        api = connect_remote(pelanggan['ip_address'], pelanggan['ppp_username'], pelanggan['ppp_password'])
        ppp = api.get_resource('/ppp/secret')
        active = api.get_resource('/ppp/active')

        secrets = ppp.get(name=pelanggan['ppp_username'])
        for s in secrets:
            id_key = s.get('.id') or s.get('id')
            comment = s.get('comment') or ''
            profile_asli = 'billing'
            match = re.search(r'Paket:\s*(\w+)', comment)
            if match:
                profile_asli = match.group(1)

            if id_key:
                ppp.set(id=id_key, profile=profile_asli)
                sessions = active.get(name=pelanggan['ppp_username'])
                for a in sessions:
                    sid = a.get('.id') or a.get('id')
                    if sid:
                        active.remove(id=sid)

        # Update status di database
        c.execute("UPDATE pelanggan SET status = 'aktif' WHERE id = ? AND id_petugas = ?", (id_pelanggan, session['petugas_id']))
        conn.commit()
        flash(f"✅ Pelanggan telah diaktifkan kembali (profil: {profile_asli})", "success")

    except Exception as e:
        conn.rollback()
        flash(f"❌ Gagal mengaktifkan pelanggan: {e}", "error")
    finally:
        conn.close()

    return redirect(url_for('petugas.dashboard'))
