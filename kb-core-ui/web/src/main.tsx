import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import './index.css'
import App from './App.tsx'
import { HomeView } from './pages/HomeView.tsx'
import { ModuleView } from './pages/ModuleView.tsx'
import { SymbolDetailView } from './pages/SymbolDetailView.tsx'
import { GraphPageView } from './pages/GraphPageView.tsx'
import { BotsView } from './pages/BotsView.tsx'
import { MemoryView } from './pages/MemoryView.tsx'
import { WorkspaceChatRoute } from './routes/WorkspaceChatRoute.tsx'
import { IngestionView } from './pages/IngestionView.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<App />}>
          <Route index element={<HomeView />} />
          <Route path="file/*" element={<ModuleView />} />
          <Route path="symbol/:id" element={<SymbolDetailView />} />
          <Route path="graph" element={<GraphPageView />} />
          <Route path="bots" element={<BotsView />} />
          <Route path="memory" element={<MemoryView />} />
          <Route path="chat" element={<WorkspaceChatRoute />} />
          <Route path="ingest" element={<IngestionView />} />
        </Route>
      </Routes>
    </BrowserRouter>
  </StrictMode>,
)
