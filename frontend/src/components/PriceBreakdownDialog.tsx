import type { PriceHistory } from '../types'
import { formatCurrency, parseUTC } from '../lib/utils'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from './ui/dialog'

interface PriceBreakdownDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  monitorName: string
  history: PriceHistory[]
}

interface DaySummary {
  date: string
  low: number
  high: number
  checks: number
  available: boolean
}

function buildDaySummaries(history: PriceHistory[]): DaySummary[] {
  const grouped: Record<string, { prices: number[]; available: boolean; count: number }> = {}

  for (const h of history) {
    if (!h.checked_at) continue
    const date = parseUTC(h.checked_at).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    })
    if (!grouped[date]) {
      grouped[date] = { prices: [], available: false, count: 0 }
    }
    grouped[date].count++
    if (h.price !== null) {
      grouped[date].prices.push(h.price)
    }
    if (h.available) {
      grouped[date].available = true
    }
  }

  return Object.entries(grouped)
    .map(([date, data]) => ({
      date,
      low: data.prices.length ? Math.min(...data.prices) : 0,
      high: data.prices.length ? Math.max(...data.prices) : 0,
      checks: data.count,
      available: data.available,
    }))
    .reverse()
}

export function PriceBreakdownDialog({ open, onOpenChange, monitorName, history }: PriceBreakdownDialogProps) {
  const summaries = buildDaySummaries(history)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[550px] max-h-[80vh]">
        <DialogHeader>
          <DialogTitle>Price Breakdown — {monitorName}</DialogTitle>
          <DialogDescription>Day-by-day high and low prices</DialogDescription>
        </DialogHeader>
        {summaries.length === 0 ? (
          <p className="text-muted-foreground text-sm py-4">No price data recorded yet.</p>
        ) : (
          <div className="overflow-y-auto max-h-[50vh]">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-card">
                <tr className="border-b">
                  <th className="text-left py-2 px-3 font-medium">Date</th>
                  <th className="text-right py-2 px-3 font-medium">Low</th>
                  <th className="text-right py-2 px-3 font-medium">High</th>
                  <th className="text-right py-2 px-3 font-medium">Checks</th>
                  <th className="text-center py-2 px-3 font-medium">Available</th>
                </tr>
              </thead>
              <tbody>
                {summaries.map((s) => (
                  <tr key={s.date} className="border-b last:border-0">
                    <td className="py-2 px-3">{s.date}</td>
                    <td className="py-2 px-3 text-right">{s.low > 0 ? formatCurrency(s.low) : '—'}</td>
                    <td className="py-2 px-3 text-right">{s.high > 0 ? formatCurrency(s.high) : '—'}</td>
                    <td className="py-2 px-3 text-right">{s.checks}</td>
                    <td className="py-2 px-3 text-center">
                      {s.available ? (
                        <span className="text-green-500 font-medium">Yes</span>
                      ) : (
                        <span className="text-muted-foreground">No</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
