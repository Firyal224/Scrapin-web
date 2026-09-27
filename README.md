---
title: ScrapIn
emoji: 🗺️
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
---

# ScrapIn: Scraper Data Tempat Usaha (Tool Internal)

Web app internal untuk mengumpulkan daftar tempat usaha (restoran, cafe, salon, atau kategori apa saja) di satu area. Sumber datanya **OpenStreetMap**, jadi **gratis, tanpa API key, dan tanpa billing**.

Alurnya: isi **keyword**, **area**, **maks hasil**, dan (opsional) **range harga**, lalu klik **Mulai scraping**. Setelah selesai, **file CSV otomatis terdownload**. XLSX dan ZIP (berisi foto) juga tersedia.

Kolom output: `Nama, Der Treffpunkt, Sosmed, Kontak, Gambar, Alasan`.

| Komponen | Teknologi |
|---|---|
| Backend + API | Python, FastAPI, uvicorn (`scraper/web`) |
| Frontend | React + Vite (`frontend/`), dibuild lalu disajikan oleh backend |
| Sumber data | OpenStreetMap: Nominatim (area) + Overpass (tempat usaha), ditambah website tiap tempat |
| Log | `logs/scraper.log` (rotating, tiap baris punya `job=<id>`) |

## 1. Instalasi

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows  (Linux/macOS: source .venv/bin/activate)
pip install -r requirements-dev.txt

cd frontend
npm install
npm run build
cd ..
```

File `.env` opsional. Salin dari `.env.example` kalau ingin mengubah host, port, atau base URL.

## 2. Menjalankan

```bash
python -m scraper.web
```

Buka http://127.0.0.1:8000.

**Supaya bisa dipakai tim di jaringan kantor**, isi `.env` dengan:
```
HOST=0.0.0.0
```
Lalu tim membuka `http://<IP-komputer-server>:8000`.

Mode development frontend (hot reload, backend tetap harus jalan):
```bash
cd frontend && npm run dev      # http://localhost:5173, /api diproxy ke API_TARGET (default http://127.0.0.1:8000)
```

CLI tanpa UI:
```bash
python -m scraper.main --keyword salon --area "Jakarta Selatan" --max-results 20
python -m scraper.main --keyword restoran --area "Jakarta Selatan" --max-results 10 --price-min 50000 --price-max 150000
```
Exit code: `0` sukses, `1` error sumber data/konfigurasi, `2` input tidak valid, `3` tidak ada hasil.

## 3. Base URL dinamis

Semua URL di aplikasi mengikuti alamat yang dipakai untuk membukanya, tanpa ada yang dihardcode:

- **Frontend** memanggil API lewat path relatif (`/api/...`), jadi otomatis ikut host yang sedang dibuka.
- **Link galeri di CSV/XLSX** (kolom Gambar) dibentuk dari alamat akses. Dibuka lewat `http://192.168.1.10:8000` → link galerinya `http://192.168.1.10:8000/galeri/<job-id>/<nama-tempat>`. Header `Host` divalidasi dulu. Kalau tidak valid, dipakai `http://127.0.0.1:<PORT>`.
- **Override** hanya diperlukan kalau server berada di belakang reverse proxy/domain: isi `PUBLIC_BASE_URL=https://scraper.kantor.id`.
- **CLI** memakai `PUBLIC_BASE_URL`, atau `http://<HOST>:<PORT>` kalau tidak diisi.
- **Dev proxy Vite** memakai `API_TARGET`.

## 4. Cara kerja

