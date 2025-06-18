from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from db import get_db
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import random
import requests
import logging
from dotenv import load_dotenv
import os

auth_bp = Blueprint('auth', __name__)
logging.basicConfig(level=logging.INFO)
load_dotenv()

WA_API_URL = os.getenv("WA_API_URL")
WA_HEADERS = {"Content-Type": "application/json"}


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT * FROM admin WHERE username = ?', (username,))
        admin = c.fetchone()

        if not admin:
            flash('Akun tidak ditemukan.', 'error')
            return redirect(url_for('auth.login'))

        if not admin['is_active']:
            flash('Akun belum aktif. Silakan verifikasi OTP terlebih dahulu.', 'error')
            return redirect(url_for('auth.verifikasi', username=username))

        if not check_password_hash(admin['password_hash'], password):
            flash('Password salah.', 'error')
            return redirect(url_for('auth.login'))

        session['admin_id'] = admin['id_admin']
        session['admin_username'] = admin['username']

        c.execute(
            'UPDATE admin SET last_login = ? WHERE id_admin = ?',
            (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), admin['id_admin'])
        )
        conn.commit()
        conn.close()

        flash('Login berhasil.', 'success')
        logging.info(f"Login sukses: {username}")
        return redirect(url_for('admin.index'))

    return render_template('login.html')


@auth_bp.route('/logout')
def logout():
    username = session.get('admin_username', 'unknown')
    session.clear()
    flash('Berhasil logout.', 'info')
    logging.info(f"Logout oleh: {username}")
    return redirect(url_for('auth.login'))


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        no_hp = request.form['no_hp']
        nama = request.form['nama']
        alamat = request.form['alamat']

        otp = str(random.randint(100000, 999999))
        otp_expiry = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        message = f"Kode OTP Anda adalah: {otp}"

        try:
            requests.post(WA_API_URL, headers=WA_HEADERS, json={"number": no_hp, "message": message})
        except Exception as e:
            flash("Gagal mengirim OTP ke WhatsApp.", "error")
            logging.error(f"Gagal kirim OTP ke {no_hp}: {e}")
            return redirect(url_for('auth.register'))

        conn = get_db()
        c = conn.cursor()
        try:
            c.execute('''
                INSERT INTO admin (username, password_hash, no_hp, nama, alamat, is_active, otp_code, otp_expiry)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                username,
                generate_password_hash(password),
                no_hp,
                nama,
                alamat,
                0,  # is_active default
                otp,
                otp_expiry
            ))
            conn.commit()
            flash('Registrasi berhasil. Silakan verifikasi OTP.', 'success')
            logging.info(f"Registrasi berhasil: {username}")
            return redirect(url_for('auth.verifikasi', username=username))
        except Exception as e:
            flash('Registrasi gagal. Username mungkin sudah digunakan.', 'error')
            logging.error(f"Gagal registrasi {username}: {e}")
            return redirect(url_for('auth.register'))
        finally:
            conn.close()

    return render_template('register.html')

@auth_bp.route('/verifikasi', methods=['GET', 'POST'])
def verifikasi():
    username = request.args.get('username')

    if not username:
        flash('Username tidak ditemukan.', 'error')
        return redirect(url_for('auth.register'))

    if request.method == 'POST':
        otp_input = request.form['otp']

        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT * FROM admin WHERE username = ?', (username,))
        admin = c.fetchone()

        if not admin:
            flash('Akun tidak ditemukan.', 'error')
            return redirect(url_for('auth.register'))

        if admin['is_active'] == 1:
            flash('Akun sudah aktif. Silakan login.', 'info')
            return redirect(url_for('auth.login'))

        if admin['otp_code'] != otp_input:
            flash('Kode OTP salah.', 'error')
            return redirect(url_for('auth.verifikasi', username=username))

        # TODO: Tambahkan validasi waktu kedaluwarsa OTP (otp_expiry)

        c.execute('''
            UPDATE admin
            SET is_active = 1, otp_code = NULL, otp_expiry = NULL, last_login = ?
            WHERE username = ?
        ''', (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), username))
        conn.commit()
        conn.close()

        flash('Verifikasi berhasil! Akun Anda sudah aktif.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('verifikasi.html', username=username)

@auth_bp.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    if request.method == 'POST':
        no_hp = request.form['no_hp']

        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT * FROM admin WHERE no_hp = ?', (no_hp,))
        admin = c.fetchone()

        if not admin:
            flash('Nomor tidak terdaftar.', 'error')
            return redirect(url_for('auth.reset_password'))

        otp = str(random.randint(100000, 999999))
        otp_expiry = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        message = f"Kode OTP reset password Anda: {otp}"

        try:
            requests.post(WA_API_URL, headers=WA_HEADERS, json={"number": no_hp, "message": message})
        except Exception as e:
            logging.error(f"Gagal mengirim OTP ke WhatsApp: {e}")
            flash("Gagal mengirim OTP ke WhatsApp.", "error")
            return redirect(url_for('auth.reset_password'))

        c.execute('UPDATE admin SET otp_code = ?, otp_expiry = ? WHERE id_admin = ?', (otp, otp_expiry, admin['id_admin']))
        conn.commit()
        conn.close()

        flash('OTP dikirim ke WhatsApp. Masukkan OTP untuk lanjut.', 'success')
        return redirect(url_for('auth.reset_verify', no_hp=no_hp))

    return render_template('reset_password.html')

@auth_bp.route('/reset-password/verify', methods=['GET', 'POST'])
def reset_verify():
    no_hp = request.args.get('no_hp')

    if not no_hp:
        flash('Nomor HP tidak valid.', 'error')
        return redirect(url_for('auth.reset_password'))

    if request.method == 'POST':
        otp_input = request.form['otp']

        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT * FROM admin WHERE no_hp = ?', (no_hp,))
        admin = c.fetchone()

        if not admin or admin['otp_code'] != otp_input:
            flash('Kode OTP salah atau tidak ditemukan.', 'error')
            return redirect(url_for('auth.reset_verify', no_hp=no_hp))

        flash('OTP valid. Silakan buat password baru.', 'success')
        return redirect(url_for('auth.reset_new_password', no_hp=no_hp))

    return render_template('reset_verify.html', no_hp=no_hp)

@auth_bp.route('/reset-password/new', methods=['GET', 'POST'])
def reset_new_password():
    no_hp = request.args.get('no_hp')

    if request.method == 'POST':
        password = request.form['password']
        password_hash = generate_password_hash(password)

        conn = get_db()
        c = conn.cursor()
        c.execute('''
            UPDATE admin SET password_hash = ?, otp_code = NULL, otp_expiry = NULL
            WHERE no_hp = ?
        ''', (password_hash, no_hp))
        conn.commit()
        conn.close()

        flash('Password berhasil diganti. Silakan login.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('reset_new_password.html', no_hp=no_hp)

