export interface Monitor {
  id: number
  name: string
  source: 'tcgplayer' | 'ebay' | 'manapool'
  url: string
  min_price: number | null
  max_price: number | null
  track_min_price: number | null
  track_max_price: number | null
  alerts_enabled: boolean
  last_checked_at: string | null
  last_price: number | null
  last_status: 'available' | 'unavailable' | 'error' | null
  last_alerted_at: string | null
  created_at: string | null
  updated_at: string | null
}

export interface MonitorCreate {
  name: string
  source: 'tcgplayer' | 'ebay' | 'manapool'
  url: string
  min_price: number | null
  max_price: number | null
  track_min_price: number | null
  track_max_price: number | null
  alerts_enabled: boolean
}

export interface MonitorUpdate {
  name?: string
  url?: string
  min_price?: number | null
  max_price?: number | null
  track_min_price?: number | null
  track_max_price?: number | null
  alerts_enabled?: boolean
}

export interface PriceHistory {
  id: number
  monitor_id: number
  price: number | null
  available: boolean
  source_detail: string | null
  checked_at: string | null
}

export interface HealthStatus {
  status: string
  monitors_count: number
  scheduler_running: boolean
}