1. **Area** dicari lewat Nominatim untuk mendapatkan batas wilayah administratifnya. Singkatan seperti `Jaksel` tetap dikenali. Kalau area berupa titik (bukan wilayah), pencarian memakai radius 3 km.
2. **Tempat usaha** di dalam batas wilayah itu diambil lewat Overpass. Keyword umum (restoran, cafe, salon, gym, bengkel, klinik, apotek, dll.) dipetakan ke tag OSM, sedangkan keyword lain dicocokkan dengan nama tempat. Kalau server Overpass sibuk, 4 mirror dicoba bergantian.
3. Hasil **diurutkan dari data yang paling lengkap**, lalu duplikat nama dibuang.
4. **Enrichment**: kalau tempat punya website, halaman depannya dibaca, ditambah maksimal 2 halaman **menu/pricelist/layanan** di domain yang sama. Dari situ diambil link Instagram, WhatsApp/telepon, harga (`Rp 35.000`, `35rb`, `35k`, `1,2jt`), dan kandidat foto.
5. **Filter harga (opsional)**: kalau range harga diisi, Overpass hanya mengambil tempat yang punya website, lalu website tersebut dicek satu per satu (maks. 80). Tempat lolos kalau minimal satu harga di websitenya masuk range. **Tempat tanpa info harga dibuang.**
6. **Foto**: maksimal 6 per tempat. Ikon, logo, badge, pixel tracking, gambar kecil (<200px), gambar transparan, dan gambar yang didominasi satu warna (logo/grafik) dibuang, begitu juga foto duplikat. Foto dari halaman menu, atau yang nama file/alt-nya mengandung kata menu/pricelist/layanan, diberi label **Menu/Layanan** dan diurutkan paling depan. Semua foto diencode ulang ke JPEG (maks. 800px) di `output/<job-id>/images/`.
7. File CSV, XLSX, ZIP, dan `gallery.json` ditulis ke `output/<job-id>/`, lalu CSV otomatis terdownload di browser.

Hasil Nominatim dan Overpass dicache 24 jam di `output/.cache/`. Pencarian yang sama jadi lebih cepat, dan kalau semua server Overpass sedang down, cache lama tetap dipakai.

Batasan (tanpa AI): label Menu/Layanan dan filter logo berbasis aturan, jadi sesekali keliru. Foto dan harga hanya dari website, bukan dari Instagram. Harga yang ada di dalam gambar atau PDF menu tidak terbaca.

### Arti kolom
| Kolom | Isi |
|---|---|
| Nama | Nama tempat dari OpenStreetMap |
| Der Treffpunkt | Link Google Maps (`maps/search/?api=1&query=nama, alamat`). Ini link biasa, bukan API. |
| Sosmed | Instagram → website → kalau tidak ada keduanya, link "Cari IG" (pencarian Google) |
| Kontak | HP: `https://wa.me/62...`, kantor: `tel:+62...` |
| Gambar | Link **galeri foto** tempat itu (maks. 6 foto, foto menu/layanan di depan). Hanya bisa dibuka selama server menyala. |
| Alasan | Jumlah foto, kisaran harga dari website, dan catatan data yang kosong. Contoh: `tanpa nomor telepon; 2 foto (1 menu/layanan); harga Rp 32.000 sampai Rp 57.000 (dari website)` |

Kelengkapan data tergantung kategori. Dari hasil tes di Jakarta Selatan, restoran dan cafe hampir semua punya kontak, sedangkan salon dan bengkel masih banyak yang kosong.

## 5. Log dan tracing

Semua aktivitas ditulis ke `logs/scraper.log` (rotasi 2 MB × 5 file). Contohnya:

```
2026-09-28 00:59:13 INFO    [job=0c85884c] scraper.web.jobs: Job dimulai: keyword='cafe' area='Jaksel' max=8 base=http://localhost:8001
2026-09-28 00:59:14 INFO    [job=0c85884c] scraper.sources.osm: Area 'Jaksel' -> relation/5802438 (Jakarta Selatan, ...)
2026-09-28 00:59:20 WARNING [job=0c85884c] scraper.sources.osm: Overpass gagal, coba mirror berikutnya: ... HTTP 504
2026-09-28 00:59:25 INFO    [job=0c85884c] scraper.enrich: Enrichment Poly Board Games Cafe: instagram, image
```

Untuk error internal, UI menampilkan ID job yang bisa dicari dengan `grep job=<id> logs/scraper.log`. Detail log bisa ditambah lewat `LOG_LEVEL=DEBUG` (termasuk query Overpass).

## 6. Keamanan

