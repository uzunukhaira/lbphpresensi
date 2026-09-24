from io import StringIO
import csv
from flask import Blueprint, Response, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from database import get_connection, release_connection

admin_bp = Blueprint('admin_bp', __name__)

@admin_bp.route('/admin/presensi', methods=['GET'])
def get_admin_presensi():
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # PERBAIKAN: Melakukan JOIN lengkap ke tabel kelas, jadwal, dan matakuliah
        cursor.execute("""
            SELECT p.id_presensi, p.nim, m.nama_lengkap, k.nama_kelas, mk.nama_mk, p.status_absen, p.tanggal, p.waktu_absen 
            FROM presensi p
            JOIN mahasiswa m ON p.nim = m.nim
            LEFT JOIN kelas k ON m.id_kelas = k.id_kelas
            LEFT JOIN jadwal_kuliah jk ON p.id_jadwal = jk.id_jadwal
            LEFT JOIN matakuliah mk ON jk.id_mk = mk.id_mk
            ORDER BY p.tanggal DESC, p.waktu_absen DESC LIMIT 50
        """)
        
        rows = cursor.fetchall()
        rekap_list = []
        for r in rows:
            # Menggabungkan tanggal dan waktu dengan aman
            tgl_str = str(r[6]) if r[6] else ""
            waktu_str = str(r[7]) if r[7] else ""
            waktu_gabung = f"{tgl_str} {waktu_str}".strip()

            rekap_list.append({
                "id": r[0], 
                "nim": r[1], 
                "nama": r[2], 
                "nama_kelas": r[3] if r[3] else "-", # Nama Kelas
                "mata_kuliah": r[4] if r[4] else "Tidak Diketahui", # Mata Kuliah
                "status": r[5],
                "waktu": waktu_gabung if waktu_gabung else "-"
            })
            
        cursor.close()
        release_connection(conn)
        return jsonify({"status": "success", "data": rekap_list}), 200
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@admin_bp.route('/admin/mahasiswa', methods=['GET'])
def admin_get_mahasiswa():
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # PERBAIKAN: JOIN ke tabel kelas agar nama_kelas dan id_kelas bisa tampil di web
        cursor.execute("""
            SELECT m.nim, m.nama_lengkap, m.wajah_terdaftar, m.id_kelas, k.nama_kelas 
            FROM mahasiswa m 
            LEFT JOIN kelas k ON m.id_kelas = k.id_kelas 
            ORDER BY m.nim ASC
        """)
        
        rows = cursor.fetchall()
        cursor.close()
        release_connection(conn)
        
        data = [{
            "nim": r[0], 
            "nama": r[1], 
            "wajah_terdaftar": r[2],
            "id_kelas": r[3],
            "nama_kelas": r[4]
        } for r in rows]
        
        return jsonify({"status": "success", "data": data}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@admin_bp.route('/admin/mahasiswa/<nim>', methods=['PUT'])
def admin_edit_mahasiswa(nim):
    nama = request.form.get('nama')
    id_kelas = request.form.get('id_kelas')
    password = request.form.get('password')

    if not nama or not id_kelas:
        return jsonify({"status": "error", "message": "Nama dan Kelas wajib diisi!"}), 400

    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Logika: Jika admin mengetik password baru, update passwordnya
        if password and password.strip() != "":
            hashed_pw = generate_password_hash(password)
            cursor.execute("""
                UPDATE mahasiswa 
                SET nama_lengkap = %s, id_kelas = %s, password = %s 
                WHERE nim = %s
            """, (nama, id_kelas, hashed_pw, nim))
        # Jika password di form kosong, jangan ubah password di database
        else:
            cursor.execute("""
                UPDATE mahasiswa 
                SET nama_lengkap = %s, id_kelas = %s 
                WHERE nim = %s
            """, (nama, id_kelas, nim))

        conn.commit()
        cursor.close()
        release_connection(conn)

        return jsonify({"status": "success", "message": f"Data Mahasiswa {nim} berhasil diperbarui!"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@admin_bp.route('/admin/mahasiswa/<nim>', methods=['DELETE'])
def admin_delete_mahasiswa(nim):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM mahasiswa WHERE nim = %s", (nim,))
        conn.commit()
        cursor.close()
        release_connection(conn)
        return jsonify({"status": "success", "message": f"Mahasiswa {nim} berhasil dihapus!"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@admin_bp.route('/admin/master-data', methods=['GET'])
def get_master_data():
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id_kelas, nama_kelas FROM kelas")
        kelas = [{"id": r[0], "nama": r[1]} for r in cursor.fetchall()]
        cursor.execute("SELECT id_dosen, nama_dosen FROM dosen")
        dosen = [{"id": r[0], "nama": r[1]} for r in cursor.fetchall()]
        cursor.execute("SELECT id_mk, nama_mk FROM matakuliah")
        matkul = [{"id": r[0], "nama": r[1]} for r in cursor.fetchall()]
        cursor.execute("SELECT id_ruangan, nama_ruangan FROM ruangan")
        ruangan = [{"id": r[0], "nama": r[1]} for r in cursor.fetchall()]
        cursor.close()
        release_connection(conn)
        return jsonify({"status": "success", "data": {"kelas": kelas, "dosen": dosen, "matkul": matkul, "ruangan": ruangan}}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@admin_bp.route('/admin/kelas', methods=['GET'])
def admin_get_kelas():
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id_kelas, nama_kelas FROM kelas ORDER BY nama_kelas ASC")
        rows = cursor.fetchall()
        cursor.close()
        release_connection(conn)
        
        data = [{"id_kelas": r[0], "nama_kelas": r[1]} for r in rows]
        return jsonify({"status": "success", "data": data}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@admin_bp.route('/admin/jadwal', methods=['GET', 'POST'])
def kelola_jadwal():
    try:
        conn = get_connection()
        cursor = conn.cursor()
        if request.method == 'GET':
            query = """
                SELECT j.id_jadwal, m.nama_mk, d.nama_dosen, k.nama_kelas, r.nama_ruangan, 
                       j.hari, j.jam_mulai, j.jam_selesai, j.tahun_akademik, j.semester
                FROM jadwal_kuliah j
                JOIN matakuliah m ON j.id_mk = m.id_mk
                JOIN dosen d ON j.id_dosen = d.id_dosen
                JOIN kelas k ON j.id_kelas = k.id_kelas
                LEFT JOIN ruangan r ON j.id_ruangan = r.id_ruangan
                ORDER BY j.hari, j.jam_mulai
            """
            cursor.execute(query)
            rows = cursor.fetchall()
            hasil = [{
                "id_jadwal": r[0], "nama_mk": r[1], "nama_dosen": r[2], "nama_kelas": r[3],
                "nama_ruangan": r[4], "hari": r[5], "jam_mulai": str(r[6]), "jam_selesai": str(r[7]),
                "tahun_akademik": r[8], "semester": r[9]
            } for r in rows]
            cursor.close()
            release_connection(conn)
            return jsonify({"status": "success", "data": hasil}), 200

        elif request.method == 'POST':
            data = request.json
            id_mk = data.get('id_mk')
            id_dosen = data.get('id_dosen')
            id_kelas = data.get('id_kelas')
            id_ruangan = data.get('id_ruangan')
            hari = data.get('hari')
            jam_mulai = data.get('jam_mulai')
            jam_selesai = data.get('jam_selesai')
            tahun_akademik = data.get('tahun_akademik', '2023/2024')
            semester = data.get('semester', 'Genap')

            if not all([id_mk, id_dosen, id_kelas, hari, jam_mulai, jam_selesai]):
                return jsonify({"status": "error", "message": "Semua kolom wajib diisi!"}), 400

            cursor.execute("""
                INSERT INTO jadwal_kuliah (id_mk, id_dosen, id_kelas, id_ruangan, hari, jam_mulai, jam_selesai, tahun_akademik, semester)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (int(id_mk), int(id_dosen), int(id_kelas), int(id_ruangan) if id_ruangan else None, hari, jam_mulai, jam_selesai, tahun_akademik, semester))
            
            conn.commit()
            cursor.close()
            release_connection(conn)
            return jsonify({"status": "success", "message": "Jadwal berhasil ditambahkan"}), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@admin_bp.route('/admin/jadwal/<int:id_jadwal>', methods=['DELETE'])
def admin_delete_jadwal(id_jadwal):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM jadwal_kuliah WHERE id_jadwal = %s", (id_jadwal,))
        conn.commit()
        cursor.close()
        release_connection(conn)
        return jsonify({"status": "success", "message": "Jadwal berhasil dihapus!"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@admin_bp.route('/admin/login', methods=['POST'])
def admin_login():
    data = request.json or {}
    username, password = data.get('username'), data.get('password')
    if not username or not password:
        return jsonify({"status": "error", "message": "Username dan Password wajib diisi!"}), 400

    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id_admin, username, nama_admin, password FROM admin WHERE username = %s", (username,))
        row = cursor.fetchone()
        cursor.close()
        release_connection(conn)

        if not row or not check_password_hash(row[3], password):
            return jsonify({"status": "error", "message": "Username atau Password Admin salah!"}), 401

        return jsonify({
            "status": "success", "message": f"Welcome, {row[2]}!",
            "token": f"admin-session-{row[0]}",
            "data": {"id": row[0], "username": row[1], "nama": row[2]}
        }), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@admin_bp.route('/admin/register', methods=['POST'])
def admin_register():
    data = request.json or {}
    username, nama, password = data.get('username'), data.get('nama'), data.get('password')
    if not username or not nama or not password:
        return jsonify({"status": "error", "message": "Semua data wajib diisi!"}), 400

    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO admin (username, nama_admin, password) VALUES (%s, %s, %s) ON CONFLICT (username) DO UPDATE SET password = EXCLUDED.password, nama_admin = EXCLUDED.nama_admin",
            (username, nama, generate_password_hash(password))
        )
        conn.commit()
        cursor.close()
        release_connection(conn)
        return jsonify({"status": "success", "message": f"Admin '{username}' berhasil disimpan!"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@admin_bp.route('/admin/export/rekap', methods=['GET'])
def export_rekap_kelas():
    id_kelas = request.args.get('id_kelas')
    id_jadwal = request.args.get('id_jadwal')

    if not id_kelas or not id_jadwal:
        return jsonify({"status": "error", "message": "Parameter id_kelas dan id_jadwal wajib diisi"}), 400

    try:
        conn = get_connection()
        cursor = conn.cursor()

        # 1. Ambil info Mata Kuliah dan Kelas untuk nama file
        cursor.execute("""
            SELECT mk.nama_mk, k.nama_kelas 
            FROM jadwal_kuliah jk
            JOIN matakuliah mk ON jk.id_mk = mk.id_mk
            JOIN kelas k ON k.id_kelas = %s
            WHERE jk.id_jadwal = %s
        """, (id_kelas, id_jadwal))
        info = cursor.fetchone()
        
        if not info:
            return jsonify({"status": "error", "message": "Jadwal atau Kelas tidak ditemukan"}), 404
            
        nama_mk, nama_kelas = info

        # 2. PERBAIKAN: Menggunakan m.nama_lengkap sesuai kolom di database Anda
        query = """
            SELECT m.nim, m.nama_lengkap,
                   COUNT(CASE WHEN p.status_absen IN ('Hadir', 'Terlambat') THEN 1 END) as hadir,
                   COUNT(CASE WHEN p.status_absen IN ('Izin', 'Sakit') THEN 1 END) as izin,
                   COUNT(CASE WHEN p.status_absen = 'Alpha' THEN 1 END) as alpha
            FROM mahasiswa m
            JOIN jadwal_kuliah jk ON jk.id_jadwal = %s
            LEFT JOIN presensi p ON m.nim = p.nim AND p.id_jadwal = jk.id_jadwal
            WHERE m.id_kelas = %s
            GROUP BY m.nim, m.nama_lengkap
            ORDER BY m.nim ASC
        """
        cursor.execute(query, (id_jadwal, id_kelas))
        rows = cursor.fetchall()

        # 3. Buat file CSV di dalam memori
        output = StringIO()
        writer = csv.writer(output, delimiter=',')

        # Tulis Header Kolom Excel
        writer.writerow(['NIM', 'Nama Mahasiswa', 'Mata Kuliah', 'Kelas', 'Hadir/Terlambat', 'Izin/Sakit', 'Alpha', 'Total Pertemuan', 'Persentase (%)'])

        # Tulis Data Baris per Baris
        for r in rows:
            nim, nama, hadir, izin, alpha = r
            total_berjalan = hadir + izin + alpha
            persentase = round((hadir + izin) / total_berjalan * 100, 2) if total_berjalan > 0 else 0

            writer.writerow([nim, nama, nama_mk, nama_kelas, hadir, izin, alpha, total_berjalan, f"{persentase}%"])

        cursor.close()
        release_connection(conn)

        # 4. Kirim sebagai file CSV yang bisa didownload
        output.seek(0)
        nama_file = f"Rekap_{nama_kelas}_{nama_mk.replace(' ', '_')}.csv"
        
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment;filename={nama_file}"}
        )

    except Exception as e:
        return jsonify({"status": "error", "message": f"Gagal Export: {str(e)}"}), 500

@admin_bp.route('/admin/rekap-tabel', methods=['GET'])
def get_rekap_tabel_json():
    id_kelas = request.args.get('id_kelas')
    id_jadwal = request.args.get('id_jadwal')

    if not id_kelas or not id_jadwal:
        return jsonify({"status": "error", "message": "Parameter id_kelas dan id_jadwal wajib diisi"}), 400

    try:
        conn = get_connection()
        cursor = conn.cursor()

        query = """
            SELECT m.nim, m.nama_lengkap,
                   COUNT(CASE WHEN p.status_absen IN ('Hadir', 'Terlambat') THEN 1 END) as hadir,
                   COUNT(CASE WHEN p.status_absen IN ('Izin', 'Sakit') THEN 1 END) as izin,
                   COUNT(CASE WHEN p.status_absen = 'Alpha' THEN 1 END) as alpha
            FROM mahasiswa m
            JOIN jadwal_kuliah jk ON jk.id_jadwal = %s
            LEFT JOIN presensi p ON m.nim = p.nim AND p.id_jadwal = jk.id_jadwal
            WHERE m.id_kelas = %s
            GROUP BY m.nim, m.nama_lengkap
            ORDER BY m.nim ASC
        """
        cursor.execute(query, (id_jadwal, id_kelas))
        rows = cursor.fetchall()

        hasil = []
        for r in rows:
            nim, nama, hadir, izin, alpha = r
            total_berjalan = hadir + izin + alpha
            persentase = round((hadir + izin) / total_berjalan * 100, 2) if total_berjalan > 0 else 0

            hasil.append({
                "nim": nim,
                "nama": nama,
                "hadir": hadir,
                "izin": izin,
                "alpha": alpha,
                "total_pertemuan": total_berjalan,
                "persentase": persentase
            })

        cursor.close()
        release_connection(conn)
        return jsonify({"status": "success", "data": hasil}), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@admin_bp.route('/admin/rekap-tabel-umum', methods=['GET'])
def get_rekap_tabel_umum_json():
    id_kelas = request.args.get('id_kelas')
    if not id_kelas:
        return jsonify({"status": "error", "message": "Parameter id_kelas wajib diisi"}), 400

    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Menggunakan m.nama_lengkap dan LEFT JOIN yang aman
        query = """
            SELECT m.nim, m.nama_lengkap,
                   COUNT(CASE WHEN p.status_absen = 'Hadir' THEN 1 END) as hadir,
                   COUNT(CASE WHEN p.status_absen = 'Izin' THEN 1 END) as izin,
                   COUNT(CASE WHEN p.status_absen = 'Sakit' THEN 1 END) as sakit,
                   COUNT(CASE WHEN p.status_absen = 'Alpha' THEN 1 END) as alpha
            FROM mahasiswa m
            LEFT JOIN presensi p ON m.nim = p.nim
            WHERE m.id_kelas = %s
            GROUP BY m.nim, m.nama_lengkap
            ORDER BY m.nim ASC
        """
        cursor.execute(query, (id_kelas,))
        rows = cursor.fetchall()

        hasil = []
        for r in rows:
            nim, nama, hadir, izin, sakit, alpha = r
            hasil.append({
                "nim": nim,
                "nama": nama,
                "hadir": hadir or 0,
                "izin": izin or 0,
                "sakit": sakit or 0,
                "alpha": alpha or 0
            })

        cursor.close()
        release_connection(conn)
        return jsonify({"status": "success", "data": hasil}), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# 2. API Download Excel Rekap Umum Per Kelas
@admin_bp.route('/admin/export/rekap-umum', methods=['GET'])
def export_rekap_umum():
    id_kelas = request.args.get('id_kelas')

    if not id_kelas:
        return jsonify({"status": "error", "message": "Parameter id_kelas wajib diisi"}), 400

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT nama_kelas FROM kelas WHERE id_kelas = %s", (id_kelas,))
        kelas_row = cursor.fetchone()
        
        if not kelas_row:
            return jsonify({"status": "error", "message": "Kelas tidak ditemukan"}), 404
            
        nama_kelas = kelas_row[0]

        query = """
            SELECT m.nim, m.nama_lengkap,
                   COUNT(CASE WHEN p.status_absen = 'Hadir' THEN 1 END) as hadir,
                   COUNT(CASE WHEN p.status_absen = 'Izin' THEN 1 END) as izin,
                   COUNT(CASE WHEN p.status_absen = 'Sakit' THEN 1 END) as sakit,
                   COUNT(CASE WHEN p.status_absen = 'Alpha' THEN 1 END) as alpha
            FROM mahasiswa m
            LEFT JOIN presensi p ON m.nim = p.nim
            WHERE m.id_kelas = %s
            GROUP BY m.nim, m.nama_lengkap
            ORDER BY m.nim ASC
        """
        cursor.execute(query, (id_kelas,))
        rows = cursor.fetchall()

        output = StringIO()
        writer = csv.writer(output, delimiter=',')

        writer.writerow(['NIM / BP', 'Nama Mahasiswa', 'Hadir', 'Izin', 'Sakit', 'Alpha'])

        for r in rows:
            nim, nama, hadir, izin, sakit, alpha = r
            writer.writerow([nim, nama, hadir or 0, izin or 0, sakit or 0, alpha or 0])

        cursor.close()
        release_connection(conn)

        output.seek(0)
        nama_file = f"Rekap_Umum_Kelas_{nama_kelas}.csv"
        
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment;filename={nama_file}"}
        )

    except Exception as e:
        return jsonify({"status": "error", "message": f"Gagal Export: {str(e)}</em>"}), 500

@admin_bp.route('/admin/izin', methods=['GET'])
def get_admin_izin():
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Ambil data presensi yang statusnya Izin atau Sakit
        cursor.execute("""
            SELECT p.id_presensi, p.nim, m.nama_lengkap, mk.nama_mk, p.status_absen, p.bukti_izin, p.waktu_absen 
            FROM presensi p
            JOIN mahasiswa m ON p.nim = m.nim
            LEFT JOIN jadwal_kuliah jk ON p.id_jadwal = jk.id_jadwal
            LEFT JOIN matakuliah mk ON jk.id_mk = mk.id_mk
            WHERE p.status_absen IN ('Izin', 'Sakit')
            ORDER BY p.waktu_absen DESC
        """)
        rows = cursor.fetchall()
        
        izin_list = []
        for r in rows:
            izin_list.append({
                "id": r[0],
                "nim": r[1],
                "nama": r[2],
                "mata_kuliah": r[3] if r[3] else "-",
                "status": r[4],
                "bukti_url": r[5], # Path file surat di server
                "waktu": r[6].strftime("%d-%m-%Y %H:%M:%S") if r[6] else "-"
            })
            
        cursor.close()
        release_connection(conn)
        return jsonify({"status": "success", "data": izin_list}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500