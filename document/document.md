# Prompt untuk Claude Code — Tool Scraping Restoran/Cafe (Web UI + Deploy GitHub)

Copy-paste seluruh isi di bawah "## PROMPT" ke Claude Code untuk mulai implementasi.

---

## PROMPT

Saya mau kamu buatkan tool **web scraping restoran/cafe dengan UI**, yang bisa saya deploy sepenuhnya di GitHub (tanpa server berbayar terpisah). Contoh pemakaian: user buka web, isi keyword ("cafe") + area ("Jakarta Selatan"), klik "Scrape", hasil keluar sebagai CSV/XLSX dengan kolom PERSIS seperti ini:

```
Nama | Der Treffpunkt | Sosmed | Kontak | Gambar | Alasan
```

Contoh baris data existing (referensi format):
```
Nama: Little Talk Bistro
Der Treffpunkt: maps little talk bistro   (link Google Maps)
Sosmed: IG Little Talk Bistro             (link/handle Instagram)
Kontak: https://wa.me/62812xxxxxxxx        (link WhatsApp)
Gambar: menu gambar                       (path/link ke file gambar menu)
Alasan: (opsional, catatan manual)
```

### Arsitektur yang saya mau (WAJIB diikuti)

Semua jalan pakai fitur GitHub gratis — **tidak ada server backend terpisah**:

| Komponen | Pakai | Fungsi |
|---|---|---|
| Frontend (UI) | **GitHub Pages** (static site) | Form input keyword+area, tombol scrape, tabel hasil, tombol download |
| Mesin scraping | **GitHub Actions** (`workflow_dispatch`) | Menjalankan script Python scraper saat dipicu dari UI |
| API key Google Places | **GitHub Secrets** | Disimpan aman, tidak pernah terekspos ke browser |
| Penyimpanan hasil | **GitHub Actions Artifacts** (default) atau **GitHub Releases** | File CSV/XLSX + gambar bisa didownload lewat link |
| Trigger dari UI | **GitHub REST API** (`POST .../actions/workflows/scrape.yml/dispatches`) | Dipanggil dari JavaScript browser, pakai GitHub Personal Access Token milik user (disimpan di `localStorage` browser, TIDAK pernah dikirim ke server manapun selain langsung ke GitHub) |

### Requirement wajib

1. **TANPA AI/LLM sama sekali** di seluruh pipeline scraping — murni Google Places API / rule sederhana, supaya tidak ada biaya token.
2. **Sumber data utama: Google Places API** (Text Search + Place Details + Place Photos) untuk nama, link Maps, telepon, foto.
3. **Kolom Sosmed:** cukup link pencarian/handle Instagram (dari field "website" Places API kalau ada) — JANGAN scraping isi akun Instagram.
4. **Kolom Kontak:** format nomor telepon ke `https://wa.me/<nomor format internasional>`.
5. **Kolom Gambar:** download foto dari Google Places Photos API, simpan di `STORAGE_MODE=local` (default, ikut ke Actions artifact) — sediakan juga opsi `STORAGE_MODE=drive` (upload ke Google Drive via service account) untuk dikerjakan belakangan.
6. **Kolom Alasan:** default kosong, atau rule sederhana if/else (bukan AI).
7. **Rate limiting:** delay random 1–3 detik antar request Google Places.
8. **Output:** `.csv` + `.xlsx` sekaligus, urutan kolom persis: `Nama, Der Treffpunkt, Sosmed, Kontak, Gambar, Alasan`.

### Struktur folder yang diinginkan

```
resto-scraper/
├── .github/
│   └── workflows/
│       └── scrape.yml        # trigger via workflow_dispatch, input: keyword, area
├── frontend/                  # static site → deploy ke GitHub Pages
│   ├── index.html
│   ├── src/
│   │   ├── App.jsx            # form input + tombol scrape + tabel hasil + token input
│   │   └── github-api.js      # trigger workflow_dispatch + polling status run + ambil artifact
│   └── package.json
├── scraper/
│   ├── config.py               # baca API key dari environment (GitHub Secrets)
│   ├── main.py                  # entry point, dipanggil scrape.yml
│   ├── maps_scraper.py          # Google Places search
│   ├── image_fetcher.py         # download foto menu
│   └── storage/
│       ├── local_storage.py     # simpan gambar lokal di runner
│       └── drive_storage.py     # upload ke Google Drive (belakangan)
├── requirements.txt
└── README.md                    # cara setup Secrets, aktifkan Pages, dapetin token GitHub
```

### Alur kerja end-to-end yang harus berfungsi

1. User buka halaman GitHub Pages.
2. User masukkan GitHub Personal Access Token sekali (disimpan `localStorage`).
3. User isi keyword + area, klik "Scrape Sekarang".
4. Frontend panggil `POST /repos/{owner}/{repo}/actions/workflows/scrape.yml/dispatches` dengan `inputs: {keyword, area}`.
5. Frontend polling `GET /repos/{owner}/{repo}/actions/runs` sampai status job = completed.
6. Frontend ambil hasil dari `GET /repos/{owner}/{repo}/actions/artifacts`, tampilkan tabel preview (pakai `papaparse` untuk CSV) + tombol download CSV/XLSX.

### Library yang disarankan

**Backend (Python, dijalankan oleh Actions runner):**
- `googlemaps`, `pandas`, `openpyxl`, `Pillow`, `python-dotenv`
- (nanti) `google-api-python-client` + `google-auth` untuk mode Drive

**Frontend (JS):**
- React + Vite (atau HTML/JS polos), `papaparse`, `sheetjs/xlsx`, Tailwind

### Langkah kerja yang saya mau kamu ikuti

1. Setup struktur project + `requirements.txt` + `package.json`.
2. Implementasi `scraper/maps_scraper.py` + `local_storage.py` + output writer CSV/XLSX — test dulu lewat CLI biasa (`python main.py --keyword cafe --area "Jakarta Selatan"`), tunjukkan hasilnya ke saya.
3. Setelah saya konfirmasi hasil scraping oke, bungkus jadi `.github/workflows/scrape.yml` yang menerima `keyword` & `area` sebagai `workflow_dispatch` input.
4. Buat `frontend/` sederhana: form input, tombol trigger workflow via GitHub API, polling status, tampilkan hasil.
5. Tulis `README.md`: cara bikin Google Places API key, cara set GitHub Secret, cara aktifkan GitHub Pages, cara bikin Personal Access Token untuk dipakai di UI.
6. Setelah semua jalan, baru tambahkan `drive_storage.py` sebagai opsi kedua penyimpanan gambar.

Mulai dari langkah 1–2 dulu, tunjukkan contoh hasil scraping-nya ke saya sebelum lanjut ke bagian workflow & frontend.
