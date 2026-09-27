import { useEffect, useRef, useState } from "react";
import { fileUrl, getHealth } from "./api.js";
import { useScrapeJob } from "./useScrapeJob.js";
import Navbar from "./components/Navbar.jsx";
import SearchForm from "./components/SearchForm.jsx";
import ProgressCard from "./components/ProgressCard.jsx";
import Results from "./components/Results.jsx";
import { Toasts, useToasts } from "./components/Toasts.jsx";

const STEPS = [
  "Area dicari di OpenStreetMap untuk mendapatkan batas wilayahnya. Singkatan seperti “Jaksel” tetap dikenali.",
  "Semua tempat usaha di dalam batas wilayah itu diambil. Keyword umum (restoran, cafe, salon, gym, bengkel, dll.) dipetakan ke kategori OSM, dan keyword lain dicocokkan dengan nama tempat.",
  "Hasil diurutkan dari data yang paling lengkap. Website tiap tempat dibaca beserta maksimal 2 halaman menu/pricelist/layanan untuk mencari Instagram, WhatsApp, harga, dan foto.",
  "Kalau range harga diisi, hanya tempat yang mencantumkan harga “Rp…” di websitenya dan masuk range yang diambil.",
  "Maksimal 6 foto per tempat diunduh. Logo, ikon, dan gambar kecil dibuang. Foto dari halaman menu/layanan diberi label Menu dan ditaruh paling depan.",
  "Nomor HP dijadikan link wa.me dan telepon kantor jadi tel:. Kolom Gambar berisi link galeri foto tiap tempat.",
  "File CSV otomatis terdownload. XLSX dan ZIP (CSV + XLSX + foto) juga bisa diunduh dari panel hasil.",
];

const COLUMNS = [
  ["Nama", "Nama tempat usaha sesuai data OpenStreetMap."],
  ["Der Treffpunkt", "Link Google Maps (pencarian nama + alamat). Klik untuk membuka lokasinya."],
  ["Sosmed", "Instagram → website → kalau tidak ada keduanya, link “Cari IG” (pencarian Google)."],
  ["Kontak", "HP: https://wa.me/62…, kantor: tel:+62…. Kosong kalau tidak ditemukan."],
  ["Gambar", "Link galeri foto tempat itu (maksimal 6 foto, foto menu/layanan di depan). Hanya bisa dibuka selama server menyala."],
  ["Alasan", "Jumlah foto, kisaran harga dari website, dan catatan data yang kosong, mis. “tanpa nomor telepon”."],
];

const NOTES = [
  "Data OpenStreetMap dikelola komunitas, jadi kontak bisa kosong atau sudah tidak berlaku. Cek ulang sebelum menghubungi.",
  "Restoran dan cafe biasanya lengkap. Kategori seperti salon dan bengkel lebih sering tanpa kontak dan tanpa website.",
  "Foto hanya diambil dari website tempat usaha, bukan dari Instagram. Label Menu ditentukan otomatis (tanpa AI), jadi sesekali bisa keliru.",
  "Filter harga hanya bisa membaca harga yang tertulis sebagai teks di website. Harga di dalam gambar atau PDF menu tidak terbaca.",
  "Kalau hasil dibagikan ke luar tim, cantumkan “© OpenStreetMap contributors”.",
];

function triggerDownload(url) {
  const link = document.createElement("a");
  link.href = url;
  link.download = "";
  document.body.appendChild(link);
  link.click();
  link.remove();
}

export default function App() {
  const [health, setHealth] = useState(null);
  const { toasts, push, dismiss } = useToasts();
  const resultRef = useRef(null);

  const { job, start, reset } = useScrapeJob({
    onDone: (done) => {
      triggerDownload(fileUrl(done.id, "csv"));
      push("success", `Selesai: ${done.rows.length} data “${done.keyword}” di ${done.area}. CSV otomatis terdownload.`);
      setTimeout(() => resultRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 100);
    },
    onFail: (message) => push("error", message || "Scraping gagal. Cek logs/scraper.log."),
  });

  useEffect(() => {
    getHealth()
      .then(setHealth)
      .catch((error) => setHealth({ ok: false, detail: error.message }));
  }, []);

  const running = job?.status === "queued" || job?.status === "running";
  const phase = !job ? 1 : running ? 2 : 3;

  async function handleSubmit(values) {
    try {
      await start(values);
      push("info", `Scraping “${values.keyword}” di ${values.area} dimulai.`);
    } catch (error) {
      push("error", error.message);
    }
  }

  return (
    <div className="page">
      <Navbar health={health} />

      <main className="container">
        <section className="hero fade-up">
          <span className="eyebrow">Tool internal</span>
          <h1 className="h1">
            Scraper data <span className="accent">tempat usaha</span>
          </h1>
          <p className="lead">
            Kumpulkan daftar calon partner (restoran, cafe, salon, atau kategori apa saja) di satu area, lengkap dengan link
            Maps, Instagram, WhatsApp, dan foto. Hasilnya langsung terdownload sebagai CSV.
          </p>
          <div className="pills">
            <span className="pill">Sumber: OpenStreetMap</span>
            <span className="pill">Tanpa API key &amp; tanpa biaya</span>
            <span className="pill">Output: CSV · XLSX · ZIP</span>
            {health?.base_url && <span className="pill">Link foto: {health.base_url}</span>}
          </div>
        </section>

        {health && !health.ok && (
          <p className="notice notice--error">⚠️ Server belum siap: {health.detail || "tidak bisa dihubungi."}</p>
        )}

        <section id="cari" className="card form-card fade-up">
          <div className="form-card__top">
            <h2 className="h2">Parameter pencarian</h2>
            <div className="phase">
              <div className="phase-bars" aria-hidden="true">
                {[1, 2, 3].map((n) => (
                  <span key={n} className={n <= phase ? "is-on" : ""} />
                ))}
              </div>
              <span className="muted small">{["Isi form", "Scraping", "Selesai"][phase - 1]}</span>
            </div>
          </div>
          <SearchForm disabled={running} onSubmit={handleSubmit} />
        </section>

        {job && (
          <section className="fade-up" ref={resultRef}>
            {job.status === "done" ? <Results job={job} /> : <ProgressCard job={job} onRetry={reset} />}
          </section>
        )}

        <section id="cara" className="how">
          <h2 className="h2">Cara kerja</h2>
          <ol className="steps">
            {STEPS.map((text, index) => (
              <li key={text} className="step">
                <span className="step__num">{index + 1}</span>
                <p>{text}</p>
              </li>
            ))}
          </ol>
        </section>

        <section id="kolom" className="how">
          <h2 className="h2">Arti kolom output</h2>
          <div className="card columns-card">
            <dl className="columns">
              {COLUMNS.map(([name, text]) => (
                <div key={name} className="columns__row">
                  <dt>{name}</dt>
                  <dd>{text}</dd>
                </div>
              ))}
            </dl>
          </div>
        </section>

        <section className="how">
          <h2 className="h2">Catatan pemakaian</h2>
          <ul className="notes">
            {NOTES.map((text) => (
              <li key={text}>{text}</li>
            ))}
          </ul>
        </section>
      </main>

      <footer className="footer">
        <div className="container muted small">
          ScrapIn · Tool internal · Data ©{" "}
          <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">
            OpenStreetMap contributors
          </a>{" "}
          (ODbL) · Log: <code>logs/scraper.log</code>
        </div>
      </footer>

      <Toasts toasts={toasts} onDismiss={dismiss} />
    </div>
  );
}
