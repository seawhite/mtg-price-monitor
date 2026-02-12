import { useState } from 'react'
import type { MonitorCreate } from '../types'
import { Button } from './ui/button'
import { Input } from './ui/input'
import { Switch } from './ui/switch'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from './ui/dialog'

interface MonitorFormProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSubmit: (data: MonitorCreate) => void
  initialData?: Partial<MonitorCreate>
  isEdit?: boolean
}

const SOURCE_OPTIONS = [
  { value: 'tcgplayer' as const, label: 'TCGPlayer', placeholder: 'https://www.tcgplayer.com/product/...' },
  { value: 'ebay' as const, label: 'eBay', placeholder: 'ms. bumbleflower raised foil' },
  { value: 'manapool' as const, label: 'Manapool', placeholder: 'https://manapool.com/card/...' },
]

export function MonitorForm({ open, onOpenChange, onSubmit, initialData, isEdit }: MonitorFormProps) {
  const [source, setSource] = useState<'tcgplayer' | 'ebay' | 'manapool'>(initialData?.source || 'tcgplayer')
  const [name, setName] = useState(initialData?.name || '')
  const [url, setUrl] = useState(initialData?.url || '')
  const [minPrice, setMinPrice] = useState(initialData?.min_price?.toString() || '')
  const [maxPrice, setMaxPrice] = useState(initialData?.max_price?.toString() || '')
  const [trackMinPrice, setTrackMinPrice] = useState(initialData?.track_min_price?.toString() || '')
  const [trackMaxPrice, setTrackMaxPrice] = useState(initialData?.track_max_price?.toString() || '')
  const [alertsEnabled, setAlertsEnabled] = useState(initialData?.alerts_enabled ?? true)

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    onSubmit({
      name,
      source,
      url,
      min_price: minPrice ? parseFloat(minPrice) : null,
      max_price: maxPrice ? parseFloat(maxPrice) : null,
      track_min_price: trackMinPrice ? parseFloat(trackMinPrice) : null,
      track_max_price: trackMaxPrice ? parseFloat(trackMaxPrice) : null,
      alerts_enabled: alertsEnabled,
    })
    if (!isEdit) {
      setName('')
      setUrl('')
      setMinPrice('')
      setMaxPrice('')
      setTrackMinPrice('')
      setTrackMaxPrice('')
      setAlertsEnabled(true)
    }
  }

  const selectedSource = SOURCE_OPTIONS.find((s) => s.value === source)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>{isEdit ? 'Edit Monitor' : 'Add New Monitor'}</DialogTitle>
          <DialogDescription>
            {isEdit ? 'Update your monitor settings.' : 'Configure a new price monitor for an MTG card.'}
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Source selector */}
          <div>
            <label className="text-sm font-medium mb-2 block">Source</label>
            <div className="flex gap-2">
              {SOURCE_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => setSource(opt.value)}
                  className={`flex-1 rounded-md px-3 py-2 text-sm font-medium border transition-colors ${
                    source === opt.value
                      ? 'bg-primary text-primary-foreground border-primary'
                      : 'bg-background text-foreground border-input hover:bg-accent'
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          {/* Name */}
          <div>
            <label className="text-sm font-medium mb-1 block">Card Name</label>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Ms. Bumbleflower Raised Foil"
              required
            />
          </div>

          {/* URL / Search Term */}
          <div>
            <label className="text-sm font-medium mb-1 block">
              {source === 'ebay' ? 'Search Term' : 'Product URL'}
            </label>
            <Input
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder={selectedSource?.placeholder}
              required
            />
            {source === 'ebay' && (
              <p className="text-xs text-muted-foreground mt-1">
                Filters: Buy It Now only, US listings only
              </p>
            )}
          </div>

          {/* Tracking Range */}
          <div>
            <label className="text-sm font-medium mb-1 block">Tracking Range ($)</label>
            <p className="text-xs text-muted-foreground mb-2">Filter out irrelevant listings. Only prices in this range are recorded.</p>
            <div className="grid grid-cols-2 gap-3">
              <Input
                type="number"
                step="0.01"
                min="0"
                value={trackMinPrice}
                onChange={(e) => setTrackMinPrice(e.target.value)}
                placeholder="50.00"
              />
              <Input
                type="number"
                step="0.01"
                min="0"
                value={trackMaxPrice}
                onChange={(e) => setTrackMaxPrice(e.target.value)}
                placeholder="2000.00"
              />
            </div>
          </div>

          {/* Alert Range */}
          <div>
            <label className="text-sm font-medium mb-1 block">Alert Range ($)</label>
            <p className="text-xs text-muted-foreground mb-2">Get notified when a listing is in this price range.</p>
            <div className="grid grid-cols-2 gap-3">
              <Input
                type="number"
                step="0.01"
                min="0"
                value={minPrice}
                onChange={(e) => setMinPrice(e.target.value)}
                placeholder="400.00"
              />
              <Input
                type="number"
                step="0.01"
                min="0"
                value={maxPrice}
                onChange={(e) => setMaxPrice(e.target.value)}
                placeholder="850.00"
              />
            </div>
          </div>

          {/* Alerts Toggle */}
          <div className="flex items-center justify-between">
            <label className="text-sm font-medium">Alerts Enabled</label>
            <Switch checked={alertsEnabled} onCheckedChange={setAlertsEnabled} />
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit">{isEdit ? 'Save Changes' : 'Add Monitor'}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
