import os
import math
import cv2
import json
import numpy as np
import pytesseract
from PIL import Image
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from scipy import io
from werkzeug.utils import secure_filename
from database import get_connection, release_connection
from supabase import create_client, Client
import io
import requests
import pytesseract

# uji windows
# pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'


absen_bp = Blueprint('absen_bp', __name__)

# Konfigurasi Supabase Client
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

UPLOAD_FOLDER = 'uploads/'
DATASET_FOLDER = os.path.join(UPLOAD_FOLDER, 'dataset')
MODEL_PATH = os.path.join(UPLOAD_FOLDER, 'trainer.yml')
LABEL_MAP_PATH = os.path.join(UPLOAD_FOLDER, 'label_map.json')

# Path otomatis membaca file xml di dalam folder yang sama (folder routes)
casc_path = os.path.join(os.path.dirname(__file__), 'haarcascade_frontalface_default.xml')
face_cascade = cv2.CascadeClassifier(casc_path)
recognizer = cv2.face.LBPHFaceRecognizer_create()

# Koordinat Kampus PNP
# KAMPUS_LAT = -0.9341269661649044
# KAMPUS_LON = 100.4466865
KAMPUS_LAT = -0.4573568217480942
KAMPUS_LON = 100.48078793526156
MAX_RADIUS_METER = 195550.0


