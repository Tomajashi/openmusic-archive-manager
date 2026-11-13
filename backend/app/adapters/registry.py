from typing import Dict, List
from backend.app.adapters.base import BaseSourceAdapter
from backend.app.adapters.internet_archive import InternetArchiveAdapter
from backend.app.adapters.etree import EtreeAdapter
from backend.app.adapters.wikimedia import WikimediaCommonsAdapter
from backend.app.adapters.jamendo import JamendoAdapter
from backend.app.adapters.musopen import MusopenAdapter
from backend.app.adapters.piratebay import PirateBayAdapter


class AdapterRegistry:
    def __init__(self) -> None:
        self._adapters: Dict[str, BaseSourceAdapter] = {}
        self.register(InternetArchiveAdapter())
        self.register(EtreeAdapter())
        self.register(WikimediaCommonsAdapter())
        self.register(JamendoAdapter())
        self.register(MusopenAdapter())
        self.register(PirateBayAdapter())

    def register(self, adapter: BaseSourceAdapter) -> None:
        self._adapters[adapter.source_id] = adapter

    def get(self, source_id: str) -> BaseSourceAdapter | None:
        return self._adapters.get(source_id)

    def all(self) -> List[BaseSourceAdapter]:
        return list(self._adapters.values())

    def ids(self) -> List[str]:
        return list(self._adapters.keys())


adapter_registry = AdapterRegistry()
