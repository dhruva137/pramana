import { NavLink, Outlet } from "react-router-dom";
import { API_BASE } from "../lib/api";
import { loadKeys, modeLabel } from "../lib/keys";
import { SandboxBadge } from "./SandboxBadge";

const LINKS = [
  { to: "/", label: "Overview", end: true },
  { to: "/live", label: "Command" },
  { to: "/proof", label: "Proofs" },
  { to: "/bench", label: "Bench" },
  { to: "/history", label: "Episodes" },
  { to: "/integrations", label: "Integrate" },
  { to: "/settings", label: "Settings" },
] as const;

export function Layout() {
  // Re-read each render so /settings saves update the MOCK/LIVE chip.
  const keys = loadKeys();
  const mode = modeLabel(keys);

  return (
    <>
      <SandboxBadge />
      <div className="app-shell">
        <header className="topbar">
          <div className="brand-block">
            <div className="brand-row">
              <span className="brand-mark" aria-hidden />
              <div className="brand">Pramana</div>
            </div>
            <div className="brand-sub">Intent custody · control plane</div>
          </div>
          <nav className="nav" aria-label="Primary">
            {LINKS.map((l) => (
              <NavLink
                key={l.to}
                to={l.to}
                end={"end" in l ? l.end : false}
                className={({ isActive }) => (isActive ? "active" : undefined)}
              >
                {l.label}
              </NavLink>
            ))}
          </nav>
          <div className="topbar-actions">
            <span className={`mode-chip ${mode.toLowerCase()}`} title={API_BASE}>
              {mode}
            </span>
          </div>
        </header>
        <main className="main">
          <Outlet context={{ keys }} />
        </main>
      </div>
    </>
  );
}
