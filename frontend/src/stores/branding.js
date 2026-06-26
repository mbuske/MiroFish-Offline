import { reactive, computed } from 'vue'
import api from '@/api'

const state = reactive({ logoUrl: null, primaryColor: null, accentColor: null })

function appendCacheBuster(url) {
  if (!url) return url
  return url.includes('?') ? url + '&t=' + Date.now() : url + '?t=' + Date.now()
}

export function useBranding() {
  async function applyBranding(slug) {
    // If slug not passed (undefined), read from URL param ?account=
    if (slug === undefined) {
      slug = new URLSearchParams(window.location.search).get('account')
    }
    const url = '/api/branding/config' + (slug ? ('?account=' + encodeURIComponent(slug)) : '')
    try {
      const cfg = await api.get(url)
      if (cfg.primary_color) {
        state.primaryColor = cfg.primary_color
        document.documentElement.style.setProperty('--brand-primary', cfg.primary_color)
      }
      if (cfg.accent_color) {
        state.accentColor = cfg.accent_color
        document.documentElement.style.setProperty('--brand-accent', cfg.accent_color)
      }
      if (cfg.favicon_url) {
        let link = document.querySelector("link[rel='icon']")
        if (!link) {
          link = document.createElement('link')
          link.rel = 'icon'
          document.head.appendChild(link)
        }
        link.href = appendCacheBuster(cfg.favicon_url)
      }
      state.logoUrl = cfg.logo_url || null
    } catch (e) {
      // silently ignore — public endpoint, non-blocking
    }
  }

  return {
    logoUrl: computed(() => state.logoUrl),
    primaryColor: computed(() => state.primaryColor),
    accentColor: computed(() => state.accentColor),
    applyBranding,
  }
}
