import os
import subprocess
from flask import Flask
from routes import register_routes
from dotenv import load_dotenv

app = Flask(__name__) 
load_dotenv()
app.secret_key = os.getenv("SECRET_KEY", "fallback-secret")

# Inisialisasi database jika belum ada
if not os.path.exists('langganan.sqlite3'):
    print('[INFO] Database belum ditemukan. Menjalankan billing-init.py ...')
    subprocess.run(['python', 'billing-init.py'], check=True)

# Daftarkan semua blueprint
register_routes(app)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)  # 👈 akses dari luar
