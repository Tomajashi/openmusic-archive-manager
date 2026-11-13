import os
from pathlib import Path
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_CONFIG_DIR = Path(os.getenv("CONFIG_DIR", str(BASE_DIR / "config")))
DEFAULT_DOWNLOAD_DIR = Path(os.getenv("DOWNLOAD_DIR", str(BASE_DIR / "downloads")))
DEFAULT_MUSIC_DIR = Path(os.getenv("MUSIC_DIR", str(BASE_DIR / "music")))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "OpenMusic Archive Manager"
    app_version: str = "1.0.0"
    port: int = 8080
    log_level: str = "INFO"

    config_dir: str = str(DEFAULT_CONFIG_DIR)
    download_dir: str = str(DEFAULT_DOWNLOAD_DIR)
    music_dir: str = str(DEFAULT_MUSIC_DIR)

    database_url: str = ""

    # Concurrency & storage limits
    search_concurrency: int = 5
    download_concurrency: int = 3
    max_storage_gb: float = 500.0
    auto_duplicate_detection: bool = True

    # Audio format preferences
    preferred_formats: List[str] = ["FLAC", "WAV", "ALAC", "LOSSLESS", "MP3", "OGG"]
    min_audio_quality: str = "ANY"  # ANY, LOSSLESS_ONLY, HI_RES_ONLY
    naming_pattern: str = "{artist}/{album_year}/{track_num} - {title}.{ext}"

    # External API keys & credentials (never exposed in plaintext to frontend)
    jamendo_client_id: str = ""
    musopen_api_key: str = ""
    musicbrainz_enabled: bool = True
    musicbrainz_user_agent: str = "OpenMusicArchiveManager/1.0 (https://github.com/Tomajashi/openmusic-archive-manager)"

    # PirateBay / Torznab / Torrent Client Settings
    piratebay_enabled: bool = True
    piratebay_api_url: str = "https://apibay.org"
    torznab_url: str = ""
    torznab_api_key: str = ""
    qbittorrent_url: str = ""
    qbittorrent_username: str = ""
    qbittorrent_password: str = ""
    transmission_url: str = ""

    # Navidrome integration
    navidrome_enabled: bool = False
    navidrome_url: str = ""
    navidrome_user: str = ""
    navidrome_password: str = ""
    navidrome_music_path: str = "/music"
    navidrome_auto_rescan: bool = True

    def get_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        cfg_path = Path(self.config_dir)
        cfg_path.mkdir(parents=True, exist_ok=True)
        db_file = cfg_path / "openmusic.db"
        return f"sqlite:///{db_file.as_posix()}"

    def ensure_directories(self) -> None:
        Path(self.config_dir).mkdir(parents=True, exist_ok=True)
        Path(self.download_dir).mkdir(parents=True, exist_ok=True)
        Path(self.music_dir).mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_directories()
