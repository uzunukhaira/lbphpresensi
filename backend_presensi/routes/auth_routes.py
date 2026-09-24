from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from database import get_connection, release_connection

auth_bp = Blueprint('auth_bp', __name__)

@auth_bp.route('/login', methods=['POST'])
def login_mahasiswa():
    nim = request.form.get('nim')
    password = request.form.get('password')

    if not nim or not password:
        return jsonify({"status": "error", "message": "NIM dan Password wajib diisi!"}), 400

    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT nim, nama_lengkap, password, wajah_terdaftar FROM mahasiswa WHERE nim = %s", 
            (nim,)
        )
        row = cursor.fetchone()
        cursor.close()
        release_connection(conn)

        if not row:
            return jsonify({"status": "error", "message": "NIM tidak terdaftar di sistem!"}), 404

        db_nim, nama_mhs, db_hashed_password, wajah_terdaftar = row[0], row[1], row[2], row[3] or False

        if not db_hashed_password or not check_password_hash(db_hashed_password, password):
            return jsonify({"status": "error", "message": "Password salah!"}), 401

        return jsonify({
            "status": "success",
            "message": "Login Berhasil!",
            "data": {
                "nim": db_nim,
                "nama": nama_mhs,
                "wajah_terdaftar": wajah_terdaftar
            }
        }), 200

    except Exception as e:
        return jsonify({"status": "error", "message": f"Terjadi kesalahan server: {str(e)}"}), 500



@auth_bp.route('/reset-password', methods=['POST'])
def reset_password():
    nim = request.form.get('nim')
    new_password = request.form.get('new_password')

    if not nim or not new_password:
        return jsonify({"status": "error", "message": "NIM dan Password Baru wajib diisi!"}), 400

    hashed_password = generate_password_hash(new_password)

    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT nim FROM mahasiswa WHERE nim = %s", (nim,))
        if not cursor.fetchone():
            cursor.close()
            release_connection(conn)
            return jsonify({"status": "error", "message": "NIM tidak ditemukan di database!"}), 404

        cursor.execute("UPDATE mahasiswa SET password = %s WHERE nim = %s", (hashed_password, nim))
        conn.commit()
        cursor.close()
        release_connection(conn)

        return jsonify({"status": "success", "message": "Password berhasil direset! Silakan login."}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": f"Terjadi kesalahan server: {str(e)}"}), 500


@auth_bp.route('/register-akun', methods=['POST'])
def register_akun():
    nim = request.form.get('nim')
    nama = request.form.get('nama')
    password = request.form.get('password')

    if not nim or not nama or not password:
        return jsonify({"status": "error", "message": "Data tidak lengkap!"}), 400

    hashed_password = generate_password_hash(password)

    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO mahasiswa (nim, nama_lengkap, password, wajah_terdaftar)
            VALUES (%s, %s, %s, FALSE)
            ON CONFLICT (nim) DO UPDATE 
            SET password = EXCLUDED.password, nama_lengkap = EXCLUDED.nama_lengkap
            """,
            (nim, nama, hashed_password)
        )
        conn.commit()
        cursor.close()
        release_connection(conn)

        return jsonify({"status": "success", "message": "Akun mahasiswa berhasil didaftarkan!"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500