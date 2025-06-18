from routeros_api import RouterOsApiPool
from routeros_api.exceptions import RouterOsApiConnectionError
from dotenv import load_dotenv
import os

load_dotenv()

MIKROTIK_HOST = os.getenv("MIKROTIK_HOST")
MIKROTIK_USER = os.getenv("MIKROTIK_USER")
MIKROTIK_PASS = os.getenv("MIKROTIK_PASS")
MIKROTIK_PORT = int(os.getenv("MIKROTIK_PORT", 8728))


# Koneksi Mikrotik
def connect():
    try:
        api_pool = RouterOsApiPool(
            MIKROTIK_HOST,
            username=MIKROTIK_USER,
            password=MIKROTIK_PASS,
            port=MIKROTIK_PORT,
            plaintext_login=True
        )
        return api_pool.get_api()
    except RouterOsApiConnectionError as e:
        raise Exception(f"Koneksi gagal: {e}")

# Cek apakah pool sudah ada
def pool_exists(name):
    api = connect()
    pools = api.get_resource('/ip/pool')
    return any(p['name'] == name for p in pools.get())

# Tambahkan pool baru
def add_pool(name, address_range):
    api = connect()
    pools = api.get_resource('/ip/pool')
    pools.add(name=name, ranges=address_range)

def get_active_ppp_ip(username):
    api = connect()
    ppp_active = api.get_resource('/ppp/active')
    data = ppp_active.get(name=username)
    if data:
        return data[0].get('address')
    return None

# Tambahkan PPP Secret (user)
def add_secret(name, password='1234', comment='Billing', profile='billing', service='l2tp'):
    api = connect()
    ppp = api.get_resource('/ppp/secret')
    
    # Cek apakah sudah ada user PPP dengan nama tersebut
    existing = ppp.get(name=name)
    if existing:
        raise Exception(f"PPP user '{name}' sudah ada di Mikrotik.")
    
    ppp.add(
        name=name,
        password=password,
        service=service,
        profile=profile,
        comment=comment
    )

def secret_exists(username):
    api = connect()
    ppp = api.get_resource('/ppp/secret')
    return bool(ppp.get(name=username))

def delete_secret(username):
    api = connect()
    ppp = api.get_resource('/ppp/secret')
    secrets = ppp.get(name=username)
    for s in secrets:
        id_key = s.get('.id') or s.get('id')
        if id_key:
            ppp.remove(id=id_key)

def generate_rate_limit(speed_mbps):
    burst_limit = speed_mbps * 2
    burst_threshold = speed_mbps
    burst_time = 8
    return f"{speed_mbps}M/{speed_mbps}M {burst_limit}M/{burst_limit}M {burst_threshold}M/{burst_threshold}M {burst_time}/{burst_time} 1/1"
 
def add_profile(name, local_address='10.168.0.1', remote_address='billing', speed_mbps=5):
    api = connect()
    profile = api.get_resource('/ppp/profile')
    rate_limit = generate_rate_limit(speed_mbps)
    
    profile.add(
        name=name,
        local_address=local_address,
        remote_address=remote_address,
        rate_limit=rate_limit
    )

def profile_exists(name):
    api = connect()
    profile = api.get_resource('/ppp/profile')
    return any(p['name'] == name for p in profile.get())

def delete_profile(name):
    api = connect()
    profile = api.get_resource('/ppp/profile')
    profiles = profile.get(name=name)
    for p in profiles:
        id_key = p.get('.id') or p.get('id')
        if id_key:
            profile.remove(id=id_key)
            
def active_exists(username):
    api = connect()
    active = api.get_resource('/ppp/active')
    return bool(active.get(name=username))

def delete_active(username):
    api = connect()
    active = api.get_resource('/ppp/active')
    sessions = active.get(name=username)
    for session in sessions:
        id_key = session.get('.id') or session.get('id')
        if id_key:
            active.remove(id=id_key)

def connect_remote(ip, username, password):
    from routeros_api import RouterOsApiPool
    from routeros_api.exceptions import RouterOsApiConnectionError

    try:
        api_pool = RouterOsApiPool(
            ip,
            username=username,
            password=password,
            plaintext_login=True
        )
        return api_pool.get_api()
    except RouterOsApiConnectionError as e:
        raise Exception(f"Gagal koneksi ke Mikrotik {ip}: {e}")
    
# Tambahkan PPP Secret pada Mikrotik remote
def add_secret_remote(api, name, password='1234', comment='Billing', profile='billing', service='l2tp'):
    ppp = api.get_resource('/ppp/secret')
    existing = ppp.get(name=name)
    if existing:
        raise Exception(f"PPP user '{name}' sudah ada di Mikrotik.")
    ppp.add(
        name=name,
        password=password,
        service=service,
        profile=profile,
        comment=comment
    )

# Hapus PPP Secret dari Mikrotik remote
def delete_secret_remote(api, username):
    ppp = api.get_resource('/ppp/secret')
    secrets = ppp.get(name=username)
    for s in secrets:
        id_key = s.get('.id') or s.get('id')
        if id_key:
            ppp.remove(id=id_key)

# Ambil daftar profil dari Mikrotik remote
def get_profiles_remote(api):
    ppp_profile = api.get_resource('/ppp/profile')
    return [p['name'] for p in ppp_profile.get()]

def active_exists_remote(api, username):
    active = api.get_resource('/ppp/active')
    return bool(active.get(name=username))

def check_active_bulk(api, username_list):
    result = {}
    try:
        active = api.get_resource('/ppp/active')
        active_list = active.get() 
        active_names = set()

        for entry in active_list:
            # Tangani berbagai kemungkinan key
            uname = entry.get('name') or entry.get('user') or entry.get('username')
            if uname:
                active_names.add(uname.strip().lower())

        for u in username_list:
            result[u] = 'online' if u.strip().lower() in active_names else 'offline'

    except Exception as e:
        print("Mikrotik error:", e)
        result = {u: 'offline' for u in username_list}

    return result


def update_admin_ip(admin_data, id_admin, db_conn):
    """
    Cek status Mikrotik dan update IP admin jika berubah.
    """
    mikrotik_status = 'offline'
    try:
        if admin_data['ppp_username']:
            ip = get_active_ppp_ip(admin_data['ppp_username'])
            if ip:
                mikrotik_status = 'online'
                if ip != admin_data['ip_address']:
                    c = db_conn.cursor()
                    c.execute(
                        'UPDATE admin SET ip_address = ? WHERE id_admin = ?',
                        (ip, id_admin)
                    )
                    db_conn.commit()
                    admin_data['ip_address'] = ip
            else:
                mikrotik_status = 'offline'
    except Exception:
        mikrotik_status = 'offline'
    return mikrotik_status, admin_data

def regenerate_ppp_user(username, password='1234'):
    """
    Menghapus dan membuat ulang user PPP di Mikrotik.
    """
    if secret_exists(username):
        delete_secret(username)
    if active_exists(username):
        delete_active(username)
    add_secret(
        name=username,
        password=password,
        profile='billing',
        service='l2tp',
        comment='Web Billing System'
    )
