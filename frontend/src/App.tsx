import React, { useEffect, useState, useCallback } from 'react';
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Database,
  Disc,
  Download,
  ExternalLink,
  FileText,
  Filter,
  FolderSync,
  HardDrive,
  Layers,
  ListMusic,
  Pause,
  Play,
  Plus,
  Radio,
  RefreshCw,
  Search,
  Server,
  Settings as SettingsIcon,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Trash2,
  Upload,
  XCircle,
} from 'lucide-react';
import { api, formatBytes, formatDuration } from './api';
import {
  DashboardStats,
  DownloadJob,
  ImportItem,
  ImportProject,
  LibraryItem,
  LogEntry,
  NavTab,
  SearchJob,
  SearchResult,
  SourceInfo,
} from './types';

const SOURCE_LABELS: Record<string, string> = {
  internet_archive: 'Internet Archive',
  etree: 'etree / Live Music Archive',
  wikimedia: 'Wikimedia Commons',
  jamendo: 'Jamendo Music',
  musopen: 'Musopen Classical',
  piratebay: 'PirateBay / Torrent P2P',
};

export default function App() {
  const [activeTab, setActiveTab] = useState<NavTab>('dashboard');
  const [toast, setToast] = useState<{ type: 'ok' | 'err'; text: string } | null>(null);

  // Dashboard
  const [stats, setStats] = useState<DashboardStats | null>(null);

  // Imports & Projects
  const [projects, setProjects] = useState<ImportProject[]>([]);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [rawImportText, setRawImportText] = useState('');
  const [formatHint, setFormatHint] = useState('');
  const [previewItems, setPreviewItems] = useState<ImportItem[]>([]);
  const [previewWarnings, setPreviewWarnings] = useState<string[]>([]);
  const [previewFormat, setPreviewFormat] = useState('JSON');
  const [projectName, setProjectName] = useState('');
  const [projectDesc, setProjectDesc] = useState('');
  const [newManualItem, setNewManualItem] = useState<ImportItem>({
    artist: '',
    album: '',
    track: '',
  });

  // Search
  const [searchArtist, setSearchArtist] = useState('');
  const [searchAlbum, setSearchAlbum] = useState('');
  const [searchTrack, setSearchTrack] = useState('');
  const [selectedProjectId, setSelectedProjectId] = useState<number | ''>('');
  const [searchLosslessOnly, setSearchLosslessOnly] = useState(false);
  const [searchJobs, setSearchJobs] = useState<SearchJob[]>([]);
  const [selectedJobFilter, setSelectedJobFilter] = useState<number | undefined>(undefined);

  // Results & Selection
  const [results, setResults] = useState<SearchResult[]>([]);
  const [resultsTotal, setResultsTotal] = useState(0);
  const [resultSourceFilter, setResultSourceFilter] = useState('');
  const [resultArtistFilter, setResultArtistFilter] = useState('');
  const [resultLosslessFilter, setResultLosslessFilter] = useState(false);
  const [compareDuplicatesKey, setCompareDuplicatesKey] = useState('');
  const [expandedResultIds, setExpandedResultIds] = useState<Record<number, boolean>>({});
  const [metadataModalResult, setMetadataModalResult] = useState<SearchResult | null>(null);
  const [selectedAlbumIds, setSelectedAlbumIds] = useState<number[]>([]);
  const [selectedTrackIds, setSelectedTrackIds] = useState<number[]>([]);
  const [approvalModalOpen, setApprovalModalOpen] = useState(false);
  const [overwriteExisting, setOverwriteExisting] = useState(false);

  // Downloads
  const [downloads, setDownloads] = useState<DownloadJob[]>([]);

  // Library & Navidrome
  const [libraryItems, setLibraryItems] = useState<LibraryItem[]>([]);
  const [libArtistFilter, setLibArtistFilter] = useState('');
  const [libLosslessOnly, setLibLosslessOnly] = useState(false);
  const [libFlaggedOnly, setLibFlaggedOnly] = useState(false);
  const [navidromeStatus, setNavidromeStatus] = useState<Record<string, unknown>>({});

  // Sources, Settings & Logs
  const [sources, setSources] = useState<SourceInfo[]>([]);
  const [selectedSearchSources, setSelectedSearchSources] = useState<string[]>([]);
  const [settingsData, setSettingsData] = useState<Record<string, unknown>>({});
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [logLevelFilter, setLogLevelFilter] = useState('');
  const [logCategoryFilter, setLogCategoryFilter] = useState('');

  const notify = (type: 'ok' | 'err', text: string) => {
    setToast({ type, text });
    setTimeout(() => setToast(null), 4500);
  };

  const refreshCore = useCallback(async () => {
    try {
      const [st, sr, sj, dl] = await Promise.all([
        api.getDashboardStats(),
        api.listSources(),
        api.listSearchJobs(),
        api.listDownloads(),
      ]);
      setStats(st);
      setSources(sr);
      setSearchJobs(sj);
      setDownloads(dl);
      setSelectedSearchSources((prev) =>
        prev.length > 0 ? prev : sr.filter((s) => s.enabled).map((s) => s.id),
      );
    } catch {
      // ignore transient poll error
    }
  }, []);

  const loadResults = useCallback(async () => {
    try {
      const res = await api.listSearchResults({
        job_id: selectedJobFilter,
        source: resultSourceFilter || undefined,
        artist: resultArtistFilter || undefined,
        lossless_only: resultLosslessFilter,
        limit: 100,
      });
      setResults(res.items);
      setResultsTotal(res.total);
    } catch (e: unknown) {
      notify('err', e instanceof Error ? e.message : 'Failed to load results');
    }
  }, [selectedJobFilter, resultSourceFilter, resultArtistFilter, resultLosslessFilter]);

  useEffect(() => {
    refreshCore();
    api.listProjects().then(setProjects).catch(() => {});
    api.getSettings().then(setSettingsData).catch(() => {});
    const timer = setInterval(refreshCore, 3000);
    return () => clearInterval(timer);
  }, [refreshCore]);

  useEffect(() => {
    if (activeTab === 'results' || activeTab === 'search') {
      loadResults();
    } else if (activeTab === 'import') {
      api.listProjects().then(setProjects).catch(() => {});
    } else if (activeTab === 'library') {
      api
        .listLibrary({
          artist: libArtistFilter || undefined,
          lossless_only: libLosslessOnly,
          flagged_only: libFlaggedOnly,
        })
        .then(setLibraryItems)
        .catch(() => {});
      api.getNavidromeStatus().then(setNavidromeStatus).catch(() => {});
    } else if (activeTab === 'settings') {
      api.getSettings().then(setSettingsData).catch(() => {});
    } else if (activeTab === 'logs') {
      api
        .listLogs(logLevelFilter || undefined, logCategoryFilter || undefined)
        .then(setLogs)
        .catch(() => {});
    }
  }, [
    activeTab,
    loadResults,
    libArtistFilter,
    libLosslessOnly,
    libFlaggedOnly,
    logLevelFilter,
    logCategoryFilter,
  ]);

  // Handlers — Import
  const handlePreviewImport = async () => {
    try {
      const res = await api.previewImport(uploadFile, rawImportText, formatHint);
      setPreviewItems(res.items);
      setPreviewWarnings(res.warnings);
      setPreviewFormat(res.format);
      if (!projectName) {
        setProjectName(
          uploadFile ? uploadFile.name.replace(/\.[^.]+$/, '') : `Import ${new Date().toLocaleDateString()}`,
        );
      }
      notify('ok', `Validated ${res.count} entries (${res.format}). Review entries below.`);
    } catch (e: unknown) {
      notify('err', e instanceof Error ? e.message : 'Import validation failed');
    }
  };

  const handleAddManualPreviewRow = () => {
    if (!newManualItem.artist.trim()) {
      notify('err', 'Artist name is required');
      return;
    }
    setPreviewItems((prev) => [...prev, { ...newManualItem }]);
    setNewManualItem({ artist: '', album: '', track: '' });
  };

  const handleSaveProject = async () => {
    if (!projectName.trim()) {
      notify('err', 'Enter a project name before saving');
      return;
    }
    if (previewItems.length === 0) {
      notify('err', 'Add or import at least one entry before saving project');
      return;
    }
    try {
      const created = await api.createProject({
        name: projectName,
        description: projectDesc,
        source_format: previewFormat,
        items: previewItems,
      });
      const updated = await api.listProjects();
      setProjects(updated);
      notify('ok', `Saved reusable project "${created.name}" (${created.items.length} entries).`);
    } catch (e: unknown) {
      notify('err', e instanceof Error ? e.message : 'Could not save project');
    }
  };

  // Handlers — Search
  const handleStartSearch = async (overrideProjectId?: number) => {
    const pid = overrideProjectId !== undefined ? overrideProjectId : selectedProjectId || undefined;
    if (!pid && !searchArtist.trim() && !searchAlbum.trim() && !searchTrack.trim()) {
      notify('err', 'Enter an artist, album, or track, or select an import project');
      return;
    }
    try {
      const job = await api.startSearch({
        artist: searchArtist,
        album: searchAlbum,
        track: searchTrack,
        project_id: pid ? Number(pid) : undefined,
        sources: selectedSearchSources,
        lossless_only: searchLosslessOnly,
      });
      notify('ok', `Started async search job #${job.id}: ${job.query_summary}`);
      setSelectedJobFilter(job.id);
      await refreshCore();
      setTimeout(loadResults, 1800);
    } catch (e: unknown) {
      notify('err', e instanceof Error ? e.message : 'Failed to start search');
    }
  };

  // Handlers — Selection & Approval
  const toggleAlbumSelection = (resultId: number) => {
    setSelectedAlbumIds((prev) =>
      prev.includes(resultId) ? prev.filter((id) => id !== resultId) : [...prev, resultId],
    );
  };

  const toggleTrackSelection = (trackId: number) => {
    setSelectedTrackIds((prev) =>
      prev.includes(trackId) ? prev.filter((id) => id !== trackId) : [...prev, trackId],
    );
  };

  const handleConfirmApprovedDownload = async () => {
    try {
      const jobs = await api.queueDownloads({
        result_ids: selectedAlbumIds,
        track_ids: selectedTrackIds,
        approved_by_user: true,
        overwrite_existing: overwriteExisting,
      });
      setApprovalModalOpen(false);
      setSelectedAlbumIds([]);
      setSelectedTrackIds([]);
      notify('ok', `Queued ${jobs.length} approved download track(s).`);
      await refreshCore();
      setActiveTab('downloads');
    } catch (e: unknown) {
      notify('err', e instanceof Error ? e.message : 'Failed to queue downloads');
    }
  };

  const filteredResults = compareDuplicatesKey
    ? results.filter((r) => r.duplicate_group_key === compareDuplicatesKey)
    : results;

  const navItems: { id: NavTab; label: string; icon: React.ReactNode; badge?: number }[] = [
    { id: 'dashboard', label: 'Dashboard', icon: <Activity className="w-4 h-4" /> },
    { id: 'import', label: 'Import Music', icon: <Upload className="w-4 h-4" />, badge: projects.length },
    { id: 'search', label: 'Music Search', icon: <Search className="w-4 h-4" /> },
    { id: 'results', label: 'Search Results', icon: <Disc className="w-4 h-4" />, badge: resultsTotal },
    {
      id: 'downloads',
      label: 'Download Manager',
      icon: <Download className="w-4 h-4" />,
      badge: stats?.active_downloads || undefined,
    },
    {
      id: 'library',
      label: 'Music Library',
      icon: <ListMusic className="w-4 h-4" />,
      badge: stats?.total_library_tracks || undefined,
    },
    {
      id: 'sources',
      label: 'Source Management',
      icon: <Layers className="w-4 h-4" />,
      badge: stats?.enabled_sources_count,
    },
    { id: 'settings', label: 'Settings', icon: <SettingsIcon className="w-4 h-4" /> },
    { id: 'logs', label: 'Logs', icon: <FileText className="w-4 h-4" /> },
  ];

  return (
    <div className="min-h-screen flex bg-slate-950 text-slate-100">
      {/* Sidebar */}
      <aside className="w-64 bg-slate-900/90 border-r border-slate-800 flex flex-col justify-between shrink-0">
        <div>
          <div className="p-5 flex items-center gap-3 border-b border-slate-800">
            <div className="w-10 h-10 rounded-xl bg-emerald-500/20 border border-emerald-500/40 flex items-center justify-center text-emerald-400">
              <Radio className="w-6 h-6" />
            </div>
            <div>
              <h1 className="font-bold text-base tracking-tight text-white">OpenMusic</h1>
              <p className="text-xs text-slate-400">Archive & Lossless Manager</p>
            </div>
          </div>

          <nav className="p-3 space-y-1">
            {navItems.map((item) => {
              const active = activeTab === item.id;
              return (
                <button
                  key={item.id}
                  onClick={() => setActiveTab(item.id)}
                  className={`w-full flex items-center justify-between px-3.5 py-2.5 rounded-lg text-sm font-medium transition ${
                    active
                      ? 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/30'
                      : 'text-slate-400 hover:text-slate-100 hover:bg-slate-800/60'
                  }`}
                >
                  <span className="flex items-center gap-3">
                    {item.icon}
                    {item.label}
                  </span>
                  {item.badge !== undefined && item.badge > 0 && (
                    <span className="text-xs px-2 py-0.5 rounded-full bg-slate-800 text-slate-300">
                      {item.badge}
                    </span>
                  )}
                </button>
              );
            })}
          </nav>
        </div>

        <div className="p-4 border-t border-slate-800 text-xs text-slate-400 space-y-1.5">
          <div className="flex items-center justify-between">
            <span>FFprobe Verifier</span>
            <span className="text-emerald-400 font-medium flex items-center gap-1">
              <ShieldCheck className="w-3.5 h-3.5" /> Active
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span>Enabled Archives</span>
            <span className="text-slate-200 font-semibold">{stats?.enabled_sources_count ?? 6}</span>
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 flex flex-col min-w-0 overflow-y-auto">
        {/* Top Header */}
        <header className="h-16 border-b border-slate-800 bg-slate-900/50 px-8 flex items-center justify-between sticky top-0 z-20 backdrop-blur">
          <div className="flex items-center gap-3">
            <h2 className="text-lg font-semibold capitalize">
              {navItems.find((n) => n.id === activeTab)?.label}
            </h2>
            {searchJobs.some((j) => j.status === 'RUNNING') && (
              <span className="flex items-center gap-2 text-xs px-3 py-1 rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/30">
                <RefreshCw className="w-3.5 h-3.5 animate-spin" /> Search running in background...
              </span>
            )}
          </div>

          <div className="flex items-center gap-3">
            {(selectedAlbumIds.length > 0 || selectedTrackIds.length > 0) && (
              <button
                onClick={() => setApprovalModalOpen(true)}
                className="flex items-center gap-2 px-4 py-2 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold text-sm shadow-lg shadow-emerald-500/20"
              >
                <Download className="w-4 h-4" />
                Review & Approve ({selectedAlbumIds.length} Albums, {selectedTrackIds.length} Tracks)
              </button>
            )}
            <button
              onClick={() => setActiveTab('search')}
              className="flex items-center gap-2 px-3.5 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-sm"
            >
              <Search className="w-4 h-4" /> Quick Search
            </button>
          </div>
        </header>

        {/* Toast Notification */}
        {toast && (
          <div
            className={`fixed bottom-6 right-6 z-50 px-4 py-3 rounded-xl border shadow-xl flex items-center gap-3 text-sm font-medium ${
              toast.type === 'ok'
                ? 'bg-emerald-950/95 border-emerald-500/50 text-emerald-200'
                : 'bg-rose-950/95 border-rose-500/50 text-rose-200'
            }`}
          >
            {toast.type === 'ok' ? (
              <CheckCircle2 className="w-4 h-4 text-emerald-400" />
            ) : (
              <AlertTriangle className="w-4 h-4 text-rose-400" />
            )}
            <span>{toast.text}</span>
          </div>
        )}

        <div className="p-8 space-y-8 max-w-7xl w-full mx-auto">
          {/* 1. DASHBOARD */}
          {activeTab === 'dashboard' && (
            <div className="space-y-8">
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
                  <span className="text-xs text-slate-400 uppercase tracking-wider">Artists Requested</span>
                  <div className="text-3xl font-bold mt-2 text-white">
                    {stats?.total_artists_requested ?? 0}
                  </div>
                  <p className="text-xs text-slate-500 mt-1">Across {projects.length} import projects</p>
                </div>

                <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
                  <span className="text-xs text-slate-400 uppercase tracking-wider">Albums Found</span>
                  <div className="text-3xl font-bold mt-2 text-emerald-400">
                    {stats?.albums_found ?? 0}
                  </div>
                  <p className="text-xs text-slate-500 mt-1">
                    {stats?.albums_available_for_download ?? 0} available for download
                  </p>
                </div>

                <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
                  <span className="text-xs text-slate-400 uppercase tracking-wider">Downloads (Done / Failed)</span>
                  <div className="text-3xl font-bold mt-2 text-sky-400">
                    {stats?.completed_downloads ?? 0}{' '}
                    <span className="text-lg text-rose-400 font-normal">
                      / {stats?.failed_downloads ?? 0}
                    </span>
                  </div>
                  <p className="text-xs text-slate-500 mt-1">
                    {stats?.active_downloads ?? 0} currently active in queue
                  </p>
                </div>

                <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
                  <span className="text-xs text-slate-400 uppercase tracking-wider">Library Storage Used</span>
                  <div className="text-3xl font-bold mt-2 text-purple-400">
                    {formatBytes(stats?.total_downloaded_storage_bytes ?? 0)}
                  </div>
                  <p className="text-xs text-slate-500 mt-1">
                    {stats?.enabled_sources_count ?? 0} enabled music archives
                  </p>
                </div>
              </div>

              {/* Audio Verification & Source Overview */}
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div className="lg:col-span-2 bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-4">
                  <div className="flex items-center justify-between">
                    <h3 className="font-semibold text-base flex items-center gap-2">
                      <Sparkles className="w-4 h-4 text-emerald-400" /> Quick Start Workflow
                    </h3>
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <button
                      onClick={() => setActiveTab('import')}
                      className="p-4 rounded-xl bg-slate-950 border border-slate-800 hover:border-emerald-500/50 text-left transition"
                    >
                      <div className="text-emerald-400 font-semibold text-sm">1. Import Requests</div>
                      <p className="text-xs text-slate-400 mt-1">
                        Upload CSV, YAML, or JSON lists of desired artists, albums, and tracks.
                      </p>
                    </button>
                    <button
                      onClick={() => setActiveTab('search')}
                      className="p-4 rounded-xl bg-slate-950 border border-slate-800 hover:border-emerald-500/50 text-left transition"
                    >
                      <div className="text-sky-400 font-semibold text-sm">2. Parallel Archive Search</div>
                      <p className="text-xs text-slate-400 mt-1">
                        Query Internet Archive, etree, Wikimedia, Jamendo, Musopen & Torrents.
                      </p>
                    </button>
                    <button
                      onClick={() => setActiveTab('results')}
                      className="p-4 rounded-xl bg-slate-950 border border-slate-800 hover:border-emerald-500/50 text-left transition"
                    >
                      <div className="text-purple-400 font-semibold text-sm">3. Approve & Organize</div>
                      <p className="text-xs text-slate-400 mt-1">
                        Verify FLAC bit-depth with FFprobe and organize directly for Navidrome.
                      </p>
                    </button>
                  </div>
                </div>

                <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-3">
                  <h3 className="font-semibold text-base flex items-center gap-2">
                    <ShieldCheck className="w-4 h-4 text-emerald-400" /> FFprobe Integrity Audit
                  </h3>
                  <div className="text-sm text-slate-300 space-y-2">
                    <div className="flex justify-between py-1.5 border-b border-slate-800">
                      <span className="text-slate-400">Total Library Tracks</span>
                      <span className="font-semibold">{stats?.total_library_tracks ?? 0}</span>
                    </div>
                    <div className="flex justify-between py-1.5 border-b border-slate-800">
                      <span className="text-slate-400">Verified True Lossless</span>
                      <span className="font-semibold text-emerald-400">
                        {stats?.verified_lossless_tracks ?? 0}
                      </span>
                    </div>
                    <div className="flex justify-between py-1.5">
                      <span className="text-slate-400">Flagged / Suspicious Files</span>
                      <span className="font-semibold text-amber-400">{stats?.flagged_tracks ?? 0}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* 2. IMPORT MUSIC */}
          {activeTab === 'import' && (
            <div className="space-y-8">
              <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-5">
                <div className="flex flex-wrap items-center justify-between gap-4">
                  <div>
                    <h3 className="font-semibold text-base">Import Desired Artists, Albums & Tracks</h3>
                    <p className="text-xs text-slate-400 mt-0.5">
                      Upload standard CSV, Spotify / Exportify CSV, TuneMyMusic CSV, YAML, or JSON files, validate entries, edit inline, and save as reusable projects.
                    </p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <a
                      href="/api/v1/imports/templates/csv"
                      download
                      className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-medium text-slate-200"
                    >
                      Download CSV Template
                    </a>
                    <a
                      href="/api/v1/imports/templates/spotify"
                      download
                      className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-medium text-emerald-300"
                    >
                      Download Spotify CSV Template
                    </a>
                    <a
                      href="/api/v1/imports/templates/yaml"
                      download
                      className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-medium text-slate-200"
                    >
                      Download YAML Template
                    </a>
                    <a
                      href="/api/v1/imports/templates/json"
                      download
                      className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-medium text-slate-200"
                    >
                      Download JSON Template
                    </a>
                  </div>
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                  <div className="space-y-3">
                    <label className="block text-xs font-medium text-slate-300">
                      Upload File (.csv, .yaml, .yml, .json)
                    </label>
                    <input
                      type="file"
                      accept=".csv,.yaml,.yml,.json"
                      onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
                      className="block w-full text-sm text-slate-300 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-emerald-500/20 file:text-emerald-300 hover:file:bg-emerald-500/30 bg-slate-950 border border-slate-800 rounded-lg p-2"
                    />
                    <div className="flex items-center gap-3">
                      <select
                        value={formatHint}
                        onChange={(e) => setFormatHint(e.target.value)}
                        className="bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200"
                      >
                        <option value="">Auto-detect Format</option>
                        <option value="JSON">JSON</option>
                        <option value="YAML">YAML</option>
                        <option value="CSV">CSV</option>
                      </select>
                      <button
                        onClick={handlePreviewImport}
                        className="px-4 py-2 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold text-xs"
                      >
                        Validate & Preview Entries
                      </button>
                    </div>
                  </div>

                  <div className="space-y-2">
                    <label className="block text-xs font-medium text-slate-300">
                      Or Paste CSV / YAML / JSON Content Directly
                    </label>
                    <textarea
                      rows={5}
                      value={rawImportText}
                      onChange={(e) => setRawImportText(e.target.value)}
                      placeholder={'artist,album,track\nDaft Punk,Discovery,\nPink Floyd,The Dark Side of the Moon,'}
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg p-3 text-xs font-mono text-slate-200"
                    />
                  </div>
                </div>

                {previewWarnings.length > 0 && (
                  <div className="p-3 rounded-lg bg-amber-950/50 border border-amber-500/40 text-xs text-amber-200 space-y-1">
                    {previewWarnings.map((w, i) => (
                      <div key={i}>• {w}</div>
                    ))}
                  </div>
                )}

                {/* Editable Preview Table */}
                <div className="space-y-3 pt-4 border-t border-slate-800">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <h4 className="text-sm font-semibold text-slate-200">
                      Staged Import Entries ({previewItems.length})
                    </h4>
                    <div className="flex flex-wrap items-center gap-2">
                      <input
                        type="text"
                        placeholder="Project Name (e.g. Classic Rock Lossless)"
                        value={projectName}
                        onChange={(e) => setProjectName(e.target.value)}
                        className="bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-slate-100 w-64"
                      />
                      <button
                        onClick={handleSaveProject}
                        className="px-4 py-1.5 rounded-lg bg-sky-500 hover:bg-sky-400 text-slate-950 font-semibold text-xs"
                      >
                        Save as Reusable Project
                      </button>
                    </div>
                  </div>

                  {/* Add Manual Row */}
                  <div className="grid grid-cols-1 sm:grid-cols-4 gap-2 bg-slate-950 p-3 rounded-lg border border-slate-800">
                    <input
                      type="text"
                      placeholder="Artist *"
                      value={newManualItem.artist}
                      onChange={(e) => setNewManualItem({ ...newManualItem, artist: e.target.value })}
                      className="bg-slate-900 border border-slate-800 rounded px-2.5 py-1.5 text-xs"
                    />
                    <input
                      type="text"
                      placeholder="Album (optional)"
                      value={newManualItem.album}
                      onChange={(e) => setNewManualItem({ ...newManualItem, album: e.target.value })}
                      className="bg-slate-900 border border-slate-800 rounded px-2.5 py-1.5 text-xs"
                    />
                    <input
                      type="text"
                      placeholder="Track (optional)"
                      value={newManualItem.track}
                      onChange={(e) => setNewManualItem({ ...newManualItem, track: e.target.value })}
                      className="bg-slate-900 border border-slate-800 rounded px-2.5 py-1.5 text-xs"
                    />
                    <button
                      onClick={handleAddManualPreviewRow}
                      className="flex items-center justify-center gap-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded px-3 py-1.5 text-xs font-medium"
                    >
                      <Plus className="w-3.5 h-3.5" /> Add Entry Manually
                    </button>
                  </div>

                  {previewItems.length > 0 && (
                    <div className="overflow-x-auto border border-slate-800 rounded-lg">
                      <table className="w-full text-left text-xs">
                        <thead className="bg-slate-950 text-slate-400 border-b border-slate-800">
                          <tr>
                            <th className="py-2.5 px-3">Artist</th>
                            <th className="py-2.5 px-3">Album</th>
                            <th className="py-2.5 px-3">Track</th>
                            <th className="py-2.5 px-3 w-20">Actions</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-800">
                          {previewItems.map((it, idx) => (
                            <tr key={idx} className="bg-slate-900/60">
                              <td className="p-2">
                                <input
                                  value={it.artist}
                                  onChange={(e) => {
                                    const copy = [...previewItems];
                                    copy[idx] = { ...copy[idx], artist: e.target.value };
                                    setPreviewItems(copy);
                                  }}
                                  className="w-full bg-slate-950 border border-slate-800 rounded px-2 py-1"
                                />
                              </td>
                              <td className="p-2">
                                <input
                                  value={it.album}
                                  onChange={(e) => {
                                    const copy = [...previewItems];
                                    copy[idx] = { ...copy[idx], album: e.target.value };
                                    setPreviewItems(copy);
                                  }}
                                  className="w-full bg-slate-950 border border-slate-800 rounded px-2 py-1"
                                />
                              </td>
                              <td className="p-2">
                                <input
                                  value={it.track}
                                  onChange={(e) => {
                                    const copy = [...previewItems];
                                    copy[idx] = { ...copy[idx], track: e.target.value };
                                    setPreviewItems(copy);
                                  }}
                                  className="w-full bg-slate-950 border border-slate-800 rounded px-2 py-1"
                                />
                              </td>
                              <td className="p-2">
                                <button
                                  onClick={() =>
                                    setPreviewItems(previewItems.filter((_, i) => i !== idx))
                                  }
                                  className="text-rose-400 hover:text-rose-300 p-1"
                                >
                                  <Trash2 className="w-4 h-4" />
                                </button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              </div>

              {/* Saved Reusable Projects */}
              <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-4">
                <h3 className="font-semibold text-base">Saved Import Projects ({projects.length})</h3>
                {projects.length === 0 ? (
                  <p className="text-xs text-slate-400">
                    No saved projects yet. Upload a CSV, YAML, or JSON file above and save it as a project.
                  </p>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {projects.map((proj) => (
                      <div
                        key={proj.id}
                        className="p-4 rounded-xl bg-slate-950 border border-slate-800 flex flex-col justify-between gap-3"
                      >
                        <div>
                          <div className="flex items-center justify-between">
                            <span className="font-semibold text-sm text-white">{proj.name}</span>
                            <span className="text-[11px] px-2 py-0.5 rounded bg-slate-800 text-slate-300">
                              {proj.source_format} • {proj.items.length} items
                            </span>
                          </div>
                          <div className="mt-2 max-h-28 overflow-y-auto text-xs text-slate-400 space-y-1">
                            {proj.items.map((item) => (
                              <div key={item.id} className="truncate">
                                • <span className="text-slate-200">{item.artist}</span>
                                {item.album ? ` — ${item.album}` : ''}
                                {item.track ? ` (${item.track})` : ''}
                              </div>
                            ))}
                          </div>
                        </div>
                        <div className="flex items-center justify-between pt-2 border-t border-slate-800">
                          <button
                            onClick={() => {
                              setPreviewItems(
                                proj.items.map((i) => ({
                                  artist: i.artist,
                                  album: i.album,
                                  track: i.track,
                                })),
                              );
                              setProjectName(`${proj.name} (Edited)`);
                            }}
                            className="text-xs text-sky-400 hover:underline"
                          >
                            Load into Editor
                          </button>
                          <div className="flex items-center gap-2">
                            <button
                              onClick={() => {
                                handleStartSearch(proj.id);
                                setActiveTab('results');
                              }}
                              className="px-3 py-1.5 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold text-xs flex items-center gap-1.5"
                            >
                              <Search className="w-3.5 h-3.5" /> Search All Archives
                            </button>
                            <button
                              onClick={async () => {
                                await api.deleteProject(proj.id);
                                setProjects(await api.listProjects());
                              }}
                              className="p-1.5 rounded bg-slate-800 hover:bg-rose-950 text-rose-400"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* 3. MUSIC SEARCH */}
          {activeTab === 'search' && (
            <div className="space-y-8">
              <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-5">
                <h3 className="font-semibold text-base">Multi-Archive Parallel Music Search</h3>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div>
                    <label className="block text-xs text-slate-400 mb-1">Artist Name</label>
                    <input
                      type="text"
                      value={searchArtist}
                      onChange={(e) => setSearchArtist(e.target.value)}
                      placeholder="e.g. Grateful Dead, Daft Punk, Bach"
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-slate-400 mb-1">Album / Concert Title</label>
                    <input
                      type="text"
                      value={searchAlbum}
                      onChange={(e) => setSearchAlbum(e.target.value)}
                      placeholder="e.g. Discovery, Cornell 1977, Goldberg Variations"
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-slate-400 mb-1">Track Title (Optional)</label>
                    <input
                      type="text"
                      value={searchTrack}
                      onChange={(e) => setSearchTrack(e.target.value)}
                      placeholder="Leave blank to prioritize full albums"
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2">
                  <div>
                    <label className="block text-xs text-slate-400 mb-1">
                      Or Batch-Search a Saved Import Project
                    </label>
                    <select
                      value={selectedProjectId}
                      onChange={(e) =>
                        setSelectedProjectId(e.target.value ? Number(e.target.value) : '')
                      }
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm"
                    >
                      <option value="">-- Manual Search Above --</option>
                      {projects.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.name} ({p.items.length} entries)
                        </option>
                      ))}
                    </select>
                  </div>

                  <div className="flex items-end">
                    <label className="flex items-center gap-2.5 text-sm text-slate-200 cursor-pointer pb-2">
                      <input
                        type="checkbox"
                        checked={searchLosslessOnly}
                        onChange={(e) => setSearchLosslessOnly(e.target.checked)}
                        className="rounded border-slate-700 text-emerald-500 focus:ring-emerald-500"
                      />
                      <span>Strict Lossless Filter (FLAC / WAV / 24-bit Only)</span>
                    </label>
                  </div>
                </div>

                {/* Source Checkboxes */}
                <div className="space-y-2 pt-2">
                  <span className="block text-xs text-slate-400">Target Music Archives</span>
                  <div className="flex flex-wrap gap-2.5">
                    {sources.map((src) => {
                      const checked = selectedSearchSources.includes(src.id);
                      return (
                        <label
                          key={src.id}
                          className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border text-xs cursor-pointer transition ${
                            checked
                              ? 'bg-emerald-500/15 border-emerald-500/40 text-emerald-200'
                              : 'bg-slate-950 border-slate-800 text-slate-400'
                          }`}
                        >
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={() =>
                              setSelectedSearchSources((prev) =>
                                checked ? prev.filter((id) => id !== src.id) : [...prev, src.id],
                              )
                            }
                          />
                          <span>{src.name}</span>
                        </label>
                      );
                    })}
                  </div>
                </div>

                <div className="flex items-center gap-3 pt-2">
                  <button
                    onClick={() => handleStartSearch()}
                    className="px-5 py-2.5 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold text-sm flex items-center gap-2"
                  >
                    <Search className="w-4 h-4" /> Launch Parallel Search
                  </button>
                  <button
                    onClick={() => setActiveTab('results')}
                    className="px-4 py-2.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-sm"
                  >
                    View Matching Releases ({resultsTotal})
                  </button>
                </div>
              </div>

              {/* Background Search Jobs */}
              <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-4">
                <h3 className="font-semibold text-base">Recent Asynchronous Search Jobs</h3>
                {searchJobs.length === 0 ? (
                  <p className="text-xs text-slate-400">No search jobs executed yet.</p>
                ) : (
                  <div className="space-y-2.5">
                    {searchJobs.map((job) => {
                      const pct =
                        job.total_queries > 0
                          ? Math.round((job.completed_queries / job.total_queries) * 100)
                          : 100;
                      return (
                        <div
                          key={job.id}
                          className="p-4 rounded-xl bg-slate-950 border border-slate-800 flex flex-wrap items-center justify-between gap-4"
                        >
                          <div className="space-y-1">
                            <div className="flex items-center gap-2.5">
                              <span className="font-semibold text-sm text-white">
                                #{job.id} — {job.query_summary}
                              </span>
                              <span
                                className={`text-[11px] px-2 py-0.5 rounded font-medium ${
                                  job.status === 'COMPLETED'
                                    ? 'bg-emerald-500/20 text-emerald-300'
                                    : job.status === 'RUNNING'
                                      ? 'bg-amber-500/20 text-amber-300'
                                      : 'bg-slate-800 text-slate-400'
                                }`}
                              >
                                {job.status}
                              </span>
                            </div>
                            <p className="text-xs text-slate-400">
                              Sources: {job.sources_used.join(', ')} • Queries: {job.completed_queries}/
                              {job.total_queries} ({pct}%)
                            </p>
                          </div>

                          <div className="flex items-center gap-2">
                            <button
                              onClick={() => {
                                setSelectedJobFilter(job.id);
                                setActiveTab('results');
                              }}
                              className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs text-emerald-300 font-medium"
                            >
                              Inspect Results
                            </button>
                            {job.status === 'RUNNING' && (
                              <button
                                onClick={async () => {
                                  await api.cancelSearchJob(job.id);
                                  refreshCore();
                                }}
                                className="px-3 py-1.5 rounded-lg bg-rose-950/60 hover:bg-rose-900 text-xs text-rose-300"
                              >
                                Cancel
                              </button>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* 4. SEARCH RESULTS */}
          {activeTab === 'results' && (
            <div className="space-y-6">
              {/* Filter Bar */}
              <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 flex flex-wrap items-center justify-between gap-3">
                <div className="flex flex-wrap items-center gap-3">
                  <div className="flex items-center gap-1.5 text-xs text-slate-400">
                    <Filter className="w-3.5 h-3.5" />
                    <span>Filter:</span>
                  </div>
                  <input
                    type="text"
                    placeholder="Filter by Artist..."
                    value={resultArtistFilter}
                    onChange={(e) => setResultArtistFilter(e.target.value)}
                    className="bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs"
                  />
                  <select
                    value={resultSourceFilter}
                    onChange={(e) => setResultSourceFilter(e.target.value)}
                    className="bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs"
                  >
                    <option value="">All Sources</option>
                    {Object.entries(SOURCE_LABELS).map(([k, v]) => (
                      <option key={k} value={k}>
                        {v}
                      </option>
                    ))}
                  </select>
                  <label className="flex items-center gap-1.5 text-xs text-slate-300 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={resultLosslessFilter}
                      onChange={(e) => setResultLosslessFilter(e.target.checked)}
                    />
                    <span>Lossless Only</span>
                  </label>
                  {selectedJobFilter !== undefined && (
                    <button
                      onClick={() => setSelectedJobFilter(undefined)}
                      className="text-xs px-2.5 py-1 rounded bg-sky-500/20 text-sky-300"
                    >
                      Job #{selectedJobFilter} ✕
                    </button>
                  )}
                  {compareDuplicatesKey && (
                    <button
                      onClick={() => setCompareDuplicatesKey('')}
                      className="text-xs px-2.5 py-1 rounded bg-purple-500/20 text-purple-300"
                    >
                      Comparing Duplicates ({compareDuplicatesKey}) ✕
                    </button>
                  )}
                </div>

                <div className="flex items-center gap-2">
                  <button
                    onClick={loadResults}
                    className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs flex items-center gap-1.5"
                  >
                    <RefreshCw className="w-3.5 h-3.5" /> Refresh
                  </button>
                </div>
              </div>

              {/* Release Cards */}
              {filteredResults.length === 0 ? (
                <div className="bg-slate-900 border border-slate-800 rounded-xl p-12 text-center space-y-3">
                  <Disc className="w-10 h-10 text-slate-600 mx-auto" />
                  <div className="text-base font-medium text-slate-300">No Matching Releases Displayed</div>
                  <p className="text-xs text-slate-500 max-w-md mx-auto">
                    Run a search in the Music Search tab or clear active filters to inspect matching albums and tracks.
                  </p>
                </div>
              ) : (
                <div className="space-y-4">
                  {filteredResults.map((rel) => {
                    const isAlbumSelected = selectedAlbumIds.includes(rel.id);
                    const isExpanded = !!expandedResultIds[rel.id];
                    return (
                      <div
                        key={rel.id}
                        className={`bg-slate-900 border rounded-xl p-5 transition ${
                          isAlbumSelected
                            ? 'border-emerald-500/70 bg-emerald-950/10'
                            : 'border-slate-800 hover:border-slate-700'
                        }`}
                      >
                        <div className="flex flex-col lg:flex-row gap-5 justify-between">
                          <div className="flex gap-4">
                            {/* Cover Art */}
                            <div className="w-24 h-24 rounded-lg bg-slate-950 border border-slate-800 shrink-0 overflow-hidden flex items-center justify-center">
                              {rel.cover_url ? (
                                <img
                                  src={rel.cover_url}
                                  alt={rel.album}
                                  className="w-full h-full object-cover"
                                  onError={(e) => {
                                    (e.target as HTMLImageElement).style.display = 'none';
                                  }}
                                />
                              ) : (
                                <Disc className="w-10 h-10 text-slate-700" />
                              )}
                            </div>

                            {/* Metadata Summary */}
                            <div className="space-y-1.5">
                              <div className="flex flex-wrap items-center gap-2">
                                <span className="px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-slate-800 text-sky-300 border border-slate-700">
                                  {SOURCE_LABELS[rel.source] || rel.source}
                                </span>
                                <span
                                  className={`px-2.5 py-0.5 rounded-full text-[11px] font-semibold ${
                                    rel.is_lossless
                                      ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                                      : 'bg-amber-500/15 text-amber-300 border border-amber-500/30'
                                  }`}
                                >
                                  {rel.primary_format} {rel.is_lossless ? '• Lossless' : ''}
                                </span>
                                {rel.quality_label && (
                                  <span className="text-xs text-slate-300 font-mono bg-slate-950 px-2 py-0.5 rounded border border-slate-800">
                                    {rel.quality_label}
                                  </span>
                                )}
                                {(rel.duplicate_count ?? 1) > 1 && (
                                  <button
                                    onClick={() =>
                                      setCompareDuplicatesKey(
                                        compareDuplicatesKey === rel.duplicate_group_key
                                          ? ''
                                          : rel.duplicate_group_key,
                                      )
                                    }
                                    className="text-[11px] px-2 py-0.5 rounded bg-purple-500/20 text-purple-300 border border-purple-500/30 hover:bg-purple-500/30"
                                  >
                                    Compare {rel.duplicate_count} Duplicate Releases
                                  </button>
                                )}
                              </div>

                              <h4 className="text-base font-bold text-white">
                                {rel.artist} — <span className="text-emerald-300">{rel.album}</span>{' '}
                                {rel.year ? (
                                  <span className="text-slate-400 font-normal">({rel.year})</span>
                                ) : null}
                              </h4>

                              <div className="flex flex-wrap items-center gap-x-5 gap-y-1 text-xs text-slate-400">
                                <span>
                                  Tracks: <strong className="text-slate-200">{rel.track_count}</strong>
                                </span>
                                <span>
                                  Size:{' '}
                                  <strong className="text-slate-200">
                                    {formatBytes(rel.total_size_bytes)}
                                  </strong>
                                </span>
                                <span>
                                  Formats:{' '}
                                  <strong className="text-slate-200">
                                    {rel.available_formats.join(', ')}
                                  </strong>
                                </span>
                                <span>
                                  Availability:{' '}
                                  <strong className="text-slate-200">{rel.download_availability}</strong>
                                </span>
                                {rel.seeders !== null && rel.seeders !== undefined && (
                                  <span className="text-emerald-400">
                                    Seeders: {rel.seeders} / Leechers: {rel.leechers ?? 0}
                                  </span>
                                )}
                              </div>

                              <div className="text-xs text-slate-400 truncate max-w-2xl">
                                License: <span className="text-slate-300">{rel.license}</span>
                              </div>
                            </div>
                          </div>

                          {/* Action Buttons */}
                          <div className="flex flex-wrap lg:flex-col items-end justify-between gap-2 shrink-0">
                            <div className="flex items-center gap-2">
                              <button
                                onClick={() =>
                                  setExpandedResultIds((prev) => ({
                                    ...prev,
                                    [rel.id]: !prev[rel.id],
                                  }))
                                }
                                className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-medium text-slate-200 flex items-center gap-1"
                              >
                                {isExpanded ? (
                                  <ChevronUp className="w-3.5 h-3.5" />
                                ) : (
                                  <ChevronDown className="w-3.5 h-3.5" />
                                )}
                                View Tracks ({rel.tracks.length})
                              </button>

                              <button
                                onClick={() => toggleAlbumSelection(rel.id)}
                                className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition ${
                                  isAlbumSelected
                                    ? 'bg-emerald-500 text-slate-950'
                                    : 'bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-300 border border-emerald-500/30'
                                }`}
                              >
                                {isAlbumSelected ? '✓ Album Selected' : 'Select Album'}
                              </button>
                            </div>

                            <div className="flex items-center gap-2">
                              <button
                                onClick={() => setMetadataModalResult(rel)}
                                className="px-2.5 py-1 rounded bg-slate-950 hover:bg-slate-800 text-[11px] text-slate-400 border border-slate-800"
                              >
                                Full Metadata
                              </button>
                              {rel.source_url && (
                                <a
                                  href={rel.source_url}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="px-2.5 py-1 rounded bg-slate-950 hover:bg-slate-800 text-[11px] text-sky-400 border border-slate-800 flex items-center gap-1"
                                >
                                  Open Source <ExternalLink className="w-3 h-3" />
                                </a>
                              )}
                            </div>
                          </div>
                        </div>

                        {/* Individual Track Listing Drawer */}
                        {isExpanded && (
                          <div className="mt-4 pt-4 border-t border-slate-800 overflow-x-auto">
                            <table className="w-full text-left text-xs">
                              <thead className="text-slate-400 border-b border-slate-800">
                                <tr>
                                  <th className="py-2 px-2 w-10">Select</th>
                                  <th className="py-2 px-2 w-12">#</th>
                                  <th className="py-2 px-2">Track Title</th>
                                  <th className="py-2 px-2">Format</th>
                                  <th className="py-2 px-2">Quality</th>
                                  <th className="py-2 px-2">Duration</th>
                                  <th className="py-2 px-2">Size</th>
                                  <th className="py-2 px-2">Checksum</th>
                                </tr>
                              </thead>
                              <tbody className="divide-y divide-slate-800/60">
                                {rel.tracks.map((trk) => {
                                  const trkSelected =
                                    isAlbumSelected || selectedTrackIds.includes(trk.id);
                                  return (
                                    <tr key={trk.id} className="hover:bg-slate-950/60">
                                      <td className="py-2 px-2">
                                        <input
                                          type="checkbox"
                                          checked={trkSelected}
                                          disabled={isAlbumSelected}
                                          onChange={() => toggleTrackSelection(trk.id)}
                                        />
                                      </td>
                                      <td className="py-2 px-2 text-slate-400">{trk.track_number}</td>
                                      <td className="py-2 px-2 font-medium text-slate-200">
                                        {trk.title}
                                      </td>
                                      <td className="py-2 px-2">
                                        <span
                                          className={`px-2 py-0.5 rounded text-[10px] font-semibold ${
                                            trk.is_lossless
                                              ? 'bg-emerald-500/20 text-emerald-300'
                                              : 'bg-slate-800 text-slate-300'
                                          }`}
                                        >
                                          {trk.format}
                                        </span>
                                      </td>
                                      <td className="py-2 px-2 text-slate-400 font-mono">
                                        {trk.bit_depth ? `${trk.bit_depth}-bit` : '--'} /{' '}
                                        {trk.sample_rate ? `${(trk.sample_rate / 1000).toFixed(1)}kHz` : '--'}
                                      </td>
                                      <td className="py-2 px-2 text-slate-400">
                                        {formatDuration(trk.duration_seconds)}
                                      </td>
                                      <td className="py-2 px-2 text-slate-400">
                                        {formatBytes(trk.size_bytes)}
                                      </td>
                                      <td className="py-2 px-2 text-slate-500 font-mono text-[10px]">
                                        {trk.checksum_md5
                                          ? `MD5:${trk.checksum_md5.slice(0, 8)}…`
                                          : trk.checksum_sha1
                                            ? `SHA1:${trk.checksum_sha1.slice(0, 8)}…`
                                            : '—'}
                                      </td>
                                    </tr>
                                  );
                                })}
                              </tbody>
                            </table>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* 5. DOWNLOAD MANAGER */}
          {activeTab === 'downloads' && (
            <div className="space-y-6">
              <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-4">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="font-semibold text-base">Active & Historical Downloads</h3>
                    <p className="text-xs text-slate-400">
                      Every completed file is inspected with FFprobe to verify true lossless audio codecs and checksums.
                    </p>
                  </div>
                  <button
                    onClick={refreshCore}
                    className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs flex items-center gap-1.5"
                  >
                    <RefreshCw className="w-3.5 h-3.5" /> Refresh Queue
                  </button>
                </div>

                {downloads.length === 0 ? (
                  <p className="text-xs text-slate-400 py-8 text-center">
                    No downloads queued yet. Select albums or tracks in Search Results and approve them to start.
                  </p>
                ) : (
                  <div className="space-y-3">
                    {downloads.map((dl) => (
                      <div
                        key={dl.id}
                        className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-3"
                      >
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div>
                            <div className="flex items-center gap-2">
                              <span className="font-semibold text-sm text-white">
                                {dl.artist} — {dl.title}
                              </span>
                              <span className="text-xs text-slate-400">({dl.album})</span>
                              <span className="text-[11px] px-2 py-0.5 rounded bg-slate-800 text-sky-300">
                                {SOURCE_LABELS[dl.source] || dl.source}
                              </span>
                            </div>
                            {dl.final_path && (
                              <div className="text-[11px] text-slate-400 font-mono mt-0.5">
                                Saved: {dl.final_path}
                              </div>
                            )}
                          </div>

                          <div className="flex items-center gap-2">
                            <span
                              className={`text-xs px-2.5 py-0.5 rounded font-semibold ${
                                dl.status === 'COMPLETED'
                                  ? 'bg-emerald-500/20 text-emerald-300'
                                  : dl.status === 'FAILED'
                                    ? 'bg-rose-500/20 text-rose-300'
                                    : dl.status === 'PAUSED'
                                      ? 'bg-amber-500/20 text-amber-300'
                                      : 'bg-sky-500/20 text-sky-300'
                              }`}
                            >
                              {dl.status}
                            </span>

                            {dl.status === 'DOWNLOADING' && (
                              <button
                                onClick={async () => {
                                  await api.pauseDownload(dl.id);
                                  refreshCore();
                                }}
                                className="p-1.5 rounded bg-slate-800 hover:bg-slate-700 text-amber-300"
                                title="Pause"
                              >
                                <Pause className="w-3.5 h-3.5" />
                              </button>
                            )}
                            {dl.status === 'PAUSED' && (
                              <button
                                onClick={async () => {
                                  await api.resumeDownload(dl.id);
                                  refreshCore();
                                }}
                                className="p-1.5 rounded bg-slate-800 hover:bg-slate-700 text-emerald-300"
                                title="Resume"
                              >
                                <Play className="w-3.5 h-3.5" />
                              </button>
                            )}
                            {dl.status === 'FAILED' && (
                              <button
                                onClick={async () => {
                                  await api.retryDownload(dl.id);
                                  refreshCore();
                                }}
                                className="px-2.5 py-1 rounded bg-sky-500/20 text-sky-300 text-xs"
                              >
                                Retry
                              </button>
                            )}
                            {['QUEUED', 'DOWNLOADING', 'PAUSED'].includes(dl.status) && (
                              <button
                                onClick={async () => {
                                  await api.cancelDownload(dl.id);
                                  refreshCore();
                                }}
                                className="p-1.5 rounded bg-slate-800 hover:bg-rose-950 text-rose-400"
                                title="Cancel"
                              >
                                <XCircle className="w-3.5 h-3.5" />
                              </button>
                            )}
                            <button
                              onClick={async () => {
                                await api.deleteDownload(dl.id);
                                refreshCore();
                              }}
                              className="p-1.5 rounded bg-slate-900 hover:bg-rose-950 text-slate-500 hover:text-rose-400"
                              title="Remove Record"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        </div>

                        {/* Progress Bar */}
                        <div className="w-full bg-slate-900 h-2 rounded-full overflow-hidden">
                          <div
                            className={`h-full transition-all ${
                              dl.status === 'FAILED' ? 'bg-rose-500' : 'bg-emerald-500'
                            }`}
                            style={{ width: `${Math.min(100, dl.progress_percent || 0)}%` }}
                          />
                        </div>

                        <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-400">
                          <div className="flex items-center gap-4">
                            <span>{dl.progress_percent.toFixed(1)}%</span>
                            <span>
                              {formatBytes(dl.downloaded_bytes)} / {formatBytes(dl.total_bytes)}
                            </span>
                            {dl.speed_bps > 0 && <span>Speed: {formatBytes(dl.speed_bps)}/s</span>}
                            {dl.eta_seconds !== null && dl.eta_seconds !== undefined && (
                              <span>ETA: {dl.eta_seconds}s</span>
                            )}
                            {dl.retries > 0 && <span>Retries: {dl.retries}</span>}
                          </div>

                          {/* FFprobe Audit Badges */}
                          <div className="flex flex-wrap items-center gap-2">
                            {dl.ffprobe_codec && (
                              <span className="px-2 py-0.5 rounded bg-slate-900 border border-slate-800 font-mono text-[11px] text-slate-300">
                                FFprobe: {dl.ffprobe_codec}{' '}
                                {dl.ffprobe_bit_depth ? `${dl.ffprobe_bit_depth}-bit` : ''}{' '}
                                {dl.ffprobe_sample_rate
                                  ? `${(dl.ffprobe_sample_rate / 1000).toFixed(1)}kHz`
                                  : ''}
                              </span>
                            )}
                            {dl.is_verified_lossless === true && (
                              <span className="flex items-center gap-1 text-emerald-400 font-medium">
                                <ShieldCheck className="w-3.5 h-3.5" /> Verified Lossless
                              </span>
                            )}
                            {dl.audit_flags &&
                              dl.audit_flags.map((flag, i) => (
                                <span
                                  key={i}
                                  className="flex items-center gap-1 px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 text-[11px]"
                                >
                                  <ShieldAlert className="w-3 h-3" /> {flag}
                                </span>
                              ))}
                          </div>
                        </div>

                        {dl.error_message && (
                          <div className="text-xs text-rose-400 bg-rose-950/40 border border-rose-500/30 rounded p-2">
                            Error: {dl.error_message}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* 6. MUSIC LIBRARY & NAVIDROME */}
          {activeTab === 'library' && (
            <div className="space-y-6">
              <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 flex flex-wrap items-center justify-between gap-4">
                <div className="flex items-center gap-3">
                  <Server className="w-5 h-5 text-emerald-400" />
                  <div>
                    <h3 className="font-semibold text-sm">Navidrome & NAS Music Library</h3>
                    <p className="text-xs text-slate-400">
                      Organized structure: <code>/music/Artist/Album (Year)/01 - Track.flac</code>
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={async () => {
                      const res = await api.scanLibraryDisk();
                      notify('ok', `Scanned ${res.scanned} audio files, indexed ${res.added} new items.`);
                      setLibraryItems(await api.listLibrary());
                      refreshCore();
                    }}
                    className="px-3.5 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-medium flex items-center gap-1.5"
                  >
                    <HardDrive className="w-3.5 h-3.5" /> Scan /music Disk with FFprobe
                  </button>
                  <button
                    onClick={async () => {
                      const res = await api.triggerNavidromeRescan();
                      notify(
                        res.status === 'ok' ? 'ok' : 'err',
                        String(res.message || `Navidrome scan: ${res.status}`),
                      );
                    }}
                    className="px-3.5 py-2 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold text-xs flex items-center gap-1.5"
                  >
                    <FolderSync className="w-3.5 h-3.5" /> Trigger Navidrome Rescan
                  </button>
                </div>
              </div>

              <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-4">
                <div className="flex flex-wrap items-center gap-4">
                  <input
                    type="text"
                    placeholder="Filter Library by Artist..."
                    value={libArtistFilter}
                    onChange={(e) => setLibArtistFilter(e.target.value)}
                    className="bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs"
                  />
                  <label className="flex items-center gap-1.5 text-xs text-slate-300 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={libLosslessOnly}
                      onChange={(e) => setLibLosslessOnly(e.target.checked)}
                    />
                    <span>Verified Lossless Only</span>
                  </label>
                  <label className="flex items-center gap-1.5 text-xs text-amber-300 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={libFlaggedOnly}
                      onChange={(e) => setLibFlaggedOnly(e.target.checked)}
                    />
                    <span>Show Flagged Suspicious Files Only</span>
                  </label>
                  <span className="text-xs text-slate-500 ml-auto">
                    Navidrome Status: {String(navidromeStatus.message || (navidromeStatus.connected ? 'Connected' : 'Standalone'))}
                  </span>
                </div>

                {libraryItems.length === 0 ? (
                  <p className="text-xs text-slate-400 py-8 text-center">
                    No organized tracks in library yet. Approved downloads automatically organize here.
                  </p>
                ) : (
                  <div className="overflow-x-auto border border-slate-800 rounded-lg">
                    <table className="w-full text-left text-xs">
                      <thead className="bg-slate-950 text-slate-400 border-b border-slate-800">
                        <tr>
                          <th className="py-2.5 px-3">Artist</th>
                          <th className="py-2.5 px-3">Album</th>
                          <th className="py-2.5 px-3">#</th>
                          <th className="py-2.5 px-3">Track Title</th>
                          <th className="py-2.5 px-3">Codec / Quality</th>
                          <th className="py-2.5 px-3">Size</th>
                          <th className="py-2.5 px-3">Integrity Status</th>
                          <th className="py-2.5 px-3">Path</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800">
                        {libraryItems.map((item) => (
                          <tr key={item.id} className="hover:bg-slate-950/60">
                            <td className="py-2.5 px-3 font-medium text-white">{item.artist}</td>
                            <td className="py-2.5 px-3 text-slate-300">
                              {item.album} {item.year ? `(${item.year})` : ''}
                            </td>
                            <td className="py-2.5 px-3 text-slate-400">{item.track_number}</td>
                            <td className="py-2.5 px-3 text-emerald-300 font-medium">{item.title}</td>
                            <td className="py-2.5 px-3 font-mono text-slate-300">
                              {item.codec || item.format}{' '}
                              {item.bit_depth ? `${item.bit_depth}-bit` : ''}{' '}
                              {item.sample_rate ? `${(item.sample_rate / 1000).toFixed(1)}kHz` : ''}
                            </td>
                            <td className="py-2.5 px-3 text-slate-400">
                              {formatBytes(item.size_bytes)}
                            </td>
                            <td className="py-2.5 px-3">
                              {item.audit_flags && item.audit_flags.length > 0 ? (
                                <span className="px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 text-[11px]">
                                  Flagged: {item.audit_flags.join(', ')}
                                </span>
                              ) : item.is_verified_lossless ? (
                                <span className="text-emerald-400 font-medium">✓ Verified Lossless</span>
                              ) : (
                                <span className="text-slate-400">Standard Audio</span>
                              )}
                            </td>
                            <td className="py-2.5 px-3 font-mono text-[11px] text-slate-500 max-w-xs truncate">
                              {item.file_path}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* 7. SOURCE MANAGEMENT */}
          {activeTab === 'sources' && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
              {sources.map((src) => (
                <div
                  key={src.id}
                  className="bg-slate-900 border border-slate-800 rounded-xl p-6 flex flex-col justify-between space-y-4"
                >
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <div>
                        <h3 className="font-bold text-base text-white">{src.name}</h3>
                        <a
                          href={src.website}
                          target="_blank"
                          rel="noreferrer"
                          className="text-xs text-sky-400 hover:underline flex items-center gap-1"
                        >
                          {src.website} <ExternalLink className="w-3 h-3" />
                        </a>
                      </div>
                      <button
                        onClick={async () => {
                          await api.toggleSource(src.id);
                          refreshCore();
                        }}
                        className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition ${
                          src.enabled
                            ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                            : 'bg-slate-800 text-slate-400'
                        }`}
                      >
                        {src.enabled ? 'Enabled' : 'Disabled'}
                      </button>
                    </div>

                    <p className="text-xs text-slate-300">{src.description}</p>

                    <div className="p-3 rounded-lg bg-slate-950 border border-slate-800 text-xs text-slate-400">
                      <strong className="text-slate-300">Documented API Notes:</strong> {src.limitations}
                    </div>
                  </div>

                  <div className="flex flex-wrap items-center justify-between gap-2 pt-3 border-t border-slate-800 text-xs text-slate-400">
                    <span>Priority: {src.priority}</span>
                    <span>Rate Limit: {src.rate_limit_per_sec} req/s</span>
                    <span>
                      API Key:{' '}
                      {src.requires_api_key
                        ? src.api_key_configured
                          ? '✓ Configured'
                          : '⚠ Set in Settings'
                        : 'Not Required'}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* 8. SETTINGS */}
          {activeTab === 'settings' && (
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-6">
              <div className="flex items-center justify-between border-b border-slate-800 pb-4">
                <div>
                  <h3 className="font-semibold text-base">Application, Audio & Integration Settings</h3>
                  <p className="text-xs text-slate-400">
                    API keys are stored securely on the backend and masked in the browser.
                  </p>
                </div>
                <button
                  onClick={async () => {
                    const updated = await api.updateSettings(settingsData);
                    setSettingsData(updated);
                    notify('ok', 'Settings saved successfully.');
                  }}
                  className="px-5 py-2 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold text-sm"
                >
                  Save Settings
                </button>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {/* Paths & Storage */}
                <div className="space-y-4">
                  <h4 className="text-sm font-semibold text-emerald-400">Paths & Concurrency</h4>
                  <div>
                    <label className="block text-xs text-slate-400 mb-1">
                      Final Music Library Directory (NAS Mount)
                    </label>
                    <input
                      type="text"
                      value={String(settingsData.music_dir || '')}
                      onChange={(e) =>
                        setSettingsData({ ...settingsData, music_dir: e.target.value })
                      }
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs font-mono"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-slate-400 mb-1">Staging Download Directory</label>
                    <input
                      type="text"
                      value={String(settingsData.download_dir || '')}
                      onChange={(e) =>
                        setSettingsData({ ...settingsData, download_dir: e.target.value })
                      }
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs font-mono"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-slate-400 mb-1">
                      Library Naming Convention Pattern
                    </label>
                    <input
                      type="text"
                      value={String(settingsData.naming_pattern || '')}
                      onChange={(e) =>
                        setSettingsData({ ...settingsData, naming_pattern: e.target.value })
                      }
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs font-mono"
                    />
                  </div>
                  <div className="grid grid-cols-3 gap-3">
                    <div>
                      <label className="block text-xs text-slate-400 mb-1">Search Concurrency</label>
                      <input
                        type="number"
                        value={Number(settingsData.search_concurrency ?? 5)}
                        onChange={(e) =>
                          setSettingsData({
                            ...settingsData,
                            search_concurrency: Number(e.target.value),
                          })
                        }
                        className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-slate-400 mb-1">Download Concurrency</label>
                      <input
                        type="number"
                        value={Number(settingsData.download_concurrency ?? 3)}
                        onChange={(e) =>
                          setSettingsData({
                            ...settingsData,
                            download_concurrency: Number(e.target.value),
                          })
                        }
                        className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-slate-400 mb-1">Max Storage (GB)</label>
                      <input
                        type="number"
                        value={Number(settingsData.max_storage_gb ?? 500)}
                        onChange={(e) =>
                          setSettingsData({
                            ...settingsData,
                            max_storage_gb: Number(e.target.value),
                          })
                        }
                        className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs"
                      />
                    </div>
                  </div>
                </div>

                {/* Audio Quality & API Keys */}
                <div className="space-y-4">
                  <h4 className="text-sm font-semibold text-sky-400">
                    Audio Format Priority & Source Credentials
                  </h4>
                  <div>
                    <label className="block text-xs text-slate-400 mb-1">
                      Preferred Format Order (comma-separated, default: FLAC, WAV, ALAC, LOSSLESS, MP3, OGG)
                    </label>
                    <input
                      type="text"
                      value={
                        Array.isArray(settingsData.preferred_formats)
                          ? settingsData.preferred_formats.join(', ')
                          : 'FLAC, WAV, ALAC'
                      }
                      onChange={(e) =>
                        setSettingsData({
                          ...settingsData,
                          preferred_formats: e.target.value
                            .split(',')
                            .map((s) => s.trim().toUpperCase())
                            .filter(Boolean),
                        })
                      }
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs font-mono"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-slate-400 mb-1">Minimum Audio Quality</label>
                    <select
                      value={String(settingsData.min_audio_quality || 'ANY')}
                      onChange={(e) =>
                        setSettingsData({ ...settingsData, min_audio_quality: e.target.value })
                      }
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs"
                    >
                      <option value="ANY">Allow All Formats (Prioritize Lossless First)</option>
                      <option value="LOSSLESS_ONLY">Lossless Only (FLAC / WAV / ALAC)</option>
                      <option value="HI_RES_ONLY">24-Bit Hi-Res Lossless Only</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs text-slate-400 mb-1">
                      Jamendo API v3.0 Client ID (Masked)
                    </label>
                    <input
                      type="password"
                      value={String(settingsData.jamendo_client_id || '')}
                      onChange={(e) =>
                        setSettingsData({ ...settingsData, jamendo_client_id: e.target.value })
                      }
                      placeholder="Enter Jamendo client_id"
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs"
                    />
                  </div>
                </div>

                {/* PirateBay / Torrent Settings */}
                <div className="space-y-3 pt-4 border-t border-slate-800">
                  <h4 className="text-sm font-semibold text-purple-400">
                    Torrent / PirateBay Indexer & Client Integration
                  </h4>
                  <label className="flex items-center gap-2 text-xs text-slate-200">
                    <input
                      type="checkbox"
                      checked={Boolean(settingsData.piratebay_enabled ?? true)}
                      onChange={(e) =>
                        setSettingsData({ ...settingsData, piratebay_enabled: e.target.checked })
                      }
                    />
                    <span>Enable PirateBay / Torrent P2P Adapter</span>
                  </label>
                  <div>
                    <label className="block text-xs text-slate-400 mb-1">
                      PirateBay API Endpoint URL
                    </label>
                    <input
                      type="text"
                      value={String(settingsData.piratebay_api_url || 'https://apibay.org')}
                      onChange={(e) =>
                        setSettingsData({ ...settingsData, piratebay_api_url: e.target.value })
                      }
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs font-mono"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-slate-400 mb-1">
                      qBittorrent WebUI URL (Optional for direct magnet dispatch)
                    </label>
                    <input
                      type="text"
                      placeholder="http://qbittorrent:8080"
                      value={String(settingsData.qbittorrent_url || '')}
                      onChange={(e) =>
                        setSettingsData({ ...settingsData, qbittorrent_url: e.target.value })
                      }
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs font-mono"
                    />
                  </div>
                </div>

                {/* Navidrome Integration */}
                <div className="space-y-3 pt-4 border-t border-slate-800">
                  <h4 className="text-sm font-semibold text-emerald-400">
                    Navidrome Server Integration
                  </h4>
                  <label className="flex items-center gap-2 text-xs text-slate-200">
                    <input
                      type="checkbox"
                      checked={Boolean(settingsData.navidrome_enabled)}
                      onChange={(e) =>
                        setSettingsData({ ...settingsData, navidrome_enabled: e.target.checked })
                      }
                    />
                    <span>Enable Navidrome Subsonic API Auto-Rescan</span>
                  </label>
                  <div>
                    <label className="block text-xs text-slate-400 mb-1">Navidrome Server URL</label>
                    <input
                      type="text"
                      placeholder="http://navidrome:4533"
                      value={String(settingsData.navidrome_url || '')}
                      onChange={(e) =>
                        setSettingsData({ ...settingsData, navidrome_url: e.target.value })
                      }
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs font-mono"
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs text-slate-400 mb-1">Navidrome Username</label>
                      <input
                        type="text"
                        value={String(settingsData.navidrome_user || '')}
                        onChange={(e) =>
                          setSettingsData({ ...settingsData, navidrome_user: e.target.value })
                        }
                        className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-slate-400 mb-1">
                        Navidrome Password (Masked)
                      </label>
                      <input
                        type="password"
                        value={String(settingsData.navidrome_password || '')}
                        onChange={(e) =>
                          setSettingsData({ ...settingsData, navidrome_password: e.target.value })
                        }
                        className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs"
                      />
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* 9. LOGS */}
          {activeTab === 'logs' && (
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <select
                    value={logLevelFilter}
                    onChange={(e) => setLogLevelFilter(e.target.value)}
                    className="bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs"
                  >
                    <option value="">All Levels</option>
                    <option value="INFO">INFO</option>
                    <option value="WARNING">WARNING</option>
                    <option value="ERROR">ERROR</option>
                  </select>
                  <select
                    value={logCategoryFilter}
                    onChange={(e) => setLogCategoryFilter(e.target.value)}
                    className="bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs"
                  >
                    <option value="">All Categories</option>
                    <option value="SYSTEM">SYSTEM</option>
                    <option value="IMPORT">IMPORT</option>
                    <option value="SEARCH">SEARCH</option>
                    <option value="DOWNLOAD">DOWNLOAD</option>
                    <option value="AUDIT">AUDIT (FFprobe)</option>
                    <option value="NAVIDROME">NAVIDROME</option>
                  </select>
                </div>
                <button
                  onClick={async () => {
                    await api.clearLogs();
                    setLogs([]);
                  }}
                  className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-rose-950 text-xs text-rose-300"
                >
                  Clear Logs
                </button>
              </div>

              <div className="space-y-2 max-h-[600px] overflow-y-auto font-mono text-xs">
                {logs.map((log) => (
                  <div
                    key={log.id}
                    className="p-3 rounded-lg bg-slate-950 border border-slate-800 flex flex-wrap items-start justify-between gap-2"
                  >
                    <div className="space-x-2">
                      <span
                        className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                          log.level === 'ERROR'
                            ? 'bg-rose-500/20 text-rose-300'
                            : log.level === 'WARNING'
                              ? 'bg-amber-500/20 text-amber-300'
                              : 'bg-emerald-500/20 text-emerald-300'
                        }`}
                      >
                        {log.level}
                      </span>
                      <span className="text-sky-400">[{log.category}]</span>
                      <span className="text-slate-200">{log.message}</span>
                    </div>
                    <span className="text-[10px] text-slate-500">{log.created_at}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </main>

      {/* Full Metadata Inspection Modal */}
      {metadataModalResult && (
        <div className="fixed inset-0 z-50 bg-black/75 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-2xl w-full p-6 space-y-4 max-h-[85vh] overflow-y-auto">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="font-bold text-base">
                Full Archive Metadata — {metadataModalResult.artist} - {metadataModalResult.album}
              </h3>
              <button
                onClick={() => setMetadataModalResult(null)}
                className="text-slate-400 hover:text-white text-sm"
              >
                ✕ Close
              </button>
            </div>
            <pre className="bg-slate-950 p-4 rounded-xl border border-slate-800 text-xs font-mono text-emerald-300 overflow-x-auto">
              {JSON.stringify(metadataModalResult, null, 2)}
            </pre>
          </div>
        </div>
      )}

      {/* Explicit User Approval Confirmation Modal */}
      {approvalModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/75 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-emerald-500/40 rounded-2xl max-w-lg w-full p-6 space-y-4 shadow-2xl">
            <div className="flex items-center gap-3 text-emerald-400">
              <ShieldCheck className="w-6 h-6" />
              <h3 className="font-bold text-base text-white">Approve Selected Downloads</h3>
            </div>
            <p className="text-xs text-slate-300 leading-relaxed">
              OpenMusic Archive Manager never downloads files without explicit user approval. Please
              confirm your selection below:
            </p>
            <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 text-xs space-y-1.5">
              <div>
                • Selected Full Albums: <strong>{selectedAlbumIds.length}</strong>
              </div>
              <div>
                • Selected Individual Tracks: <strong>{selectedTrackIds.length}</strong>
              </div>
              <div>
                • Post-Download Verification: <strong>FFprobe Codec & Checksum Audit Enabled</strong>
              </div>
            </div>
            <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
              <input
                type="checkbox"
                checked={overwriteExisting}
                onChange={(e) => setOverwriteExisting(e.target.checked)}
              />
              <span>Allow overwriting existing files in library if duplicate exists</span>
            </label>
            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                onClick={() => setApprovalModalOpen(false)}
                className="px-4 py-2 rounded-lg bg-slate-800 text-xs text-slate-300"
              >
                Cancel
              </button>
              <button
                onClick={handleConfirmApprovedDownload}
                className="px-5 py-2 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold text-xs"
              >
                Approve & Start Download
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
