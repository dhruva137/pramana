import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { Benchmark } from "./pages/Benchmark";
import { Dashboard } from "./pages/Dashboard";
import { History } from "./pages/History";
import { Integrations } from "./pages/Integrations";
import { LiveEpisode } from "./pages/LiveEpisode";
import { ProofViewer } from "./pages/ProofViewer";
import { Settings } from "./pages/Settings";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="live" element={<LiveEpisode />} />
          <Route path="proof" element={<ProofViewer />} />
          <Route path="bench" element={<Benchmark />} />
          <Route path="history" element={<History />} />
          <Route path="integrations" element={<Integrations />} />
          <Route path="settings" element={<Settings />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
