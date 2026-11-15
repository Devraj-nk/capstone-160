import { Link, NavLink, Route, Routes } from "react-router-dom";
import ReviewPage from "./pages/ReviewPage.jsx";
import DashboardPage from "./pages/DashboardPage.jsx";
import { ReportListPage, ReportPage } from "./pages/ReportPage.jsx";

export default function App() {
  return (
    <>
      <header className="shell-nav">
        <Link to="/" className="shell-brand">
          <span className="shell-brand-mark" />
          <span className="shell-brand-text">Crisis Monitor</span>
        </Link>
        <nav className="shell-links" aria-label="Main">
          <NavLink to="/" end>
            Review
          </NavLink>
          <NavLink to="/dashboard">Dashboard</NavLink>
          <NavLink to="/reports">Reports</NavLink>
        </nav>
      </header>
      <main className="shell-main">
        <Routes>
          <Route path="/" element={<ReviewPage />} />
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/reports" element={<ReportListPage />} />
          <Route path="/reports/:day" element={<ReportPage />} />
        </Routes>
      </main>
    </>
  );
}
