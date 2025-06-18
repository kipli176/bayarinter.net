from flask import Blueprint, render_template, session, redirect, url_for, flash, jsonify, request
from werkzeug.security import generate_password_hash
from db import get_db
from mikrotik_helper import (
    secret_exists, delete_secret, active_exists,
    delete_active, add_secret, get_active_ppp_ip, connect_remote
)
from datetime import datetime
from functools import wraps
import logging
from utils import normalize_nomor_hp

admin_bp = Blueprint('admin', __name__)
logging.basicConfig(level=logging.INFO)

def admin_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_id' not in session:
            flash('Silakan login terlebih dahulu.', 'error')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

@admin_bp.route('/')
def landing():
    return render_template('index.html')

@admin_bp.route('/dashboard')
@admin_login_required
def index():
    id_admin = session['admin_id']

    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT ip_address, ppp_username, ppp_password, username FROM admin WHERE id_admin = ?', (id_admin,))
    admin_data = dict(c.fetchone())

    mikrotik_status = 'offline'

    try:
        if admin_data['ppp_username']:
            ip = get_active_ppp_ip(admin_data['ppp_username'])
            logging.info(f"IP aktif untuk {admin_data['ppp_username']}: {ip}")

            if ip:
                mikrotik_status = 'online'
                if ip != admin_data['ip_address']:
                    c.execute('UPDATE admin SET ip_address = ? WHERE id_admin = ?', (ip, id_admin))
                    conn.commit()
                    admin_data['ip_address'] = ip
    except Exception as e:
        logging.warning(f"Gagal mendapatkan IP aktif: {e}")
        mikrotik_status = 'offline'

    conn.close()

    return render_template('billing.html', admin_data=admin_data, mikrotik_status=mikrotik_status)

@admin_bp.route('/generate-admin-data', methods=['POST'])
@admin_login_required
def generate_admin_data():
    conn = get_db()
    c = conn.cursor()

    c.execute('SELECT username FROM admin WHERE id_admin = ?', (session['admin_id'],))
    admin = c.fetchone()

    if not admin:
        flash('Admin tidak ditemukan.', 'error')
        conn.close()
        return redirect(url_for('admin.index'))

    username = admin['username']
    password = '1234'  # Default password untuk PPP user baru

    try:
        # Hapus secret & active PPP jika sudah ada
        if secret_exists(username):
            delete_secret(username)

        if active_exists(username):
            delete_active(username)

        # Buat ulang PPP user baru
        add_secret(
            name=username,
            password=password,
            profile='billing',
            service='l2tp',
            comment='Web Billing System'
        )

        # Simpan kredensial PPP ke database
        c.execute('''
            UPDATE admin
            SET ppp_username = ?, ppp_password = ?
            WHERE id_admin = ?
        ''', (username, password, session['admin_id']))
        conn.commit()

        flash('PPP user berhasil dibuat dan disimpan.', 'success')
        logging.info(f"PPP user {username} berhasil dibuat.")

    except Exception as e:
        flash('Terjadi kesalahan saat membuat PPP user.', 'error')
        logging.error(f"Gagal membuat PPP user: {e}")

    conn.close()
    return redirect(url_for('admin.index'))

@admin_bp.route('/trafik-data')
@admin_login_required
def trafik_data():
    try:
        id_admin = session['admin_id']
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM admin WHERE id_admin = ?", (id_admin,))
        admin = c.fetchone()

        if not admin:
            logging.warning("Admin tidak ditemukan saat akses trafik.")
            return jsonify({'error': 'Admin tidak ditemukan'}), 404

        api = connect_remote(admin['ip_address'], admin['ppp_username'], admin['ppp_password'])

        monitor_traffic = api.get_binary_resource('/interface').call(
            'monitor-traffic',
            {'interface': b'ether1', 'once': b' '}
        )

        tx_bps = int(monitor_traffic[0]['tx-bits-per-second'])
        rx_bps = int(monitor_traffic[0]['rx-bits-per-second'])

        return jsonify({
            'timestamp': datetime.now().strftime('%H:%M:%S'),
            'tx': round(tx_bps / 1_000_000, 2),  # Mbps
            'rx': round(rx_bps / 1_000_000, 2)
        })

    except Exception as e:
        logging.error(f"Kesalahan saat mengambil trafik data: {e}")
        return jsonify({'error': str(e)}), 500
 
@admin_bp.route('/petugas', methods=['GET'])
@admin_login_required
def tampilkan_petugas():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM petugas WHERE id_admin = ?", (session['admin_id'],))
    petugas_list = c.fetchall()
    conn.close()
    return render_template('petugas.html', petugas_list=petugas_list)

@admin_bp.route('/petugas/simpan', methods=['POST'])
@admin_login_required
def simpan_petugas():
    id_petugas = request.form.get('id_petugas')
    username = request.form.get('username')
    nama = request.form.get('nama')
    no_hp = normalize_nomor_hp(request.form.get('no_hp'))
    password = request.form.get('password')

    conn = get_db()
    c = conn.cursor()

    if id_petugas:
        # Edit (tanpa ubah password)
        try:
            c.execute("""
                UPDATE petugas
                SET username = ?, nama = ?, no_hp = ?
                WHERE id_petugas = ? AND id_admin = ?
            """, (username, nama, no_hp, id_petugas, session['admin_id']))
            conn.commit()
            flash("Petugas berhasil diperbarui.", "success")
        except Exception as e:
            flash(f"Gagal memperbarui petugas: {e}", "error")
    else:
        # Tambah baru
        try:
            password_hash = generate_password_hash(password)
            c.execute("""
                INSERT INTO petugas (username, password_hash, nama, no_hp, id_admin)
                VALUES (?, ?, ?, ?, ?)
            """, (username, password_hash, nama, no_hp, session['admin_id']))
            conn.commit()
            flash("Petugas berhasil ditambahkan.", "success")
        except Exception as e:
            flash(f"Gagal menambahkan petugas: {e}", "error")

    conn.close()
    return redirect(url_for('admin.tampilkan_petugas'))

@admin_bp.route('/petugas/hapus/<int:id>')
@admin_login_required
def hapus_petugas(id):
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("DELETE FROM petugas WHERE id_petugas = ? AND id_admin = ?", (id, session['admin_id']))
        conn.commit()
        flash("Petugas berhasil dihapus.", "success")
    except Exception as e:
        flash(f"Gagal menghapus petugas: {e}", "error")
    conn.close()
    return redirect(url_for('admin.tampilkan_petugas'))