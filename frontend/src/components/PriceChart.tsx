import { useState, useMemo, useEffect } from 'react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import type { PriceHistory } from '../types'
import { Button } from './ui/button'

interface PriceChartProps {
  history: PriceHistory[]
  isLoading?: boolean
  onRangeChange?: (days: number) => void
}

const TIME_RANGES = [
  { label: '7d', days: 7 },
  { label: '30d', days: 30 },
  { label: '1y', days: 365 },
  { label: '5y', days: 1825 },
]

const ALL_GRANULARITIES = [
  { label: '1m', minutes: 1 },
  { label: '5m', minutes: 5 },
  { label: '15m', minutes: 15 },
  { label: '1h', minutes: 60 },
  { label: '1d', minutes: 1440 },
  { label: '1w', minutes: 10080 },
]

// Which granularities are available for each range, and the default index
const RANGE_GRAN_CONFIG: Record<number, { available: number[]; defaultIdx: number }> = {
  7:    { available: [0, 1, 2, 3],    defaultIdx: 2 },  // 1m,5m,15m,1h → default 15m
  30:   { available: [1, 2, 3, 4],    defaultIdx: 2 },  // 5m,15m,1h,1d → default 1h
  365:  { available: [3, 4, 5],       defaultIdx: 1 },  // 1h,1d,1w → default 1d
  1825: { available: [4, 5],          defaultIdx: 1 },  // 1d,1w → default 1w
}

interface AggregatedPoint {
  time: string
  low: number
  high: number
  price: number
}

function aggregateHistory(history: PriceHistory[], granMinutes: number): AggregatedPoint[] {
  const priced = history.filter((h) => h.price !== null && h.checked_at)
  if (!priced.length) return []

  const buckets: Record<string, { prices: number[]; lows: number[]; highs: number[] }> = {}

  for (const h of priced) {
    const ts = new Date(h.checked_at!).getTime()
    const bucketTs = Math.floor(ts / (granMinutes * 60000)) * (granMinutes * 60000)
    const key = String(bucketTs)
    if (!buckets[key]) buckets[key] = { prices: [], lows: [], highs: [] }
    buckets[key].prices.push(h.price!)
    // Use server-side rollup low/high if available
    if (h.low != null) buckets[key].lows.push(h.low)
    if (h.high != null) buckets[key].highs.push(h.high)
  }

  return Object.entries(buckets)
    .sort(([a], [b]) => Number(a) - Number(b))
    .map(([key, bucket]) => {
      const d = new Date(Number(key))
      let fmt: string
      if (granMinutes >= 1440) {
        fmt = d.toLocaleString('en-US', { month: 'short', day: 'numeric', year: granMinutes >= 10080 ? 'numeric' : undefined })
      } else if (granMinutes >= 60) {
        fmt = d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric' })
      } else {
        fmt = d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
      }
      // Prefer server-side aggregates when present
      const low = bucket.lows.length ? Math.min(...bucket.lows) : Math.min(...bucket.prices)
      const high = bucket.highs.length ? Math.max(...bucket.highs) : Math.max(...bucket.prices)
      return {
        time: fmt,
        low,
        high,
        price: bucket.prices.reduce((a, b) => a + b, 0) / bucket.prices.length,
      }
    })
}

export function PriceChart({ history, isLoading, onRangeChange }: PriceChartProps) {
  const [rangeIdx, setRangeIdx] = useState(0)
  const currentDays = TIME_RANGES[rangeIdx].days
  const granConfig = RANGE_GRAN_CONFIG[currentDays] || RANGE_GRAN_CONFIG[7]
  const [granSelIdx, setGranSelIdx] = useState(granConfig.defaultIdx)

  // Auto-select default granularity when range changes
  useEffect(() => {
    const cfg = RANGE_GRAN_CONFIG[currentDays] || RANGE_GRAN_CONFIG[7]
    setGranSelIdx(cfg.defaultIdx)
  }, [currentDays])

  const activeGranMinutes = ALL_GRANULARITIES[granConfig.available[granSelIdx] ?? granConfig.available[0]].minutes

  const data = useMemo(
    () => aggregateHistory(history, activeGranMinutes),
    [history, activeGranMinutes]
  )

  if (isLoading) {
    return (
      <div className="h-[300px] flex items-center justify-center text-muted-foreground">
        Loading chart data...
      </div>
    )
  }

  if (!history.length) {
    return (
      <div className="h-[300px] flex items-center justify-center text-muted-foreground">
        No price history yet. Data will appear after the first check.
      </div>
    )
  }

  return (
    <div>
      <div className="flex items-center gap-4 mb-4 flex-wrap">
        <div className="flex gap-1">
          {TIME_RANGES.map((r, i) => (
            <Button
              key={r.label}
              variant={rangeIdx === i ? 'default' : 'outline'}
              size="sm"
              onClick={() => { setRangeIdx(i); onRangeChange?.(r.days) }}
            >
              {r.label}
            </Button>
          ))}
        </div>
        <span className="text-xs text-muted-foreground">Granularity:</span>
        <div className="flex gap-1">
          {granConfig.available.map((gIdx, i) => (
            <Button
              key={ALL_GRANULARITIES[gIdx].label}
              variant={granSelIdx === i ? 'default' : 'outline'}
              size="sm"
              onClick={() => setGranSelIdx(i)}
            >
              {ALL_GRANULARITIES[gIdx].label}
            </Button>
          ))}
        </div>
      </div>
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
          <XAxis
            dataKey="time"
            tick={{ fontSize: 11 }}
            className="text-muted-foreground"
          />
          <YAxis
            tick={{ fontSize: 11 }}
            tickFormatter={(v) => `$${v}`}
            className="text-muted-foreground"
          />
          <Tooltip
            formatter={(value: number, name: string) => {
              const label = name === 'high' ? 'High' : name === 'low' ? 'Low' : 'Avg'
              return [`$${value.toFixed(2)}`, label]
            }}
            labelStyle={{ color: 'hsl(var(--foreground))' }}
            contentStyle={{
              backgroundColor: 'hsl(var(--card))',
              border: '1px solid hsl(var(--border))',
              borderRadius: '0.5rem',
            }}
          />
          <Line
            type="monotone"
            dataKey="high"
            stroke="hsl(var(--primary))"
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4 }}
            name="high"
          />
          <Line
            type="monotone"
            dataKey="low"
            stroke="hsl(142 76% 36%)"
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4 }}
            name="low"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
