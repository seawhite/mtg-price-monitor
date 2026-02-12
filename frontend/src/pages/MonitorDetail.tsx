import { useEffect, useState, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, ExternalLink, RefreshCw } from 'lucide-react'
import type { Monitor, MonitorCreate, MonitorUpdate, PriceHistory } from '../types'
import { api } from '../lib/api'
import { formatCurrency, formatDate, sourceLabel } from '../lib/utils'
import { Button } from '../components/ui/button'
import { Badge } from '../components/ui/badge'
import { Switch } from '../components/ui/switch'
import { PriceChart } from '../components/PriceChart'
import { MonitorForm } from '../components/MonitorForm'

export function MonitorDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [monitor, setMonitor] = useState<Monitor | null>(null)
  const [history, setHistory] = useState<PriceHistory[]>([])
  const [loading, setLoading] = useState(true)
  const [historyLoading, setHistoryLoading] = useState(true)
  const [editOpen, setEditOpen] = useState(false)
  const [historyDays, setHistoryDays] = useState(7)

  const monitorId = parseInt(id || '0')

  const fetchMonitor = useCallback(async () => {
    try {
      const data = await api.getMonitor(monitorId)
      setMonitor(data)
    } catch (err) {
      console.error('Failed to fetch monitor:', err)
    } finally {
      setLoading(false)
    }
  }, [monitorId])

  const fetchHistory = useCallback(async () => {
    setHistoryLoading(true)
    try {
      const data = await api.getHistory(monitorId, historyDays)
      setHistory(data)
    } catch (err) {
      console.error('Failed to fetch history:', err)
    } finally {
      setHistoryLoading(false)
    }
  }, [monitorId, historyDays])

  useEffect(() => {
    fetchMonitor()
    fetchHistory()
    const interval = setInterval(() => {
      fetchMonitor()
      fetchHistory()
    }, 15000)
    return () => clearInterval(interval)
  }, [fetchMonitor, fetchHistory])

  const handleUpdate = async (data: MonitorCreate) => {
    try {
      const update: MonitorUpdate = {
        name: data.name,
        url: data.url,
        min_price: data.min_price,
        max_price: data.max_price,
        alerts_enabled: data.alerts_enabled,
      }
      await api.updateMonitor(monitorId, update)
      setEditOpen(false)
      fetchMonitor()
    } catch (err) {
      console.error('Failed to update monitor:', err)
    }
  }

  const handleToggleAlerts = async () => {
    try {
      await api.toggleAlerts(monitorId)
      fetchMonitor()
    } catch (err) {
      console.error('Failed to toggle alerts:', err)
    }
  }

  const handleCheckNow = async () => {
    try {
      await api.checkNow(monitorId)
      setTimeout(() => {
        fetchMonitor()
        fetchHistory()
      }, 2000)
    } catch (err) {
      console.error('Failed to check now:', err)
    }
  }

  if (loading) {
    return <div className="text-center py-12 text-muted-foreground">Loading...</div>
  }

  if (!monitor) {
    return <div className="text-center py-12 text-muted-foreground">Monitor not found.</div>
  }

  const listingUrl =
    monitor.source === 'ebay' && !monitor.url.startsWith('http')
      ? `https://www.ebay.com/sch/i.html?_nkw=${encodeURIComponent(monitor.url)}&LH_BIN=1&LH_PrefLoc=1`
      : monitor.url

  const priceRange = [
    monitor.min_price != null ? `$${monitor.min_price.toFixed(2)}` : null,
    monitor.max_price != null ? `$${monitor.max_price.toFixed(2)}` : null,
  ]
    .filter(Boolean)
    .join(' - ')

  return (
    <div>
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <Button variant="ghost" size="icon" onClick={() => navigate('/')}>
          <ArrowLeft className="h-5 w-5" />
        </Button>
        <div className="flex-1">
          <h1 className="text-2xl font-bold">{monitor.name}</h1>
          <p className="text-muted-foreground text-sm">{sourceLabel(monitor.source)}</p>
        </div>
        <Button variant="outline" onClick={() => setEditOpen(true)}>
          Edit
        </Button>
      </div>

      {/* Info Grid */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4 mb-8">
        <div className="rounded-lg border bg-card p-4">
          <p className="text-sm text-muted-foreground">Last Price</p>
          <p className="text-2xl font-bold">{formatCurrency(monitor.last_price)}</p>
        </div>
        <div className="rounded-lg border bg-card p-4">
          <p className="text-sm text-muted-foreground">Status</p>
          <div className="mt-1">
            {monitor.last_status === 'available' ? (
              <Badge className="bg-green-600 hover:bg-green-600/80">Available</Badge>
            ) : monitor.last_status === 'error' ? (
              <Badge variant="destructive">Error</Badge>
            ) : (
              <Badge variant="secondary">{monitor.last_status || 'Pending'}</Badge>
            )}
          </div>
        </div>
        <div className="rounded-lg border bg-card p-4">
          <p className="text-sm text-muted-foreground">Target Range</p>
          <p className="text-lg font-semibold">{priceRange || 'Not set'}</p>
        </div>
        <div className="rounded-lg border bg-card p-4">
          <p className="text-sm text-muted-foreground">Last Checked</p>
          <p className="text-sm font-medium">{formatDate(monitor.last_checked_at)}</p>
        </div>
      </div>

      {/* Actions Bar */}
      <div className="flex items-center gap-4 mb-8 p-4 rounded-lg border bg-card">
        <div className="flex items-center gap-2">
          <Switch checked={monitor.alerts_enabled} onCheckedChange={handleToggleAlerts} />
          <span className="text-sm">{monitor.alerts_enabled ? 'Alerts enabled' : 'Alerts disabled'}</span>
        </div>
        <div className="flex-1" />
        <Button variant="outline" size="sm" onClick={handleCheckNow}>
          <RefreshCw className="h-4 w-4 mr-2" />
          Check Now
        </Button>
        <Button variant="outline" size="sm" onClick={() => window.open(listingUrl, '_blank')}>
          <ExternalLink className="h-4 w-4 mr-2" />
          View Listing
        </Button>
      </div>

      {/* Price Chart */}
      <div className="rounded-lg border bg-card p-6 mb-8">
        <h2 className="text-lg font-semibold mb-4">Price History</h2>
        <PriceChart history={history} isLoading={historyLoading} />
      </div>

      {/* Recent Checks Table */}
      <div className="rounded-lg border bg-card p-6">
        <h2 className="text-lg font-semibold mb-4">Recent Checks</h2>
        {history.length === 0 ? (
          <p className="text-muted-foreground text-sm">No checks recorded yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b">
                  <th className="text-left py-2 px-3 font-medium">Time</th>
                  <th className="text-left py-2 px-3 font-medium">Price</th>
                  <th className="text-left py-2 px-3 font-medium">Available</th>
                  <th className="text-left py-2 px-3 font-medium">Details</th>
                </tr>
              </thead>
              <tbody>
                {[...history].reverse().slice(0, 50).map((h) => (
                  <tr key={h.id} className="border-b last:border-0">
                    <td className="py-2 px-3">{formatDate(h.checked_at)}</td>
                    <td className="py-2 px-3">{formatCurrency(h.price)}</td>
                    <td className="py-2 px-3">
                      {h.available ? (
                        <span className="text-green-600 font-medium">Yes</span>
                      ) : (
                        <span className="text-muted-foreground">No</span>
                      )}
                    </td>
                    <td className="py-2 px-3 text-muted-foreground max-w-[200px] truncate">
                      {h.source_detail || '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Edit Form */}
      {monitor && (
        <MonitorForm
          open={editOpen}
          onOpenChange={setEditOpen}
          onSubmit={handleUpdate}
          initialData={{
            name: monitor.name,
            source: monitor.source,
            url: monitor.url,
            min_price: monitor.min_price,
            max_price: monitor.max_price,
            alerts_enabled: monitor.alerts_enabled,
          }}
          isEdit
        />
      )}
    </div>
  )
}
