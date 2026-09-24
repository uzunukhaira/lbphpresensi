import psycopg2
from psycopg2 import pool

# 1. DEKLARASIKAN VARIABEL GLOBAL DI SINI SEBELUM BLOK TRY
db_pool = None

# Kredensial Supabase
DB_HOST = "aws-0-ap-southeast-1.pooler.supabase.com"
DB_PORT = "6543"
DB_NAME = "postgres"
DB_USER = "postgres.mkbmmyuoxpuwxnsmsfsb"
DB_PASS = "DyaBae1909Nu"

try:
    db_pool = psycopg2.pool.SimpleConnectionPool(
        1, 20,
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
        port=DB_PORT
    )
    if db_pool:
        print("Koneksi ke PostgreSQL Supabase berhasil!")
except (Exception, psycopg2.DatabaseError) as error:
    print("Error saat menghubungkan ke database:", error)
    # db_pool akan tetap bernilai None jika koneksi gagal

def get_connection():
    # 2. TAMBAHKAN PENGECEKAN INI AGAR TIDAK ERROR NAMA
    if db_pool is None:
        raise Exception("Database pool belum siap atau koneksi gagal!")
    return db_pool.getconn()

def release_connection(conn):
    if db_pool and conn:
        db_pool.putconn(conn)