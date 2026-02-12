import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ExternalLink, RefreshCw, ShoppingCart, Store, Globe, BarChart3 } from 'lucide-react'
import { LineChart, Line, ResponsiveContainer, Tooltip } from 'recharts'
import type { Monitor, PriceHistory } from '../types'
import { formatCurrency, formatDate, parseUTC, sourceLabel } from '../lib/utils'
import { Badge } from './ui/badge'
import { Button } from './ui/button'
import { Switch } from './ui/switch'
import { PriceBreakdownDialog } from './PriceBreakdownDialog'

interface MonitorCardProps {
  monitor: Monitor
  priceHistory?: PriceHistory[]
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

export function MonitorCard({ monitor, priceHistory = [], onToggleAlerts, onCheckNow, onDelete }: MonitorCardProps) {
  const navigate = useNavigate()
  const [breakdownOpen, setBreakdownOpen] = useState(false)

  const alertRange = [
    monitor.min_price != null ? `$${monitor.min_price.toFixed(2)}` : null,
    monitor.max_price != null ? `$${monitor.max_price.toFixed(2)}` : null,
  ]
    .filter(Boolean)
    .join(' - ')

  const trackRange = [
    monitor.track_min_price != null ? `$${monitor.track_min_price.toFixed(2)}` : null,
    monitor.track_max_price != null ? `$${monitor.track_max_price.toFixed(2)}` : null,
  ]
    .filter(Boolean)
    .join(' - ')

  // Aggregate into hourly buckets to smooth out per-listing fluctuations
  const sparkData = (() => {
    const priced = priceHistory.filter((h) => h.price !== null && h.checked_at)
    if (!priced.length) return []
    const buckets: Record<string, { prices: number[]; label: string }> = {}
    for (const h of priced) {
      const ts = parseUTC(h.checked_at!).getTime()
      const hourTs = Math.floor(ts / 3600000) * 3600000
      const key = String(hourTs)
      if (!buckets[key]) {
        buckets[key] = {
          prices: [],
          label: new Date(hourTs).toLocaleString('en-US', {
            month: 'short', day: 'numeric', hour: 'numeric',
          }),
        }
      }
      buckets[key].prices.push(h.price!)
    }
    return Object.entries(buckets)
      .sort(([a], [b]) => Number(a) - Number(b))
      .map(([, bucket]) => ({
        time: bucket.label,
        price: Math.min(...bucket.prices),
      }))
  })()

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

      <div className="space-y-2 text-sm text-muted-foreground mb-3">
        <div className="flex justify-between">
          <span>Source</span>
          <span className="font-medium text-foreground">{sourceLabel(monitor.source)}</span>
        </div>
        <div className="flex justify-between">
          <span>Last Price</span>
          <span className="font-medium text-foreground">{formatCurrency(monitor.last_price)}</span>
        </div>
        {trackRange && (
          <div className="flex justify-between">
            <span>Track Range</span>
            <span className="font-medium text-foreground">{trackRange}</span>
          </div>
        )}
        {alertRange && (
          <div className="flex justify-between">
            <span>Alert Range</span>
            <span className="font-medium text-foreground">{alertRange}</span>
          </div>
        )}
        <div className="flex justify-between">
          <span>Last Checked</span>
          <span className="font-medium text-foreground">{formatDate(monitor.last_checked_at)}</span>
        </div>
      </div>

      {/* Sparkline */}
      <div className="mb-3 border-t pt-3">
        {sparkData.length > 1 ? (
          <div className="flex items-center gap-1">
            <div className="flex-1">
              <ResponsiveContainer width="100%" height={60}>
                <LineChart data={sparkData}>
                  <Tooltip
                    formatter={(value: number) => [`$${value.toFixed(2)}`, 'Price']}
                    labelFormatter={(_: unknown, payload: Array<{ payload?: { time?: string } }>) =>
                      payload?.[0]?.payload?.time ?? ''
                    }
                    labelStyle={{ color: 'hsl(var(--foreground))' }}
                    contentStyle={{
                      backgroundColor: 'hsl(var(--card))',
                      border: '1px solid hsl(var(--border))',
                      borderRadius: '0.375rem',
                      fontSize: '0.75rem',
                    }}
                  />
                  <Line
                    type="monotone"
                    dataKey="price"
                    stroke="hsl(var(--primary))"
                    strokeWidth={1.5}
                    dot={false}
                    activeDot={{ r: 3 }}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 shrink-0"
              onClick={() => setBreakdownOpen(true)}
              title="Price breakdown"
            >
              <BarChart3 className="h-4 w-4" />
            </Button>
          </div>
        ) : (
          <div className="flex items-center justify-between">
            <p className="text-xs text-muted-foreground">No chart data yet</p>
            {priceHistory.length > 0 && (
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 shrink-0"
                onClick={() => setBreakdownOpen(true)}
                title="Price breakdown"
              >
                <BarChart3 className="h-4 w-4" />
              </Button>
            )}
          </div>
        )}
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

      <PriceBreakdownDialog
        open={breakdownOpen}
        onOpenChange={setBreakdownOpen}
        monitorName={monitor.name}
        history={priceHistory}
      />
    </div>
  )
}
