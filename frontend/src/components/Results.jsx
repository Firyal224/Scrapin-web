import { fileUrl, safeHref, safeImageSrc } from "../api.js";

const THUMBS = 3;

function LinkPill({ href, children }) {
  const safe = safeHref(href);
  if (!safe) return <span className="muted">—</span>;
  return (
    <a className="link-pill" href={safe} target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  );
}

function socialLabel(url) {
  if (url.includes("instagram.com")) return "📸 Instagram";
  if (url.startsWith("https://www.google.com/search")) return "🔎 Cari IG";
  return "🌐 Website";
}

function PhotoCell({ row }) {
  const photos = (row.Foto || []).map((p) => ({ ...p, src: safeImageSrc(p.src) })).filter((p) => p.src);
  const gallery = safeHref(row.Gambar);
  if (!photos.length || !gallery) return <span className="muted">—</span>;
  const menuCount = photos.filter((p) => p.menu).length;
  return (
    <div className="photo-cell">
      <a className="thumbs" href={gallery} target="_blank" rel="noopener noreferrer" title="Buka galeri">
        {photos.slice(0, THUMBS).map((photo) => (
          <span className="thumb-wrap" key={photo.src}>
            <img className="thumb" src={photo.src} alt={row.Nama} loading="lazy" />
            {photo.menu && <span className="thumb-badge">Menu</span>}
          </span>
        ))}
      </a>
      <a className="link-pill" href={gallery} target="_blank" rel="noopener noreferrer">
        🖼️ Galeri ({photos.length}
        {menuCount ? `, ${menuCount} menu` : ""})
      </a>
    </div>
  );
}

function contactLabel(url) {
  if (url.startsWith("https://wa.me/")) return "💬 WhatsApp";
  return "📞 Telepon";
}

export default function Results({ job }) {
  const rows = job.rows;
  const count = (predicate) => rows.filter(predicate).length;
  const stats = [
    { value: rows.length, label: `data · ${job.duration} detik` },
    { value: count((r) => r.Kontak), label: "punya kontak" },
    { value: count((r) => r.Sosmed?.includes("instagram.com")), label: "punya Instagram" },
    { value: count((r) => r.Foto?.length), label: "punya foto" },
    { value: count((r) => r.Foto?.some((p) => p.menu)), label: "punya foto menu/layanan" },
  ];
  const priceText = [job.price_min, job.price_max].some((v) => v !== null && v !== undefined)
    ? ` · harga ${job.price_min ? `Rp ${job.price_min.toLocaleString("id-ID")}` : "Rp 0"} sampai ${
        job.price_max ? `Rp ${job.price_max.toLocaleString("id-ID")}` : "tanpa batas"
      }`
    : "";

  return (
    <section className="results">
      <div className="results__head">
        <div>
          <h2 className="h2">Hasil</h2>
          <p className="muted">
            “{job.keyword}” di {job.area}
            {priceText} · sumber {job.source} · CSV sudah otomatis terdownload
          </p>
        </div>
        <div className="downloads">
          <a className="btn btn--primary" href={fileUrl(job.id, "csv")} download>
            ⬇ Download ulang CSV
          </a>
          <a className="btn btn--ghost" href={fileUrl(job.id, "xlsx")} download>
            XLSX
          </a>
          <a className="btn btn--ghost" href={fileUrl(job.id, "zip")} download>
            ZIP + foto
          </a>
        </div>
      </div>

      <div className="stats">
        {stats.map((s) => (
          <div className="stat" key={s.label}>
            <strong>{s.value}</strong>
            <span>{s.label}</span>
          </div>
        ))}
      </div>

      {job.warnings.length > 0 && (
        <p className="notice">
          ⚠️ Foto dari {job.warnings.length} tempat tidak bisa diunduh. Data lainnya tetap lengkap.
        </p>
      )}

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>Nama</th>
              <th>Der Treffpunkt</th>
              <th>Sosmed</th>
              <th>Kontak</th>
              <th>Gambar</th>
              <th>Alasan</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => {
              return (
                <tr key={`${row.Nama}-${index}`}>
                  <td className="muted">{index + 1}</td>
                  <td>
                    <div className="place-name">{row.Nama}</div>
                    <div className="muted small">{row.Alamat}</div>
                  </td>
                  <td>
                    <LinkPill href={row["Der Treffpunkt"]}>📍 Maps</LinkPill>
                  </td>
                  <td>
                    <LinkPill href={row.Sosmed}>{socialLabel(row.Sosmed)}</LinkPill>
                  </td>
                  <td>
                    <LinkPill href={row.Kontak}>{row.Kontak && contactLabel(row.Kontak)}</LinkPill>
                  </td>
                  <td>
                    <PhotoCell row={row} />
                  </td>
                  <td className="small">{row.Alasan}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