- Server default hanya listen di `127.0.0.1`. Buka ke jaringan hanya dengan `HOST=0.0.0.0`, dan hanya di jaringan internal (tidak ada autentikasi).
- Input divalidasi di client dan server (panjang, karakter yang diizinkan, rentang maks hasil). Keyword bebas dibersihkan sebelum masuk ke query Overpass.
- Header `Host` divalidasi sebelum dipakai sebagai base URL.
- Proteksi CSV/Excel formula injection: sel CSV yang diawali `= + - @` diberi prefix `'`, dan sel XLSX dipaksa bertipe teks.
- Path traversal diblok: ID job wajib UUID hex, dan nama file gambar serta key galeri diwhitelist lalu diresolve di dalam folder job.
- Halaman galeri dirender server dengan semua teks diescape (nama tempat dari data luar tidak bisa menyisipkan HTML/script).
- Halaman menu yang diikuti hanya yang berada di domain yang sama dengan website tempat usaha.
- Anti-SSRF: website dan gambar hanya diambil dari **IP publik** (loopback, jaringan privat, dan link-local ditolak), port 80/443, redirect maks. 3 (dicek per hop), batas ukuran (HTML 1.5 MB, gambar 8 MB), dan timeout.
- Gambar selalu diencode ulang oleh Pillow, dengan batas piksel untuk mencegah *decompression bomb*.
- Link di tabel hanya dirender kalau skemanya `http`, `https`, atau `tel`.
- Header keamanan aktif: CSP ketat, `X-Frame-Options: DENY`, `nosniff`, dan `Referrer-Policy: no-referrer`. Endpoint `/docs` dinonaktifkan.
- Antrian dibatasi maksimal 5 job aktif.

## 7. Tes

```bash
python -m pytest -q
cd frontend && npm test
```

## 8. Atribusi

Data © OpenStreetMap contributors, berlisensi ODbL. Atribusi sudah tampil di footer UI. Cantumkan juga kalau hasil dibagikan ke luar tim.

## 9. Deploy ke Hugging Face Spaces (private, gratis)

Repo ini sudah siap untuk Hugging Face: ada `Dockerfile`, dan konfigurasi Space ada di bagian atas README ini (`sdk: docker`, `app_port: 7860`).

1. Daftar di https://huggingface.co.
2. Buat Space baru: **New Space** → nama `scrapin-web` → SDK **Docker** (Blank) → hardware **CPU basic (free)** → visibility **Private**.
3. Buat token: **Settings → Access Tokens → New token** (tipe **Write**).
4. Dari folder proyek:
   ```bash
   git remote add space https://huggingface.co/spaces/<username-hf>/scrapin-web
   git push space main
   ```
   Isi username Hugging Face, dan untuk password tempel token dari langkah 3. Kalau Space baru berisi commit awal dari Hugging Face, gunakan `git push space main --force` untuk push pertama saja.
5. Pantau build di tab **Logs**. Setelah **Running**, buka `https://<username-hf>-scrapin-web.hf.space` (harus login Hugging Face).
6. Update berikutnya: `git push origin main` (GitHub) lalu `git push space main` (Hugging Face).

Catatan:
- Tidak ada secret yang perlu diisi, karena aplikasi tidak memakai API key.
- Space tidur setelah lama tidak dipakai, lalu bangun otomatis saat dibuka.
- Disk tidak permanen. Setelah restart/update, link galeri di CSV lama tidak bisa dibuka lagi, tapi isi CSV tetap utuh. Download ZIP kalau fotonya perlu disimpan.
- Link galeri otomatis memakai `https://<username-hf>-scrapin-web.hf.space`, karena base URL dinamis dan header proxy dipercaya (`FORWARDED_ALLOW_IPS=*` di Dockerfile).
- Supaya tim bisa membuka: buat **Organization** di Hugging Face, pindahkan Space ke sana, lalu undang anggotanya.

## 10. GitHub Actions (opsional)

`.github/workflows/scrape.yml` menjalankan CLI lewat `workflow_dispatch` (input `keyword`, `area`, `max_results`), lalu mengupload hasil dan log sebagai artifact. Tidak butuh secret apa pun.
"# Scrapin-web" 
