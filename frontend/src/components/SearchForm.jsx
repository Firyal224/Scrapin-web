import { useState } from "react";

const KEYWORDS = [
  { icon: "🍽️", label: "Restoran" },
  { icon: "☕", label: "Cafe" },
  { icon: "💇", label: "Salon" },
  { icon: "🏋️", label: "Gym" },
  { icon: "🦷", label: "Klinik gigi" },
  { icon: "🏨", label: "Hotel" },
];
const AREAS = ["Jakarta Selatan", "Jakarta Pusat", "Tangerang Selatan", "Bandung", "Surabaya"];
const MAX_OPTIONS = [10, 20, 40, 60];
const TEXT_PATTERN = /^[\p{L}\p{N}\s&'.,/()-]{2,80}$/u;
const MAX_PRICE = 10_000_000;
const PRICE_PRESETS = [
  { label: "Di bawah 50rb", min: "", max: 50000 },
  { label: "50rb sampai 100rb", min: 50000, max: 100000 },
  { label: "100rb sampai 250rb", min: 100000, max: 250000 },
  { label: "Di atas 250rb", min: 250000, max: "" },
];

export function parsePrice(text) {
  const digits = String(text ?? "").replace(/\D/g, "");
  return digits ? Number(digits) : null;
}

export function formatPrice(value) {
  return value === null || value === "" || value === undefined ? "" : Number(value).toLocaleString("id-ID");
}

export function validate({ keyword, area, maxResults, priceMin, priceMax }) {
  if (!TEXT_PATTERN.test(keyword.trim())) return "Keyword wajib 2-80 karakter (huruf, angka, spasi, & ' . , / - ( )).";
  if (!TEXT_PATTERN.test(area.trim())) return "Area wajib 2-80 karakter (huruf, angka, spasi, & ' . , / - ( )).";
  if (!Number.isInteger(maxResults) || maxResults < 1 || maxResults > 60) return "Maks hasil harus antara 1 dan 60.";
  if ([priceMin, priceMax].some((p) => p !== null && p > MAX_PRICE)) return "Harga maksimal Rp 10.000.000.";
  if (priceMin !== null && priceMax !== null && priceMin > priceMax)
    return "Harga minimum tidak boleh lebih besar dari harga maksimum.";
  return "";
}

export default function SearchForm({ disabled, onSubmit }) {
  const [keyword, setKeyword] = useState("");
  const [area, setArea] = useState("");
  const [maxResults, setMaxResults] = useState(20);
  const [priceMin, setPriceMin] = useState("");
  const [priceMax, setPriceMax] = useState("");
  const [error, setError] = useState("");

  function applyPreset(preset) {
    setPriceMin(formatPrice(preset.min));
    setPriceMax(formatPrice(preset.max));
  }

  const isPreset = (preset) => priceMin === formatPrice(preset.min) && priceMax === formatPrice(preset.max);
  const hasPriceFilter = parsePrice(priceMin) !== null || parsePrice(priceMax) !== null;

  function handleSubmit(event) {
    event.preventDefault();
    const values = {
      keyword: keyword.trim(),
      area: area.trim(),
      maxResults,
      priceMin: parsePrice(priceMin),
      priceMax: parsePrice(priceMax),
    };
    const message = validate(values);
    setError(message);
    if (!message) onSubmit(values);
  }

  return (
    <form className="search" onSubmit={handleSubmit} noValidate>
      <div className="field">
        <label htmlFor="keyword">
          <span className="field__step">1</span> Keyword bisnis
        </label>
        <input
          id="keyword"
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          placeholder="Bebas, mis. restoran, cafe, salon, bengkel, seblak..."
          maxLength={80}
          autoComplete="off"
          disabled={disabled}
        />
        <div className="chips">
          {KEYWORDS.map(({ icon, label }) => (
            <button
              type="button"
              key={label}
              className={`chip ${keyword.toLowerCase() === label.toLowerCase() ? "is-active" : ""}`}
              onClick={() => setKeyword(label)}
              disabled={disabled}
            >
              {icon} {label}
            </button>
          ))}
        </div>
      </div>

      <div className="field">
        <label htmlFor="area">
          <span className="field__step">2</span> Area
        </label>
        <input
          id="area"
          value={area}
          onChange={(e) => setArea(e.target.value)}
          placeholder="Kota/kecamatan, mis. Jakarta Selatan, Kemang, Bandung"
          maxLength={80}
          autoComplete="off"
          disabled={disabled}
        />
        <div className="chips">
          {AREAS.map((label) => (
            <button
              type="button"
              key={label}
              className={`chip ${area === label ? "is-active" : ""}`}
              onClick={() => setArea(label)}
              disabled={disabled}
            >
              📍 {label}
            </button>
          ))}
        </div>
      </div>

      <div className="field">
        <label htmlFor="maxResults">
          <span className="field__step">3</span> Maks hasil <strong className="accent">{maxResults}</strong>
        </label>
        <div className="range">
          <input
            id="maxResults"
            type="range"
            min={1}
            max={60}
            value={maxResults}
            onChange={(e) => setMaxResults(Number(e.target.value))}
            disabled={disabled}
          />
          <div className="segmented">
            {MAX_OPTIONS.map((value) => (
              <button
                type="button"
                key={value}
                className={maxResults === value ? "is-active" : ""}
                onClick={() => setMaxResults(value)}
                disabled={disabled}
              >
                {value}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="field">
        <label htmlFor="priceMin">
          <span className="field__step">4</span> Range harga <span className="muted small">(opsional)</span>
        </label>
        <div className="price-range">
          <div className="price-input">
            <span>Rp</span>
            <input
              id="priceMin"
              inputMode="numeric"
              value={priceMin}
              onChange={(e) => setPriceMin(formatPrice(parsePrice(e.target.value)))}
              placeholder="Minimum"
              maxLength={12}
              autoComplete="off"
              disabled={disabled}
            />
          </div>
          <span className="muted small">sampai</span>
          <div className="price-input">
            <span>Rp</span>
            <input
              id="priceMax"
              aria-label="Harga maksimum"
              inputMode="numeric"
              value={priceMax}
              onChange={(e) => setPriceMax(formatPrice(parsePrice(e.target.value)))}
              placeholder="Maksimum"
              maxLength={12}
              autoComplete="off"
              disabled={disabled}
            />
          </div>
        </div>
        <div className="chips">
          {PRICE_PRESETS.map((preset) => (
            <button
              type="button"
              key={preset.label}
              className={`chip ${isPreset(preset) ? "is-active" : ""}`}
              onClick={() => applyPreset(preset)}
              disabled={disabled}
            >
              {preset.label}
            </button>
          ))}
          {hasPriceFilter && (
            <button type="button" className="chip" onClick={() => applyPreset({ min: "", max: "" })} disabled={disabled}>
              ✕ Hapus filter harga
            </button>
          )}
        </div>
        <p className="hint hint--field">
          Harga dibaca dari teks “Rp…” di website tempat usaha. Kalau diisi, hanya tempat yang harganya ditemukan dan masuk
          range yang ditampilkan, jadi hasil bisa jauh lebih sedikit dan prosesnya lebih lama.
        </p>
      </div>

      <p className="hint">
        Estimasi waktu {hasPriceFilter ? "1 sampai 4 menit" : "20 sampai 90 detik"}, tergantung jumlah hasil dan
        kecepatan server.
      </p>

      {error && (
        <p className="form-error" role="alert">
          ⚠️ {error}
        </p>
      )}

      <button type="submit" className="btn btn--primary btn--block" disabled={disabled}>
        {disabled ? "Sedang scraping..." : "Mulai scraping"}
      </button>
    </form>
  );
}
