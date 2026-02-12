import { useState } from 'react'
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
}

const TIME_RANGES = [
  { label: '7d', days: 7 },
  { label: '30d', days: 30 },
  { label: 'All', days: 365 },
]

export function PriceChart({ history, isLoading }: PriceChartProps) {
  const [rangeIdx, setRangeIdx] = useState(0)

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

  const data = history
    .filter((h) => h.price !== null)
    .map((h) => ({
      time: new Date(h.checked_at!).toLocaleString('en-US', {
        month: 'short',
        day: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
      }),
      price: h.price,
      available: h.available,
    }))

  return (
    <div>
      <div className="flex gap-1 mb-4">
        {TIME_RANGES.map((r, i) => (
          <Button
            key={r.label}
            variant={rangeIdx === i ? 'default' : 'outline'}
            size="sm"
            onClick={() => setRangeIdx(i)}
          >
            {r.label}
          </Button>
        ))}
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
            formatter={(value: number) => [`$${value.toFixed(2)}`, 'Price']}
            labelStyle={{ color: 'hsl(var(--foreground))' }}
            contentStyle={{
              backgroundColor: 'hsl(var(--card))',
              border: '1px solid hsl(var(--border))',
              borderRadius: '0.5rem',
            }}
          />
          <Line
            type="monotone"
            dataKey="price"
            stroke="hsl(var(--primary))"
            strokeWidth={2}
            dot={{ r: 3 }}
            activeDot={{ r: 5 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
