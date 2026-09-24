from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
import os

# Import Blueprint rute
from routes.auth_routes import auth_bp
from routes.absen_routes import absen_bp
from routes.admin_routes import admin_bp

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

UPLOAD_FOLDER = 'uploads/'
DATASET_FOLDER = os.path.join(UPLOAD_FOLDER, 'dataset')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(DATASET_FOLDER, exist_ok=True)
os.makedirs(os.path.join(UPLOAD_FOLDER, 'izin'), exist_ok=True)


# Daftarkan Blueprint dengan url_prefix
app.register_blueprint(auth_bp, url_prefix='/api')
app.register_blueprint(absen_bp, url_prefix='/api')
app.register_blueprint(admin_bp, url_prefix='/api')

# Rute agar file upload (termasuk surat izin/sakit) bisa diakses via URL browser
@app.route('/uploads/<path:filename>', methods=['GET'])
def serve_uploads(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

@app.route('/', methods=['GET'])
def index():
    return jsonify({"message": "API Presensi LBPH Aktif & Modular"}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)