import { useNavigate } from 'react-router-dom'
import { ExternalLink, RefreshCw, ShoppingCart, Store, Globe } from 'lucide-react'
import type { Monitor } from '../types'
import { formatCurrency, formatDate, sourceLabel } from '../lib/utils'
import { Badge } from './ui/badge'
import { Button } from './ui/button'
import { Switch } from './ui/switch'

interface MonitorCardProps {
  monitor: Monitor
  onToggleAlerts: (id: number) => void
  onCheckNow: (id: number) => void
  onDelete: (id: number) => void
}

function SourceIcon({ source }: { source: string }) {
  switch (source) {
    case 'tcgplayer':
      return <Store className="h-4 w-4" />
    case 'ebay':
      return <ShoppingCart className="h-4 w-4" />
    case 'manapool':
      return <Globe className="h-4 w-4" />
    default:
      return null
  }
}

function StatusBadge({ status }: { status: string | null }) {
  if (!status) return <Badge variant="secondary">Pending</Badge>
  switch (status) {
    case 'available':
      return <Badge className="bg-green-600 hover:bg-green-600/80">Available</Badge>
    case 'unavailable':
      return <Badge variant="secondary">Unavailable</Badge>
    case 'error':
      return <Badge variant="destructive">Error</Badge>
    default:
      return <Badge variant="secondary">{status}</Badge>
  }
}

export function MonitorCard({ monitor, onToggleAlerts, onCheckNow, onDelete }: MonitorCardProps) {
  const navigate = useNavigate()

  const priceRange = [
    monitor.min_price != null ? `$${monitor.min_price.toFixed(2)}` : null,
    monitor.max_price != null ? `$${monitor.max_price.toFixed(2)}` : null,
  ]
    .filter(Boolean)
    .join(' - ')

  return (
    <div className="rounded-lg border bg-card text-card-foreground shadow-sm p-5 hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between mb-3">
        <div
          className="flex items-center gap-2 cursor-pointer hover:text-primary transition-colors"
          onClick={() => navigate(`/monitors/${monitor.id}`)}
        >
          <SourceIcon source={monitor.source} />
          <h3 className="font-semibold text-base">{monitor.name}</h3>
        </div>
        <StatusBadge status={monitor.last_status} />
      </div>

      <div className="space-y-2 text-sm text-muted-foreground mb-4">
        <div className="flex justify-between">
          <span>Source</span>
          <span className="font-medium text-foreground">{sourceLabel(monitor.source)}</span>
        </div>
        <div className="flex justify-between">
          <span>Last Price</span>
          <span className="font-medium text-foreground">{formatCurrency(monitor.last_price)}</span>
        </div>
        {priceRange && (
          <div className="flex justify-between">
            <span>Target Range</span>
            <span className="font-medium text-foreground">{priceRange}</span>
          </div>
        )}
        <div className="flex justify-between">
          <span>Last Checked</span>
          <span className="font-medium text-foreground">{formatDate(monitor.last_checked_at)}</span>
        </div>
      </div>

      <div className="flex items-center justify-between pt-3 border-t">
        <div className="flex items-center gap-2">
          <Switch
            checked={monitor.alerts_enabled}
            onCheckedChange={() => onToggleAlerts(monitor.id)}
          />
          <span className="text-xs text-muted-foreground">
            {monitor.alerts_enabled ? 'Alerts on' : 'Alerts off'}
          </span>
        </div>
        <div className="flex gap-1">
          <Button variant="ghost" size="icon" onClick={() => onCheckNow(monitor.id)} title="Check now">
            <RefreshCw className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => {
              const url = monitor.source === 'ebay' && !monitor.url.startsWith('http')
                ? `https://www.ebay.com/sch/i.html?_nkw=${encodeURIComponent(monitor.url)}&LH_BIN=1&LH_PrefLoc=1`
                : monitor.url
              window.open(url, '_blank')
            }}
            title="Open listing"
          >
            <ExternalLink className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="text-destructive hover:text-destructive"
            onClick={() => onDelete(monitor.id)}
            title="Delete"
          >
            <span className="text-sm font-bold">X</span>
          </Button>
        </div>
      </div>
    </div>
  )
}
