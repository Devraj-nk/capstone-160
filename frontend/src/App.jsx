import { NavLink, Route, Routes } from "react-router-dom";
import ReviewPage from "./pages/ReviewPage.jsx";
import DashboardPage from "./pages/DashboardPage.jsx";
import { ReportListPage, ReportPage } from "./pages/ReportPage.jsx";

export default function App() {
  return (
    <div>
      <nav>
        <NavLink to="/">Review</NavLink> | <NavLink to="/dashboard">Dashboard</NavLink> |{" "}
        <NavLink to="/reports">Reports</NavLink>
      </nav>
      <Routes>
        <Route path="/" element={<ReviewPage />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/reports" element={<ReportListPage />} />
        <Route path="/reports/:day" element={<ReportPage />} />
      </Routes>
    </div>
  );
}
