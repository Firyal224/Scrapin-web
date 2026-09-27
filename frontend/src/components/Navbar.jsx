export default function Navbar({ health }) {
  const ready = health?.ok;
  const label = health === null ? "Mengecek server..." : ready ? "Server siap" : "Server belum siap";

  return (
    <header className="nav">
      <div className="container nav__inner">
        <a href="/" className="brand">
          <span className="brand__logo" aria-hidden="true">
            <svg viewBox="0 0 53 53" width="18" height="18" fill="none" stroke="#EFECFF" strokeWidth="4.3" strokeLinecap="round">
              <circle cx="12" cy="12" r="6" />
              <circle cx="41" cy="12" r="6" />
              <circle cx="12" cy="41" r="6" />
              <circle cx="41" cy="41" r="6" />
              <path d="M16 16l21 21M37 16L16 37" />
            </svg>
          </span>
          <span className="brand__name">ScrapIn</span>
          <span className="tag">Internal</span>
        </a>
        <nav className="nav__links">
          <a href="#cari">Cari data</a>
          <a href="#cara">Cara kerja</a>
          <a href="#kolom">Arti kolom</a>
        </nav>
        <span className={`status-pill ${ready ? "is-ok" : health === null ? "" : "is-bad"}`} title={health?.detail || ""}>
          <span className="dot" /> {label}
        </span>
      </div>
    </header>
  );
}
