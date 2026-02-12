import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatCurrency(value: number | null | undefined): string {
  if (value === null || value === undefined) return 'N/A'
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
  }).format(value)
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return 'Never'
  const date = new Date(value)
  return date.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  })
}

export function sourceLabel(source: string): string {
  const labels: Record<string, string> = {
    tcgplayer: 'TCGPlayer',
    ebay: 'eBay',
    manapool: 'Manapool',
  }
  return labels[source] || source
}
