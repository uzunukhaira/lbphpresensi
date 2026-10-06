from database import get_connection, release_connection
from werkzeug.security import generate_password_hash

try:
    conn = get_connection()
    cursor = conn.cursor()
    
    username = "admin"
    nama = "Admin Utama"
    password_baru = "admin1234"
    
    password_hashed = generate_password_hash(password_baru)
    
    # Perintah ini akan memasukkan data baru, atau memperbarui jika username-nya sudah ada
    cursor.execute(
        """
        INSERT INTO admin (username, nama_admin, password) 
        VALUES (%s, %s, %s)
        ON CONFLICT (username) 
        DO UPDATE SET password = EXCLUDED.password, nama_admin = EXCLUDED.nama_admin
        """,
        (username, nama, password_hashed)
    )
    
    conn.commit()
    cursor.close()
    release_connection(conn)
    print(f"Sukses! Akun admin dengan username '{username}' dan password '{password_baru}' berhasil disimpan.")
    
except Exception as e:
    print("Terjadi kesalahan:", e)