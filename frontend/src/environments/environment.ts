declare global {
  interface Window {
    IOT_CONFIG?: {
      apiKey?: string;
      backendUrl?: string;
    };
  }
}

function getBackendUrl(): string {
  if (typeof window !== 'undefined' && window.IOT_CONFIG?.backendUrl) {
    return window.IOT_CONFIG.backendUrl;
  }
  return '/api/v1';
}

function getApiKey(): string {
  if (typeof window !== 'undefined') {
    // 1. URL parameter override (?api_key=XYZ)
    const params = new URLSearchParams(window.location.search);
    const queryKey = params.get('api_key');
    if (queryKey) {
      localStorage.setItem('iot_api_key', queryKey);
      return queryKey;
    }

    // 2. LocalStorage override
    const stored = localStorage.getItem('iot_api_key');
    if (stored) {
      return stored;
    }

    // 3. Runtime Docker injected config from .env
    if (window.IOT_CONFIG?.apiKey) {
      return window.IOT_CONFIG.apiKey;
    }
  }

  // 4. Default fallback for development
  return 'iot-secret-key-change-me-in-production';
}

export const environment = {
  production: false,
  get backendUrl(): string {
    return getBackendUrl();
  },
  get apiKey(): string {
    return getApiKey();
  },
  setApiKey(key: string): void {
    if (typeof window !== 'undefined') {
      localStorage.setItem('iot_api_key', key);
    }
  },
  clearApiKey(): void {
    if (typeof window !== 'undefined') {
      localStorage.removeItem('iot_api_key');
    }
  },
  version: 'v11.1.0',
  timezone: 'Europe/Madrid',
  dateFormat: 'dd-MM-yyyy HH:mm',
};