def hitung_jarak_haversine(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def sync_model_dari_supabase():
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    try:
        if not os.path.exists(MODEL_PATH):
            print("[INFO] Mengunduh trainer.yml dari Supabase...")
            model_bytes = supabase.storage.from_("model-lbph").download("trainer.yml")
            with open(MODEL_PATH, 'wb') as f:
                f.write(model_bytes)
                
        if not os.path.exists(LABEL_MAP_PATH):
            label_bytes = supabase.storage.from_("model-lbph").download("label_map.json")
            with open(LABEL_MAP_PATH, 'wb') as f:
                f.write(label_bytes)
    except Exception as e:
        print(f"[WARNING] File model belum ada di Supabase atau gagal unduh: {e}")

# ==========================================
# 1. API ABSEN WAJAH LBPH (DENGAN ATURAN WAKTU BARU)
# ==========================================
@absen_bp.route('/absen', methods=['POST'])
def absen_mahasiswa():
    nim = request.form.get('nim')
    id_jadwal = request.form.get('id_jadwal')
    lat_str = request.form.get('latitude')
    lon_str = request.form.get('longitude')

    if not nim or not lat_str or not lon_str or not id_jadwal:
        return jsonify({"status": "error", "message": "Data tidak lengkap"}), 400

    try:
        user_lat, user_lon = float(lat_str), float(lon_str)
    except ValueError:
        return jsonify({"status": "error", "message": "Format koordinat tidak valid"}), 400

    jarak_mahasiswa = round(hitung_jarak_haversine(KAMPUS_LAT, KAMPUS_LON, user_lat, user_lon), 2)
    if jarak_mahasiswa > MAX_RADIUS_METER:
        return jsonify({"status": "error", "message": f"Anda di luar jangkauan kampus. Jarak: {jarak_mahasiswa}m"}), 403

    if 'foto' not in request.files:
        return jsonify({"status": "error", "message": "File foto tidak ditemukan"}), 400

    # Membaca foto langsung ke memori (tanpa simpan ke lokal)
    file = request.files['foto']
    file_bytes = file.read()
    
    # 1. Pastikan file model YML ada (jika hilang, otomatis download dari Supabase)
    sync_model_dari_supabase()
    if not os.path.exists(MODEL_PATH):
        return jsonify({"status": "error", "message": "Model wajah belum tersedia! Hubungi Admin untuk melakukan Train Data."}), 500

    # 2. Proses Pengenalan Wajah Langsung dari Memori
    recognizer.read(MODEL_PATH)
    nparr = np.frombuffer(file_bytes, np.uint8)
    img_absen = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    gray = cv2.cvtColor(img_absen, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(100, 100))

    if len(faces) == 0:
        return jsonify({"status": "error", "message": "Wajah tidak terdeteksi di kamera!"}), 400

    (x, y, w, h) = faces[0]
    wajah_resize = cv2.resize(gray[y:y+h, x:x+w], (200, 200))
    id_angka, confidence = recognizer.predict(wajah_resize)
    
    nilai_confidence = float(round(float(confidence), 2))
    THRESHOLD = 50.0

    if confidence < THRESHOLD:
        # 3. Wajah Valid -> Upload Foto Bukti Presensi ke Supabase
        filename = f"absen_{nim}_{int(datetime.now().timestamp())}.jpg"
        try:
            supabase.storage.from_("foto-presensi").upload(
                file=file_bytes, path=filename, file_options={"content-type": "image/jpeg"}
            )
            public_url = supabase.storage.from_("foto-presensi").get_public_url(filename)
        except Exception as e:
            print(f"[ERROR UPLOAD] {e}")
            return jsonify({"status": "error", "message": f"Gagal upload foto absen ke cloud: {e}"}), 500

        # 4. Pencatatan ke Database PostgreSQL
        try:
            conn = get_connection()
            cursor = conn.cursor()
            
            cursor.execute("SELECT nim FROM mahasiswa WHERE nim = %s", (nim,))
            if not cursor.fetchone():
                return jsonify({"status": "error", "message": "NIM tidak terdaftar!"}), 403

            cursor.execute("SELECT jam_mulai FROM jadwal_kuliah WHERE id_jadwal = %s", (id_jadwal,))
            jadwal_row = cursor.fetchone()
            if not jadwal_row or not jadwal_row[0]:
                return jsonify({"status": "error", "message": "Jadwal kuliah tidak ditemukan!"}), 404

            jam_mulai_str = str(jadwal_row[0])
            waktu_mulai = datetime.strptime(jam_mulai_str, '%H:%M:%S' if len(jam_mulai_str.split(':')) == 3 else '%H:%M').time()
            waktu_sekarang_lokal = datetime.now()
            dt_mulai = datetime.combine(waktu_sekarang_lokal.date(), waktu_mulai)
            
            selisih_menit = (waktu_sekarang_lokal - dt_mulai).total_seconds() / 60.0

            if selisih_menit < -30:
                return jsonify({"status": "error", "message": "Absen belum dibuka! Tunggu 30 menit sebelum jadwal."}), 400
            elif selisih_menit > 45: status_kehadiran = "Alpha"
            elif selisih_menit > 35: status_kehadiran = "Terlambat"
            else: status_kehadiran = "Hadir"

            cursor.execute("SELECT COALESCE(MAX(pertemuan_ke), 0) + 1 FROM presensi WHERE nim = %s AND id_jadwal = %s", (nim, int(id_jadwal)))
            pertemuan_ke = cursor.fetchone()[0]

            cursor.execute(
                """
                INSERT INTO presensi (nim, id_jadwal, pertemuan_ke, latitude, longitude, foto_absen, status_absen, tanggal, waktu_absen) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (nim, int(id_jadwal), pertemuan_ke, user_lat, user_lon, public_url, status_kehadiran, waktu_sekarang_lokal.date(), waktu_sekarang_lokal.time())
            )
            conn.commit()
            cursor.close()
            release_connection(conn)

            return jsonify({
                "status": "success",
                "message": f"Presensi Berhasil! Status: {status_kehadiran}",
                "data": {
                    "nim": str(nim),
                    "status": str(status_kehadiran),
                    "confidence": nilai_confidence
                }
            }), 200

        except Exception as e:
            return jsonify({"status": "error", "message": f"Gagal Database: {str(e)}"}), 500
    else:
        return jsonify({"status": "error", "message": f"Wajah tidak dikenali! Score: {nilai_confidence}"}), 403

# ==========================================
# 2. API DAFTAR WAJAH & PELATIHAN (TRAIN)
# ==========================================
@absen_bp.route('/register-wajah', methods=['POST'])
def register_wajah():
    nim = request.form.get('nim')
    is_admin = request.form.get('is_admin')
    fotos = request.files.getlist('foto')

    if not nim or not fotos:
        return jsonify({"status": "error", "message": "NIM atau foto tidak lengkap"}), 400

    conn = get_connection()
    cursor = conn.cursor()
    wajah_tersimpan = 0
    waktu_sekarang = int(datetime.now().timestamp())

    for foto in fotos:
        if foto.filename == '':
            continue
        
        in_memory_file = foto.read()
        nparr = np.frombuffer(in_memory_file, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(100, 100))

        for (x, y, w, h) in faces:
            wajah_crop = gray[y:y+h, x:x+w]
            wajah_resize = cv2.resize(wajah_crop, (200, 200))
            filename = f"{nim}_{waktu_sekarang}_{wajah_tersimpan}.jpg"
            
            # 1. Ubah gambar OpenCV (numpy array) menjadi format file (bytes)
            _, buffer = cv2.imencode('.jpg', wajah_resize)
            image_bytes = buffer.tobytes()

            try:
                # 2. Upload file ke Supabase Storage (pastikan kamu sudah buat bucket 'dataset-wajah')
                supabase.storage.from_("dataset-wajah").upload(
                    file=image_bytes,
                    path=filename,
                    file_options={"content-type": "image/jpeg"}
                )
                
                # 3. Ambil URL publik dari Supabase untuk disimpan ke database
                public_url = supabase.storage.from_("dataset-wajah").get_public_url(filename)
                
                # 4. Simpan URL tersebut ke PostgreSQL, BUKAN path lokal lagi
                cursor.execute("INSERT INTO dataset_wajah (nim, file_path) VALUES (%s, %s)", (nim, public_url))
                wajah_tersimpan += 1
                break # Pindah ke foto berikutnya jika wajah sudah terdeteksi
            except Exception as e:
                print(f"[ERROR UPLOAD] Gagal upload foto ke Supabase: {str(e)}")
                break

    if wajah_tersimpan > 0:
        if is_admin != 'true':
            cursor.execute("UPDATE mahasiswa SET wajah_terdaftar = TRUE WHERE nim = %s", (nim,))
            pesan = f"Berhasil mendaftarkan {wajah_tersimpan} variasi wajah."
        else:
            pesan = f"Berhasil menambah {wajah_tersimpan} foto pancingan admin."
        conn.commit()
        status_code, response = 200, {"status": "success", "message": pesan}
    else:
        status_code, response = 400, {"status": "error", "message": "Gagal mendeteksi wajah atau upload error."}

    cursor.close()
    release_connection(conn)
    return jsonify(response), status_code


@absen_bp.route('/train', methods=['POST', 'GET'])
def train_model():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT nim, file_path FROM dataset_wajah")
    dataset = cursor.fetchall()
    cursor.close()
    release_connection(conn)

    if not dataset:
        return jsonify({"status": "error", "message": "Dataset kosong di database."}), 400

    face_samples, ids, label_map, nim_to_id, current_id = [], [], {}, {}, 0
    
    print(f"[INFO] Memulai training. Total data di DB: {len(dataset)}")
    for nim, file_path in dataset:
        try:
            # Ambil nama file asli dari path/URL di database
            filename_pasien = file_path.split("/")[-1]
            
            # Buat signed URL yang berlaku sementara (misal 60 detik) agar bisa di-download server
            signed_url_res = supabase.storage.from_("dataset-wajah").create_signed_url(filename_pasien, 60)
            
            # Ambil URL dari respons signed URL (format bisa berupa dict atau objek tergantung versi library)
            signed_url = signed_url_res.get('signedURL') if isinstance(signed_url_res, dict) else signed_url_res
            
            if not signed_url:
                print(f"[WARNING] Gagal membuat signed URL untuk: {filename_pasien}")
                continue

            resp = requests.get(signed_url, timeout=10)
            if resp.status_code != 200:
                print(f"[WARNING] Gagal download via signed URL (status {resp.status_code}): {filename_pasien}")
                continue
            
            nparr = np.frombuffer(resp.content, np.uint8)
            img_numpy = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)

            if img_numpy is None:
                print(f"[WARNING] Gagal decode gambar untuk NIM {nim}")
                continue

            if nim not in nim_to_id:
                nim_to_id[nim] = current_id
                label_map[current_id] = nim
                current_id += 1
            
            face_samples.append(img_numpy)
            ids.append(nim_to_id[nim])
        except Exception as e:
            print(f"[ERROR] Exception saat memproses {file_path}: {e}")
            continue

    print(f"[INFO] Total wajah valid terkumpul untuk training: {len(face_samples)}")

    if len(face_samples) == 0:
        return jsonify({"status": "error", "message": "Gagal mengunduh dataset. Pastikan bucket dataset-wajah dapat diakses."}), 400

    try:
        recognizer.train(face_samples, np.array(ids))
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        recognizer.save(MODEL_PATH)
        with open(LABEL_MAP_PATH, 'w') as f:
            json.dump(label_map, f)

        with open(MODEL_PATH, 'rb') as f:
            supabase.storage.from_("model-lbph").upload(
                file=f.read(), path="trainer.yml", file_options={"upsert": "true"}
            )
        with open(LABEL_MAP_PATH, 'rb') as f:
            supabase.storage.from_("model-lbph").upload(
                file=f.read(), path="label_map.json", file_options={"upsert": "true"}
            )

        return jsonify({"status": "success", "message": f"Model berhasil dilatih dengan {len(face_samples)} wajah!"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ==========================================
# 3. API JADWAL & RIWAYAT (DASHBOARD MAHASISWA)
# ==========================================
@absen_bp.route('/riwayat/<nim>', methods=['GET'])
def get_riwayat(nim):
    tahun_akademik = request.args.get('tahun')
    semester = request.args.get('semester')
    
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        query = """
            SELECT p.tanggal, p.waktu_absen, p.status_absen, mk.nama_mk, p.latitude, p.longitude
            FROM presensi p
            JOIN jadwal_kuliah jk ON p.id_jadwal = jk.id_jadwal
            JOIN matakuliah mk ON jk.id_mk = mk.id_mk
            WHERE p.nim = %s
        """
        params = [nim]
        
        if tahun_akademik:
            query += " AND jk.tahun_akademik = %s"
            params.append(tahun_akademik)
            
        if semester:
            query += " AND jk.semester = %s"
            params.append(semester)
            
        query += " ORDER BY p.tanggal DESC, p.waktu_absen DESC"
        
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()
        
        riwayat_list = []
        for r in rows:
            riwayat_list.append({
                "tanggal": str(r[0]) if r[0] else "-",
                "waktu": str(r[1]) if r[1] else "-",
                "status": r[2],
                "mata_kuliah": r[3],
                "latitude": r[4],
                "longitude": r[5]
            })
        
        cursor.close()
        release_connection(conn)
        return jsonify({"status": "success", "data": riwayat_list}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@absen_bp.route('/jadwal/<nim>', methods=['GET'])
def get_jadwal_hari_ini(nim):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        hari_inggris = datetime.now().strftime('%A')
        mapping_hari = {
            'Monday': 'Senin',
            'Tuesday': 'Selasa',
            'Wednesday': 'Rabu',
            'Thursday': 'Kamis',
            'Friday': 'Jumat',
            'Saturday': 'Sabtu',
            'Sunday': 'Minggu'
        }
        hari_ini = mapping_hari.get(hari_inggris, 'Senin')
        
        cursor.execute("""
            SELECT jk.id_jadwal, mk.nama_mk, d.nama_dosen, r.nama_ruangan, 
                   jk.jam_mulai, jk.jam_selesai, jk.hari,
                   (SELECT p.status_absen FROM presensi p 
                    WHERE p.id_jadwal = jk.id_jadwal 
                    AND p.nim = %s 
                    AND p.tanggal = CURRENT_DATE 
                    LIMIT 1) as status_hari_ini
            FROM jadwal_kuliah jk
            JOIN matakuliah mk ON jk.id_mk = mk.id_mk
            JOIN dosen d ON jk.id_dosen = d.id_dosen
            LEFT JOIN ruangan r ON jk.id_ruangan = r.id_ruangan
            JOIN mahasiswa m ON jk.id_kelas = m.id_kelas
            WHERE m.nim = %s AND jk.hari = %s
            ORDER BY jk.jam_mulai
        """, (nim, nim, hari_ini))
        
        rows = cursor.fetchall()
        jadwal_list = []
        for r in rows:
            jadwal_list.append({
                "id_jadwal": r[0],
                "nama_mk": r[1],
                "nama_dosen": r[2],
                "nama_ruangan": r[3] if r[3] else "Belum Ditentukan",
                "jam_mulai": str(r[4]),
                "jam_selesai": str(r[5]),
                "hari": r[6],
                "status_hari_ini": r[7]
            })
            
        cursor.close()
        release_connection(conn)
        return jsonify({"status": "success", "data": jadwal_list}), 200
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@absen_bp.route('/kehadiran/rekap/<nim>', methods=['GET'])
def get_rekap_kehadiran(nim):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        query = """
            SELECT jk.id_jadwal, mk.nama_mk, mk.sks, d.nama_dosen, jk.total_pertemuan,
                (SELECT COUNT(*) FROM presensi p WHERE p.id_jadwal = jk.id_jadwal AND p.nim = %s AND p.status_absen IN ('Hadir', 'Terlambat')) as total_hadir,
                (SELECT COUNT(*) FROM presensi p WHERE p.id_jadwal = jk.id_jadwal AND p.nim = %s AND p.status_absen IN ('Izin', 'Sakit')) as total_izin,
                (SELECT COUNT(*) FROM presensi p WHERE p.id_jadwal = jk.id_jadwal AND p.nim = %s AND p.status_absen = 'Alpha') as total_alpha,
                (SELECT COUNT(*) FROM presensi p WHERE p.id_jadwal = jk.id_jadwal AND p.nim = %s) as pertemuan_berjalan
            FROM jadwal_kuliah jk
            JOIN matakuliah mk ON jk.id_mk = mk.id_mk
            JOIN dosen d ON jk.id_dosen = d.id_dosen
            JOIN mahasiswa m ON jk.id_kelas = m.id_kelas
            WHERE m.nim = %s
        """
        cursor.execute(query, (nim, nim, nim, nim, nim))
        rows = cursor.fetchall()
        hasil = []
        for r in rows:
            id_jadwal, nama_mk, sks, nama_dosen, total_pertemuan, hadir, izin, alpha, berjalan = r
            persentase = round(((hadir + izin) / berjalan) * 100) if berjalan > 0 else 0
            hasil.append({
                "id_jadwal": id_jadwal, "nama_mk": nama_mk, "sks": sks, "nama_dosen": nama_dosen,
                "total_pertemuan": total_pertemuan, "pertemuan_berjalan": berjalan,
                "total_hadir": hadir, "total_izin": izin, "total_alpha": alpha, "persentase_kehadiran": persentase
            })
        cursor.close()
        release_connection(conn)
        return jsonify({"status": "success", "data": hasil}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@absen_bp.route('/kehadiran/detail/<nim>/<id_jadwal>', methods=['GET'])
def get_detail_kehadiran(nim, id_jadwal):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT total_pertemuan FROM jadwal_kuliah WHERE id_jadwal = %s", (id_jadwal,))
        row = cursor.fetchone()
        total_pertemuan = row[0] if row else 16

        cursor.execute("SELECT pertemuan_ke, tanggal, status_absen FROM presensi WHERE nim = %s AND id_jadwal = %s ORDER BY pertemuan_ke ASC", (nim, id_jadwal))
        riwayat = cursor.fetchall()
        riwayat_dict = {r[0]: {"tanggal": str(r[1]), "status": r[2]} for r in riwayat}

        detail = []
        for i in range(1, total_pertemuan + 1):
            if i in riwayat_dict:
                detail.append({"pertemuan": i, "tanggal": riwayat_dict[i]["tanggal"], "status": riwayat_dict[i]["status"]})
            else:
                detail.append({"pertemuan": i, "tanggal": "-", "status": "Belum Mulai"})

        cursor.close()
        release_connection(conn)
        return jsonify({"status": "success", "data": detail}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@absen_bp.route('/absen/izin', methods=['POST'])
def absen_izin():
    nim = request.form.get('nim')
    id_jadwal = request.form.get('id_jadwal')
    pertemuan_ke = request.form.get('pertemuan_ke')
    status = request.form.get('status') # 'Izin' atau 'Sakit'

    if not all([nim, id_jadwal, pertemuan_ke, status]) or 'bukti' not in request.files:
        return jsonify({"status": "error", "message": "Data form atau file bukti tidak lengkap"}), 400

    file = request.files['bukti']
    if file.filename == '':
        return jsonify({"status": "error", "message": "File bukti tidak valid"}), 400

    try:
        # 1. Baca file langsung ke memory (tanpa simpan ke disk Koyeb)
        file_bytes = file.read()
        img = Image.open(io.BytesIO(file_bytes))
        
        # --- PROSES OCR (DETEKSI TEKS) ---
        teks_terdeteksi = pytesseract.image_to_string(img, lang='ind')
        teks_lower = teks_terdeteksi.lower()
        print(f"--- TEKS TERDETEKSI DARI SURAT --- \n{teks_terdeteksi}\n----------------------------------")

        kata_kunci = ['sakit', 'izin', 'dokter', 'permohonan', 'surat', 'kepada', 'mahasiswa', 'tidak dapat']
        ada_kata_kunci = any(kata in teks_lower for kata in kata_kunci)

        if len(teks_terdeteksi.strip()) < 20 or not ada_kata_kunci:
            return jsonify({
                "status": "error",
                "message": "File ditolak! Sistem mendeteksi ini bukan surat izin/sakit yang valid (tidak ada teks surat yang sesuai)."
            }), 400

        # 2. Jika lolos validasi OCR, siapkan nama file
        filename = secure_filename(f"izin_{nim}_jadwal{id_jadwal}_ptm{pertemuan_ke}_{int(datetime.now().timestamp())}.jpg")
        
        # 3. Upload bytes gambar langsung ke Supabase (bucket: bukti-izin)
        supabase.storage.from_("bukti-izin").upload(
            file=file_bytes,
            path=filename,
            file_options={"content-type": file.content_type}
        )
        
        # 4. Ambil URL publik
        public_url = supabase.storage.from_("bukti-izin").get_public_url(filename)

        # 5. Simpan URL tersebut ke Database (menggantikan filepath_final lokal)
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            """
            INSERT INTO presensi (nim, id_jadwal, pertemuan_ke, status_absen, bukti_izin, tanggal, waktu_absen) 
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (nim, id_jadwal, pertemuan_ke, status, public_url, datetime.now().date(), datetime.now().time())
        )
        conn.commit()
        cursor.close()
        release_connection(conn)

        return jsonify({"status": "success", "message": f"Pengajuan {status} berhasil divalidasi dan dicatat."}), 200

    except Exception as e:
        print(f"[ERROR IZIN] {str(e)}")
        return jsonify({"status": "error", "message": f"Gagal memproses gambar: {str(e)}"}), 500