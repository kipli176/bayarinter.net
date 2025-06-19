from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from db import get_db
from mikrotik_helper import (
    check_active_bulk, delete_secret_remote, add_secret_remote,
    connect_remote, get_profiles_remote
)
from functools import wraps
import re
from utils import normalize_nomor_hp

pelanggan_bp = Blueprint('pelanggan', __name__)

# Dekorator untuk login admin

def admin_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_id' not in session:
            flash('Silakan login terlebih dahulu.', 'error')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


@pelanggan_bp.route('/sinkron-pelanggan', methods=['POST'])
@admin_login_required
def sinkron_pelanggan():
    conn = get_db()
    c = conn.cursor()

    c.execute('SELECT ip_address, ppp_username, ppp_password FROM admin WHERE id_admin = ?', (session['admin_id'],))
    admin_data = c.fetchone()

    if not admin_data or not admin_data['ip_address']:
        flash('IP address Mikrotik tidak ditemukan atau admin belum aktif.', 'error')
        conn.close()
        return redirect(url_for('pelanggan.pelanggan'))

    try:
        api = connect_remote(admin_data['ip_address'], admin_data['ppp_username'], admin_data['ppp_password'])

        active_users = api.get_resource('/ppp/active').get()
        active_names = {u['name'] for u in active_users if 'name' in u}
        secrets = api.get_resource('/ppp/secret').get()

        synced = 0
        for secret in secrets:
            name = secret.get('name')
            if not name or name not in active_names:
                continue

            c.execute(
                'SELECT COUNT(*) FROM pelanggan WHERE ppp_username = ? AND id_admin = ?',
                (name, session['admin_id'])
            )
            if c.fetchone()[0] == 0:
                password = secret.get('password', '')
                profile = secret.get('profile', '')
                c.execute('''
                    INSERT INTO pelanggan (nama, ppp_username, ppp_password, paket, harga_bulanan, status, id_admin)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (name, name, password, profile, '1.00', 'aktif', session['admin_id']))
                synced += 1

        conn.commit()
        flash(f'{synced} pelanggan aktif berhasil diimpor dari Mikrotik.', 'success')

    except Exception as e:
        flash(f'Gagal sinkronisasi: {e}', 'error')

    finally:
        conn.close()

    return redirect(url_for('pelanggan.pelanggan'))


@pelanggan_bp.route('/pelanggan')
@admin_login_required
def pelanggan():
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT p.*, pt.nama AS nama_petugas
        FROM pelanggan p
        LEFT JOIN petugas pt ON p.id_petugas = pt.id_petugas
        WHERE p.id_admin = ?
    """, (session['admin_id'],))
    data_pelanggan = c.fetchall()
    # c.execute("SELECT * FROM pelanggan WHERE id_admin = ?", (session['admin_id'],))
    # data_pelanggan = c.fetchall()

    c.execute("SELECT ip_address, ppp_username, ppp_password FROM admin WHERE id_admin = ?", (session['admin_id'],))
    admin_data = c.fetchone()
    conn.close()

    username_list = [p['ppp_username'] for p in data_pelanggan]
    status_koneksi = {}

    if not admin_data or not admin_data['ip_address']:
        flash('Admin belum mengatur koneksi Mikrotik.', 'error')
        status_koneksi = {u: 'offline' for u in username_list}
    else:
        try:
            api = connect_remote(admin_data['ip_address'], admin_data['ppp_username'], admin_data['ppp_password'])
            status_koneksi = check_active_bulk(api, username_list)
        except Exception as e:
            flash(f'Gagal koneksi ke Mikrotik: {e}', 'error')
            status_koneksi = {u: 'offline' for u in username_list}

    return render_template(
        'pelanggan.html',
        data=data_pelanggan,
        status_koneksi=status_koneksi
    )


@pelanggan_bp.route('/pelanggan/tambah', methods=['GET', 'POST'])
@admin_login_required
def tambah_pelanggan():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT ip_address, ppp_username, ppp_password FROM admin WHERE id_admin = ?", (session['admin_id'],))
    admin_data = c.fetchone()    
    c.execute("SELECT id_petugas, nama FROM petugas WHERE id_admin = ?", (session['admin_id'],))
    petugas_list = c.fetchall() 
    conn.close()

    if not admin_data or not admin_data['ip_address']:
        flash('Admin belum mengatur koneksi Mikrotik.', 'error')
        return redirect(url_for('pelanggan.tambah_pelanggan'))

    if request.method == 'POST':
        # nama = request.form['nama']
        # alamat = request.form['alamat']
        # no_hp = request.form['no_hp']
        # paket = request.form['paket']
        # harga = float(request.form['harga_bulanan'])
        # ppp_user = request.form['ppp_username']
        # ppp_pass = request.form['ppp_password']
        # # petugas = request.form['petugas']
        # status = request.form['status']
        # tgl_pasang = request.form['tgl_pasang']
        nama = request.form['nama']
        alamat = request.form['alamat']
        no_hp = normalize_nomor_hp(request.form['no_hp'])
        paket = request.form['paket']
        harga_bulanan = float(request.form['harga_bulanan'])
        ppp_username = request.form['ppp_username']
        ppp_password = request.form['ppp_password']
        tgl_pasang = request.form['tgl_pasang']
        status = request.form['status']
        id_petugas_raw = request.form.get('id_petugas')
        id_petugas = int(id_petugas_raw) if id_petugas_raw else None

        try:
            conn = get_db()
            c = conn.cursor()
            api = connect_remote(admin_data['ip_address'], admin_data['ppp_username'], admin_data['ppp_password'])             
            petugas_nama = ''
            if id_petugas:
                c.execute("SELECT nama FROM petugas WHERE id_petugas = ? AND id_admin = ?", (id_petugas, session['admin_id']))
                row = c.fetchone()
                if row:
                    petugas_nama = row['nama']
            comment = f"Nama: {nama} | HP: {no_hp} | Paket: {paket} | Pasang: {tgl_pasang}"
            if petugas_nama:
                comment += f" | Petugas: {petugas_nama}"
            add_secret_remote(api, name=ppp_username, password=ppp_password, comment=comment, profile=paket, service='pppoe')

            c.execute('''
            INSERT INTO pelanggan (id_admin, id_petugas, nama, alamat, no_hp, paket, harga_bulanan, ppp_username, ppp_password, tgl_pasang, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (session['admin_id'], id_petugas, nama, alamat, no_hp, paket, harga_bulanan, ppp_username, ppp_password, tgl_pasang, status))

            # c.execute('''
            #     INSERT INTO pelanggan 
            #     (id_admin, nama, alamat, no_hp, paket, harga_bulanan, 
            #      ppp_username, ppp_password, status, tgl_pasang, petugas)
            #     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            # ''', (
            #     session['admin_id'], nama, alamat, no_hp, paket,
            #     harga, ppp_user, ppp_pass, status, tgl_pasang, petugas
            # ))
            conn.commit()
            conn.close()

            flash('Pelanggan dan user Mikrotik berhasil ditambahkan.', 'success')
            return redirect(url_for('pelanggan.pelanggan'))

        except Exception as e:
            flash(f'Gagal menambahkan pelanggan: {e}', 'error')
            return redirect(url_for('pelanggan.tambah_pelanggan'))

    try:
        api = connect_remote(admin_data['ip_address'], admin_data['ppp_username'], admin_data['ppp_password'])
        profil_list = get_profiles_remote(api)
    except Exception as e:
        profil_list = []
        flash(f'Gagal mengambil profil dari Mikrotik: {e}', 'error')

    return render_template('tambah_pelanggan.html', profil_list=profil_list,petugas_list=petugas_list)


@pelanggan_bp.route('/pelanggan/edit/<int:id>', methods=['GET', 'POST'])
@admin_login_required
def edit_pelanggan(id):
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT * FROM pelanggan WHERE id = ? AND id_admin = ?", (id, session['admin_id']))
    pelanggan_data = c.fetchone()

    if not pelanggan_data:
        conn.close()
        flash('Pelanggan tidak ditemukan.', 'error')
        return redirect(url_for('pelanggan.pelanggan'))

    c.execute("SELECT ip_address, ppp_username, ppp_password FROM admin WHERE id_admin = ?", (session['admin_id'],))
    admin_data = c.fetchone()   
    c.execute("SELECT id_petugas, nama FROM petugas WHERE id_admin = ?", (session['admin_id'],))
    petugas_list = c.fetchall() 
    conn.close()

    if not admin_data or not admin_data['ip_address']:
        flash('Admin belum mengatur koneksi Mikrotik.', 'error')
        return redirect(url_for('pelanggan.pelanggan'))

    if request.method == 'POST':
        # nama = request.form['nama']
        # alamat = request.form['alamat']
        # no_hp = request.form['no_hp']
        # paket = request.form['paket']
        # harga_bulanan = float(request.form['harga_bulanan'])
        # ppp_username_new = request.form['ppp_username']
        # ppp_password_new = request.form['ppp_password']
        # petugas = request.form['petugas']
        # status = request.form['status']
        # tgl_pasang = request.form['tgl_pasang']
        nama = request.form['nama']
        alamat = request.form['alamat']
        no_hp = normalize_nomor_hp(request.form['no_hp'])
        paket = request.form['paket']
        harga_bulanan = float(request.form['harga_bulanan'])
        ppp_username = request.form['ppp_username']
        ppp_password = request.form['ppp_password']
        tgl_pasang = request.form['tgl_pasang']
        status = request.form['status']
        id_petugas_raw = request.form.get('id_petugas')
        id_petugas = int(id_petugas_raw) if id_petugas_raw else None 
        try:
            conn = get_db()
            c = conn.cursor()
            api = connect_remote(admin_data['ip_address'], admin_data['ppp_username'], admin_data['ppp_password'])
            if ppp_username != pelanggan_data['ppp_username']:
                delete_secret_remote(api, pelanggan_data['ppp_username'])

            petugas_nama = ''
            if id_petugas:
                c.execute("SELECT nama FROM petugas WHERE id_petugas = ? AND id_admin = ?", (id_petugas, session['admin_id']))
                row = c.fetchone()
                if row:
                    petugas_nama = row['nama']
            comment = f"Nama: {nama} | HP: {no_hp} | Paket: {paket} | Pasang: {tgl_pasang}"
            if petugas_nama:
                comment += f" | Petugas: {petugas_nama}" 
            delete_secret_remote(api, ppp_username)
            add_secret_remote(api, name=ppp_username, password=ppp_password, comment=comment, profile=paket, service='pppoe')

            c.execute('''
                UPDATE pelanggan
                SET nama = ?, alamat = ?, no_hp = ?, paket = ?, harga_bulanan = ?, 
                    ppp_username = ?, ppp_password = ?, tgl_pasang = ?, status = ?, id_petugas = ?
                WHERE id = ? AND id_admin = ?
            ''', (nama, alamat, no_hp, paket, harga_bulanan, ppp_username, ppp_password, tgl_pasang, status, id_petugas, id, session['admin_id']))

            # c.execute('''
            #     UPDATE pelanggan SET
            #         nama = ?, alamat = ?, no_hp = ?, paket = ?, harga_bulanan = ?,
            #         ppp_username = ?, ppp_password = ?, status = ?, tgl_pasang = ?, petugas = ?
            #     WHERE id = ? AND id_admin = ?
            # ''', (
            #     nama, alamat, no_hp, paket, harga_bulanan,
            #     ppp_username_new, ppp_password_new, status, tgl_pasang, petugas,
            #     id, session['admin_id']
            # ))
            conn.commit()
            conn.close()

            flash('Data pelanggan dan Mikrotik berhasil diperbarui.', 'success')
            return redirect(url_for('pelanggan.pelanggan'))
        

        except Exception as e:
            flash(f'Gagal memperbarui pelanggan: {e}', 'error')
            return redirect(url_for('pelanggan.edit_pelanggan', id=id))

    try:
        api = connect_remote(admin_data['ip_address'], admin_data['ppp_username'], admin_data['ppp_password'])
        profil_list = get_profiles_remote(api)
    except Exception as e:
        profil_list = []
        flash(f'Gagal mengambil profil Mikrotik: {e}', 'error')
    return render_template('edit_pelanggan.html', pelanggan=pelanggan_data, profil_list=profil_list, petugas_list=petugas_list)

@pelanggan_bp.route('/pelanggan/hapus/<int:id>', methods=['POST'])
@admin_login_required
def hapus_pelanggan(id):
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT * FROM pelanggan WHERE id = ? AND id_admin = ?", (id, session['admin_id']))
    pelanggan = c.fetchone()

    if not pelanggan:
        conn.close()
        flash('Pelanggan tidak ditemukan.', 'error')
        return redirect(url_for('pelanggan.pelanggan'))

    c.execute("SELECT ip_address, ppp_username, ppp_password FROM admin WHERE id_admin = ?", (session['admin_id'],))
    admin_data = c.fetchone()
    conn.close()

    if not admin_data or not admin_data['ip_address']:
        flash('Admin belum mengatur koneksi Mikrotik.', 'error')
        return redirect(url_for('pelanggan.pelanggan'))

    try:
        api = connect_remote(admin_data['ip_address'], admin_data['ppp_username'], admin_data['ppp_password'])
        delete_secret_remote(api, pelanggan['ppp_username'])
    except Exception as e:
        flash(f'Gagal menghapus secret Mikrotik: {e}', 'error')

    try:
        conn = get_db()
        c = conn.cursor()

        # Dapatkan semua id_tagihan milik pelanggan
        c.execute("SELECT id FROM tagihan WHERE id_pelanggan = ?", (id,))
        tagihan_ids = [row['id'] for row in c.fetchall()]

        if tagihan_ids:
            placeholders = ','.join(['?'] * len(tagihan_ids))
            # Hapus pembayaran terlebih dahulu
            c.execute(f"DELETE FROM pembayaran WHERE id_tagihan IN ({placeholders})", tagihan_ids)
            # Hapus tagihan
            c.execute("DELETE FROM tagihan WHERE id_pelanggan = ?", (id,))

        # Hapus pelanggan
        c.execute("DELETE FROM pelanggan WHERE id = ? AND id_admin = ?", (id, session['admin_id']))
        conn.commit()
        conn.close()
        flash('Pelanggan dan data terkait berhasil dihapus.', 'success')

    except Exception as e:
        conn.rollback()
        flash(f'Gagal menghapus pelanggan dari database: {e}', 'error')

    return redirect(url_for('pelanggan.pelanggan'))


@pelanggan_bp.route('/pelanggan/suspen/<int:id>', methods=['POST'])
@admin_login_required
def suspen_pelanggan(id):
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT * FROM pelanggan WHERE id = ? AND id_admin = ? AND id_petugas is not null", (id, session['admin_id']))
    petugase = c.fetchone()

    if not petugase:
        conn.close()
        flash('Pelanggan ini belum ada petugasnya.', 'error')
        return redirect(url_for('pelanggan.pelanggan'))
    
    c.execute("SELECT * FROM pelanggan WHERE id = ? AND id_admin = ?", (id, session['admin_id']))
    pelanggan = c.fetchone()

    if not pelanggan:
        conn.close()
        flash('Pelanggan tidak ditemukan.', 'error')
        return redirect(url_for('pelanggan.pelanggan'))

    c.execute("SELECT ip_address, ppp_username, ppp_password FROM admin WHERE id_admin = ?", (session['admin_id'],))
    admin_data = c.fetchone()
    conn.close()

    if not admin_data or not admin_data['ip_address']:
        flash('Admin belum mengatur koneksi Mikrotik.', 'error')
        return redirect(url_for('pelanggan.pelanggan'))

    try:
        api = connect_remote(admin_data['ip_address'], admin_data['ppp_username'], admin_data['ppp_password'])
        ppp = api.get_resource('/ppp/secret')
        active = api.get_resource('/ppp/active')

        secrets = ppp.get(name=pelanggan['ppp_username'])
        for s in secrets:
            id_key = s.get('.id') or s.get('id')
            if id_key:
                ppp.set(id=id_key, profile='isolir')
                sessions = active.get(name=pelanggan['ppp_username'])
                for a in sessions:
                    sid = a.get('.id') or a.get('id')
                    if sid:
                        active.remove(id=sid)

        conn = get_db()
        c = conn.cursor()
        c.execute("UPDATE pelanggan SET status = 'suspen' WHERE id = ? AND id_admin = ?", (id, session['admin_id']))
        conn.commit()
        conn.close()

        flash('Pelanggan berhasil disuspen (profil diubah menjadi isolir).', 'success')

    except Exception as e:
        flash(f'Gagal menyuspen pelanggan: {e}', 'error')

    return redirect(url_for('pelanggan.pelanggan'))

@pelanggan_bp.route('/pelanggan/aktifkan/<int:id>', methods=['POST'])
@admin_login_required
def aktifkan_pelanggan(id):
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT * FROM pelanggan WHERE id = ? AND id_admin = ?", (id, session['admin_id']))
    pelanggan = c.fetchone()

    if not pelanggan:
        conn.close()
        flash('Pelanggan tidak ditemukan.', 'error')
        return redirect(url_for('pelanggan.pelanggan'))

    c.execute("SELECT ip_address, ppp_username, ppp_password FROM admin WHERE id_admin = ?", (session['admin_id'],))
    admin_data = c.fetchone()
    conn.close()

    if not admin_data or not admin_data['ip_address']:
        flash('Admin belum mengatur koneksi Mikrotik.', 'error')
        return redirect(url_for('pelanggan.pelanggan'))

    try:
        api = connect_remote(admin_data['ip_address'], admin_data['ppp_username'], admin_data['ppp_password'])
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

        conn = get_db()
        c = conn.cursor()
        c.execute("UPDATE pelanggan SET status = 'aktif' WHERE id = ? AND id_admin = ?", (id, session['admin_id']))
        conn.commit()
        conn.close()

        flash(f'Pelanggan telah diaktifkan kembali (profil: {profile_asli}).', 'success')

    except Exception as e:
        flash(f'Gagal mengaktifkan pelanggan: {e}', 'error')

    return redirect(url_for('pelanggan.pelanggan'))
