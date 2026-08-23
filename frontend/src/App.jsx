import { NavLink, Route, Routes } from "react-router-dom";
import ReviewPage from "./pages/ReviewPage.jsx";
import DashboardPage from "./pages/DashboardPage.jsx";

export default function App() {
  return (
    <div>
      <nav>
        <NavLink to="/">Review</NavLink> | <NavLink to="/dashboard">Dashboard</NavLink>
      </nav>
      <Routes>
        <Route path="/" element={<ReviewPage />} />
        <Route path="/dashboard" element={<DashboardPage />} />
      </Routes>
    </div>
  );
}
