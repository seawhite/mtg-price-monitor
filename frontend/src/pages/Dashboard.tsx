import { useEffect, useState, useCallback } from 'react'
import { Plus } from 'lucide-react'
import type { Monitor, MonitorCreate } from '../types'
import { api } from '../lib/api'
import { Button } from '../components/ui/button'
import { MonitorForm } from '../components/MonitorForm'
import { MonitorCard } from '../components/MonitorCard'

export function Dashboard() {
  const [monitors, setMonitors] = useState<Monitor[]>([])
  const [loading, setLoading] = useState(true)
  const [formOpen, setFormOpen] = useState(false)

  const fetchMonitors = useCallback(async () => {
    try {
      const data = await api.listMonitors()
      setMonitors(data)
    } catch (err) {
      console.error('Failed to fetch monitors:', err)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchMonitors()
    const interval = setInterval(fetchMonitors, 15000)
    return () => clearInterval(interval)
  }, [fetchMonitors])

  const handleCreate = async (data: MonitorCreate) => {
    try {
      await api.createMonitor(data)
      setFormOpen(false)
      fetchMonitors()
    } catch (err) {
      console.error('Failed to create monitor:', err)
    }
  }

  const handleToggleAlerts = async (id: number) => {
    try {
      await api.toggleAlerts(id)
      fetchMonitors()
    } catch (err) {
      console.error('Failed to toggle alerts:', err)
    }
  }

  const handleCheckNow = async (id: number) => {
    try {
      await api.checkNow(id)
      setTimeout(fetchMonitors, 2000)
    } catch (err) {
      console.error('Failed to check now:', err)
    }
  }

  const handleDelete = async (id: number) => {
    if (!confirm('Are you sure you want to delete this monitor?')) return
    try {
      await api.deleteMonitor(id)
      fetchMonitors()
    } catch (err) {
      console.error('Failed to delete monitor:', err)
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">MTG Price Monitor</h1>
          <p className="text-muted-foreground mt-1">
            Monitoring {monitors.length} card{monitors.length !== 1 ? 's' : ''} across TCGPlayer, eBay, and Manapool
          </p>
        </div>
        <Button onClick={() => setFormOpen(true)}>
          <Plus className="h-4 w-4 mr-2" />
          Add Monitor
        </Button>
      </div>

      {loading ? (
        <div className="text-center py-12 text-muted-foreground">Loading monitors...</div>
      ) : monitors.length === 0 ? (
        <div className="text-center py-12">
          <p className="text-muted-foreground mb-4">
            No monitors configured yet. Add your first card to start tracking prices.
          </p>
          <Button onClick={() => setFormOpen(true)}>
            <Plus className="h-4 w-4 mr-2" />
            Add Your First Monitor
          </Button>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {monitors.map((monitor) => (
            <MonitorCard
              key={monitor.id}
              monitor={monitor}
              onToggleAlerts={handleToggleAlerts}
              onCheckNow={handleCheckNow}
              onDelete={handleDelete}
            />
          ))}
        </div>
      )}

      <MonitorForm open={formOpen} onOpenChange={setFormOpen} onSubmit={handleCreate} />
    </div>
  )
}
