function getBackendUrl(): string {
  if (typeof window !== 'undefined' && window.location) {
    const protocol = window.location.protocol || 'http:';
    const hostname = window.location.hostname || 'localhost';
    return `${protocol}//${hostname}:8765`;
  }
  return 'http://localhost:8765';
}

export const environment = {
  production: false,
  backendUrl: getBackendUrl(),
  apiKey: 'iot-secret-key-change-me-in-production',
  version: 'v11.0.0',
  timezone: 'Europe/Madrid',
  dateFormat: 'dd-MM-yyyy HH:mm',
};
