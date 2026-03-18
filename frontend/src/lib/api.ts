import axios from 'axios'

const rawBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim()

function normalizeBaseUrl(value: string | undefined): string {
  if (!value) {
    return '/api'
  }
  return value.endsWith('/') ? value.slice(0, -1) : value
}

export const API_BASE_URL = normalizeBaseUrl(rawBaseUrl)

export const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 15000,
})

export function formatApiError(error: unknown, fallback: string): string {
  if (axios.isAxiosError(error)) {
    const status = error.response?.status
    const detail = error.response?.data?.detail

    if (typeof detail === 'string' && detail) {
      return status ? `${fallback} (${status}): ${detail}` : `${fallback}: ${detail}`
    }

    if (error.code === 'ECONNABORTED') {
      return `${fallback}: request timed out`
    }

    if (error.message) {
      return `${fallback}: ${error.message}`
    }
  }

  if (error instanceof Error && error.message) {
    return `${fallback}: ${error.message}`
  }

  return fallback
}
