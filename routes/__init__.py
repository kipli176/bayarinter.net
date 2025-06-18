from .auth_routes import auth_bp
from .admin_routes import admin_bp
from .pelanggan_routes import pelanggan_bp
from .tagihan_routes import tagihan_bp
from .petugas_routes import petugas_bp

def register_routes(app):
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(pelanggan_bp)
    app.register_blueprint(tagihan_bp)
    app.register_blueprint(petugas_bp)
