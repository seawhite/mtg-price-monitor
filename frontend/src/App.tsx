import { Routes, Route } from 'react-router-dom'
import { Dashboard } from './pages/Dashboard'
import { MonitorDetail } from './pages/MonitorDetail'

export default function App() {
  return (
    <div className="min-h-screen bg-background">
      <div className="container mx-auto py-8 px-4">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/monitors/:id" element={<MonitorDetail />} />
        </Routes>
      </div>
    </div>
  )
}
