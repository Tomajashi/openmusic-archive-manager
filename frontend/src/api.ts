import {
  DashboardStats,
  DownloadJob,
  ImportItem,
  ImportProject,
  LibraryItem,
  LogEntry,
  SearchJob,
  SearchResult,
  SourceInfo,
} from './types';

export function formatBytes(bytes: number): string {
  if (!bytes || bytes <= 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return `${(bytes / Math.pow(1024, i)).toFixed(i > 1 ? 1 : 0)} ${units[i]}`;
}

export function formatDuration(seconds?: number | null): string {
  if (!seconds || seconds <= 0) return '--:--';
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...options,
    headers: {
      ...(options?.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
      ...(options?.headers || {}),
    },
  });
  if (!res.ok) {
    let errText = `HTTP ${res.status}`;
    try {
      const data = await res.json();
      errText = data.detail || data.message || errText;
    } catch {
      // ignore
    }
    throw new Error(errText);
  }
  return res.json();
}

export const api = {
  getDashboardStats: () => request<DashboardStats>('/api/v1/dashboard/stats'),

  previewImport: async (file: File | null, rawContent: string, formatHint: string) => {
    const fd = new FormData();
    if (file) fd.append('file', file);
    if (rawContent) fd.append('raw_content', rawContent);
    if (formatHint) fd.append('format_hint', formatHint);
    return request<{
      format: string;
      count: number;
      items: ImportItem[];
      warnings: string[];
    }>('/api/v1/imports/preview', { method: 'POST', body: fd });
  },

  listProjects: () => request<ImportProject[]>('/api/v1/imports/projects'),

  createProject: (payload: {
    name: string;
    description: string;
    source_format: string;
    items: ImportItem[];
  }) =>
    request<ImportProject>('/api/v1/imports/projects', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  deleteProject: (id: number) =>
    request<{ status: string }>(`/api/v1/imports/projects/${id}`, { method: 'DELETE' }),

  addProjectItem: (projectId: number, item: ImportItem) =>
    request<ImportItem>(`/api/v1/imports/projects/${projectId}/items`, {
      method: 'POST',
      body: JSON.stringify(item),
    }),

  updateProjectItem: (itemId: number, item: Partial<ImportItem>) =>
    request<ImportItem>(`/api/v1/imports/items/${itemId}`, {
      method: 'PUT',
      body: JSON.stringify(item),
    }),

  deleteProjectItem: (itemId: number) =>
    request<{ status: string }>(`/api/v1/imports/items/${itemId}`, { method: 'DELETE' }),

  startSearch: (payload: {
    artist?: string;
    album?: string;
    track?: string;
    project_id?: number;
    sources?: string[];
    lossless_only?: boolean;
  }) =>
    request<SearchJob>('/api/v1/search/start', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  listSearchJobs: () => request<SearchJob[]>('/api/v1/search/jobs'),

  cancelSearchJob: (jobId: number) =>
    request<SearchJob>(`/api/v1/search/jobs/${jobId}/cancel`, { method: 'POST' }),

  listSearchResults: (params: {
    job_id?: number;
    source?: string;
    artist?: string;
    album?: string;
    lossless_only?: boolean;
    page?: number;
    limit?: number;
  }) => {
    const q = new URLSearchParams();
    if (params.job_id !== undefined) q.set('job_id', String(params.job_id));
    if (params.source) q.set('source', params.source);
    if (params.artist) q.set('artist', params.artist);
    if (params.album) q.set('album', params.album);
    if (params.lossless_only) q.set('lossless_only', 'true');
    if (params.page) q.set('page', String(params.page));
    if (params.limit) q.set('limit', String(params.limit));
    return request<{
      total: number;
      page: number;
      limit: number;
      pages: number;
      items: SearchResult[];
    }>(`/api/v1/search/results?${q.toString()}`);
  },

  queueDownloads: (payload: {
    result_ids: number[];
    track_ids: number[];
    approved_by_user: boolean;
    overwrite_existing?: boolean;
  }) =>
    request<DownloadJob[]>('/api/v1/downloads/queue', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  listDownloads: (status?: string) =>
    request<DownloadJob[]>(
      `/api/v1/downloads${status ? `?status=${encodeURIComponent(status)}` : ''}`,
    ),

  pauseDownload: (id: number) =>
    request<DownloadJob>(`/api/v1/downloads/${id}/pause`, { method: 'POST' }),

  resumeDownload: (id: number) =>
    request<DownloadJob>(`/api/v1/downloads/${id}/resume`, { method: 'POST' }),

  retryDownload: (id: number) =>
    request<DownloadJob>(`/api/v1/downloads/${id}/retry`, { method: 'POST' }),

  cancelDownload: (id: number) =>
    request<DownloadJob>(`/api/v1/downloads/${id}/cancel`, { method: 'POST' }),

  deleteDownload: (id: number) =>
    request<{ status: string }>(`/api/v1/downloads/${id}`, { method: 'DELETE' }),

  listLibrary: (params?: {
    artist?: string;
    album?: string;
    lossless_only?: boolean;
    flagged_only?: boolean;
  }) => {
    const q = new URLSearchParams();
    if (params?.artist) q.set('artist', params.artist);
    if (params?.album) q.set('album', params.album);
    if (params?.lossless_only) q.set('lossless_only', 'true');
    if (params?.flagged_only) q.set('flagged_only', 'true');
    return request<LibraryItem[]>(`/api/v1/library?${q.toString()}`);
  },

  scanLibraryDisk: () =>
    request<{ scanned: number; added: number }>('/api/v1/library/scan-disk', {
      method: 'POST',
    }),

  getNavidromeStatus: () =>
    request<Record<string, unknown>>('/api/v1/library/navidrome/status'),

  triggerNavidromeRescan: () =>
    request<Record<string, unknown>>('/api/v1/library/navidrome/rescan', {
      method: 'POST',
    }),

  listSources: () => request<SourceInfo[]>('/api/v1/sources'),

  toggleSource: (id: string) =>
    request<{ id: string; enabled: boolean }>(`/api/v1/sources/${id}/toggle`, {
      method: 'POST',
    }),

  getSettings: () => request<Record<string, unknown>>('/api/v1/settings'),

  updateSettings: (payload: Record<string, unknown>) =>
    request<Record<string, unknown>>('/api/v1/settings', {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),

  listLogs: (level?: string, category?: string) => {
    const q = new URLSearchParams();
    if (level) q.set('level', level);
    if (category) q.set('category', category);
    return request<LogEntry[]>(`/api/v1/logs?${q.toString()}`);
  },

  clearLogs: () => request<{ status: string }>('/api/v1/logs', { method: 'DELETE' }),
};
