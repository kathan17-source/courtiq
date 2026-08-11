export function createApiClient(baseUrl) {
  const url = path => `${baseUrl.replace(/\/$/, '')}${path}`;
  return {
    url,
    async json(path, options = {}) {
      const response = await fetch(url(path), options);
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : payload.error?.message || `Request failed with ${response.status}`);
      return payload;
    }
  };
}
