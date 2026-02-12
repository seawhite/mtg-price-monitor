import { useState, useMemo } from 'react'
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
  { label: 'All', days: 365 },
]

const GRANULARITIES = [
  { label: '1m', minutes: 1 },
  { label: '5m', minutes: 5 },
  { label: '15m', minutes: 15 },
  { label: '1h', minutes: 60 },
]

interface AggregatedPoint {
  time: string
  low: number
  high: number
  price: number
}

function aggregateHistory(history: PriceHistory[], granMinutes: number): AggregatedPoint[] {
  const priced = history.filter((h) => h.price !== null && h.checked_at)
  if (!priced.length) return []

  const buckets: Record<string, number[]> = {}

  for (const h of priced) {
    const ts = new Date(h.checked_at!).getTime()
    const bucketTs = Math.floor(ts / (granMinutes * 60000)) * (granMinutes * 60000)
    const key = String(bucketTs)
    if (!buckets[key]) buckets[key] = []
    buckets[key].push(h.price!)
  }

  return Object.entries(buckets)
    .sort(([a], [b]) => Number(a) - Number(b))
    .map(([key, prices]) => {
      const d = new Date(Number(key))
      const fmt =
        granMinutes >= 60
          ? d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric' })
          : d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
      return {
        time: fmt,
        low: Math.min(...prices),
        high: Math.max(...prices),
        price: prices.reduce((a, b) => a + b, 0) / prices.length,
      }
    })
}

export function PriceChart({ history, isLoading, onRangeChange }: PriceChartProps) {
  const [rangeIdx, setRangeIdx] = useState(0)
  const [granIdx, setGranIdx] = useState(2) // default 15m

  const data = useMemo(
    () => aggregateHistory(history, GRANULARITIES[granIdx].minutes),
    [history, granIdx]
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
      <div className="flex items-center gap-4 mb-4">
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
          {GRANULARITIES.map((g, i) => (
            <Button
              key={g.label}
              variant={granIdx === i ? 'default' : 'outline'}
              size="sm"
              onClick={() => setGranIdx(i)}
            >
              {g.label}
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
