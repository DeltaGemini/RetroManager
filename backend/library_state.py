"""
What you've said about your games, rather than what they are: each game's play
status (backlog, playing, finished) and your own collections.

Kept in DATA_PATH/library-state.json, keyed by "system/rom path". Favourites
aren't here: they're the gamelist's own <favorite>, which EmulationStation
reads. Statuses and collections are also written out as EmulationStation
custom collections (custom-<name>.cfg) so the Pi can show them.
"""

import json
import logging
import re
import threading
import uuid
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Play statuses, in the order they're offered
STATUSES = [('playing', 'Playing'), ('backlog', 'Backlog'), ('finished', 'Finished')]
STATUS_KEYS = {key for key, _ in STATUSES}
_UNSAFE_NAME_RE = re.compile(r'[^A-Za-z0-9 _\-]+')


class LibraryState:
    def __init__(self, state_dir: Path):
        self.state_file = Path(state_dir) / 'library-state.json'
        self.export_dir = Path(state_dir) / 'collections'
        self._lock = threading.Lock()
        try:
            data = json.loads(self.state_file.read_text())
        except (OSError, ValueError):
            data = {}
        self._status: Dict[str, str] = {k: v for k, v in (data.get('status') or {}).items() if v in STATUS_KEYS}
        # With login on, each person has their own: {person: {game: status}}
        self._by_person: Dict[str, Dict[str, str]] = {
            person: {k: v for k, v in (statuses or {}).items() if v in STATUS_KEYS}
            for person, statuses in (data.get('status_by_person') or {}).items() if isinstance(statuses, dict)}
        self._collections: List[Dict] = [c for c in data.get('collections') or [] if c.get('id') and c.get('name')]

    def _save(self):
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_file.with_suffix('.tmp')
        tmp.write_text(json.dumps({'status': self._status, 'status_by_person': self._by_person, 'collections': self._collections}, indent=1))
        tmp.replace(self.state_file)

    # --- Reading ---

    def _statuses(self, person: Optional[str]) -> Dict[str, str]:
        """A person's play statuses, or with no person (login off) the shared set."""
        return self._status if person is None else self._by_person.setdefault(person, {})

    def adopt(self, person: str):
        """Give the shared play statuses to a person who has none of their own
        (when login is switched on, they become the first admin's)."""
        with self._lock:
            if self._status and not self._by_person.get(person):
                self._by_person[person] = dict(self._status)
                self._save()

    def snapshot(self, person: Optional[str] = None) -> Dict:
        with self._lock:
            return {'status': dict(self._statuses(person)),
                    'collections': [{'id': c['id'], 'name': c['name'], 'games': list(c.get('games') or [])} for c in self._collections]}

    def for_game(self, key: str, person: Optional[str] = None) -> Dict:
        """{'play_status': key or None, 'collections': [ids]} for one game."""
        with self._lock:
            return {'play_status': self._statuses(person).get(key),
                    'collections': [c['id'] for c in self._collections if key in (c.get('games') or [])]}

    # --- Changing ---

    def set_status(self, key: str, status: Optional[str], person: Optional[str] = None):
        if status and status not in STATUS_KEYS:
            raise ValueError("Unknown play status")
        with self._lock:
            statuses = self._statuses(person)
            if status:
                statuses[key] = status
            else:
                statuses.pop(key, None)
            self._save()

    def create_collection(self, name: str) -> Dict:
        name = (name or '').strip()[:60]
        if not name:
            raise ValueError("A collection needs a name")
        with self._lock:
            if any(c['name'].lower() == name.lower() for c in self._collections):
                raise ValueError(f'There is already a collection called "{name}"')
            collection = {'id': uuid.uuid4().hex[:10], 'name': name, 'games': []}
            self._collections.append(collection)
            self._save()
            return dict(collection)

    def _find(self, collection_id: str) -> Dict:
        for collection in self._collections:
            if collection['id'] == collection_id:
                return collection
        raise KeyError(collection_id)

    def rename_collection(self, collection_id: str, name: str):
        name = (name or '').strip()[:60]
        if not name:
            raise ValueError("A collection needs a name")
        with self._lock:
            collection = self._find(collection_id)
            if any(c['name'].lower() == name.lower() and c is not collection for c in self._collections):
                raise ValueError(f'There is already a collection called "{name}"')
            collection['name'] = name
            self._save()

    def delete_collection(self, collection_id: str):
        with self._lock:
            self._collections.remove(self._find(collection_id))
            self._save()

    def set_membership(self, collection_id: str, keys, member: bool) -> int:
        """Add games to a collection or take them out (one key or several).
        Returns how many games' membership changed."""
        if isinstance(keys, str):
            keys = [keys]
        changed = 0
        with self._lock:
            games = self._find(collection_id).setdefault('games', [])
            for key in keys:
                if member and key not in games:
                    games.append(key)
                    changed += 1
                elif not member and key in games:
                    games.remove(key)
                    changed += 1
            if changed:
                self._save()
        return changed

    def move_game(self, old_key: str, new_key: Optional[str]):
        """A game's file was renamed (or, with no new key, removed)."""
        with self._lock:
            changed = False
            for statuses in [self._status, *self._by_person.values()]:
                if old_key in statuses:
                    status = statuses.pop(old_key)
                    if new_key:
                        statuses[new_key] = status
                    changed = True
            for collection in self._collections:
                games = collection.get('games') or []
                if old_key in games:
                    at = games.index(old_key)
                    games[at:at + 1] = [new_key] if new_key and new_key not in games else []
                    changed = True
            if changed:
                self._save()

    # --- EmulationStation custom collections ---

    def export(self, roms_path_on_device: str, favourites: Optional[List[str]] = None) -> List[str]:
        """Write each status and collection as custom-<name>.cfg in
        DATA_PATH/collections: one ROM path per line, as the device running
        EmulationStation sees it. Returns the file names written."""
        prefix = (roms_path_on_device or '').rstrip('/')
        snapshot = self.snapshot()
        groups = {label: [k for k, v in snapshot['status'].items() if v == key] for key, label in STATUSES}
        for collection in snapshot['collections']:
            groups[collection['name']] = collection['games']
        written = []
        try:
            self.export_dir.mkdir(parents=True, exist_ok=True)
            for name, games in groups.items():
                file_name = f"custom-{_UNSAFE_NAME_RE.sub('', name).strip() or 'collection'}.cfg"
                target = self.export_dir / file_name
                if games:
                    target.write_text(''.join(f"{prefix}/{key}\n" for key in sorted(games)), encoding='utf-8')
                    written.append(file_name)
                elif target.exists():
                    target.unlink()
            # Collections that were renamed or deleted
            for old in self.export_dir.glob('custom-*.cfg'):
                if old.name not in written:
                    old.unlink()
        except OSError as e:
            logger.warning(f"Couldn't write EmulationStation collections: {e}")
        return written
