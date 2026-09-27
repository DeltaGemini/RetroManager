"""
Gamelist XML Manager
Safely reads, modifies, and writes EmulationStation gamelist.xml files
"""

import logging
import shutil
from pathlib import Path
from typing import Dict, Iterable, List, Optional
from lxml import etree
from datetime import datetime

from backend.models import Game
from backend.media_index import XML_MEDIA_PREFIX, strip_dot_slash

logger = logging.getLogger(__name__)

class GamelistManager:
    """Manages gamelist.xml files with atomic writes"""

    def __init__(self, media_root: Optional[str] = None):
        self.parser = etree.XMLParser(remove_blank_text=True)
        self.media_root = Path(media_root) if media_root else None

    # Public Methods

    def save_game(self, system_name: str, game: Game, roms_base: str) -> bool:
        gamelist_path = Path(roms_base) / system_name / 'gamelist.xml'
        try:
            if gamelist_path.exists():
                tree = etree.parse(str(gamelist_path), self.parser)
                root = tree.getroot()
            else:
                root = etree.Element('gameList')
                tree = etree.ElementTree(root)

            existing = self._find_game(root, game.path)
            if existing is not None:
                self._update_game_element(existing, game)
            else:
                root.append(self._create_game_element(game))

            self._write_xml_atomic(tree, gamelist_path)
            logger.info(f"Saved game {game.name} to {system_name}")
            return True
        except Exception as e:
            logger.error(f"Error saving game: {e}")
            return False

    def update_game(self, system_name: str, rom_path: str, game: Game, roms_base: str) -> bool:
        gamelist_path = Path(roms_base) / system_name / 'gamelist.xml'
        if not gamelist_path.exists():
            logger.error(f"Gamelist does not exist: {gamelist_path}")
            return False
        try:
            tree = etree.parse(str(gamelist_path), self.parser)
            game_elem = self._find_game(tree.getroot(), rom_path)
            if game_elem is None:
                logger.warning(f"Game not found in gamelist: {rom_path}")
                return False
            self._update_game_element(game_elem, game)
            self._write_xml_atomic(tree, gamelist_path)
            logger.info(f"Updated game {game.name}")
            return True
        except Exception as e:
            logger.error(f"Error updating game: {e}")
            return False

    def delete_game(self, system_name: str, rom_path: str, roms_base: str) -> bool:
        gamelist_path = Path(roms_base) / system_name / 'gamelist.xml'
        if not gamelist_path.exists():
            logger.error(f"Gamelist does not exist: {gamelist_path}")
            return False
        try:
            tree = etree.parse(str(gamelist_path), self.parser)
            root = tree.getroot()
            game_elem = self._find_game(root, rom_path)
            if game_elem is None:
                # Some older entries were saved with the system name in front
                game_elem = self._find_game(root, f"{system_name}/{self._normalize_path(rom_path)}")
            if game_elem is None:
                logger.warning(f"Game not found in gamelist: {rom_path}")
                return False
            root.remove(game_elem)
            self._write_xml_atomic(tree, gamelist_path)
            logger.info(f"Deleted game entry: {rom_path}")
            return True
        except Exception as e:
            logger.error(f"Error deleting game: {e}")
            return False

    def preview_entry(self, system_name: str, rom_path: str, game: Game, roms_base: str) -> str:
        """The <game> element a save would write, as text. Starts from the
        existing entry so tags RetroManager doesn't edit are shown as kept."""
        import copy
        gamelist_path = Path(roms_base) / system_name / 'gamelist.xml'
        existing = None
        if gamelist_path.exists():
            tree = etree.parse(str(gamelist_path), self.parser)
            existing = self._find_game(tree.getroot(), rom_path)
        if existing is not None:
            game_elem = copy.deepcopy(existing)
            self._update_game_element(game_elem, game)
        else:
            game_elem = self._create_game_element(game)
        return etree.tostring(game_elem, encoding='unicode', pretty_print=True)

    # Bulk operations (used by the Scan panel). Each makes a dated backup first
    # and returns (number changed, backup file name).

    def backup(self, system_name: str, roms_base: str) -> Optional[str]:
        """Copy gamelist.xml to gamelist_<timestamp>.xml; returns the backup name."""
        gamelist_path = Path(roms_base) / system_name / 'gamelist.xml'
        if not gamelist_path.exists():
            return None
        backup_path = gamelist_path.parent / f"gamelist_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xml"
        shutil.copy2(gamelist_path, backup_path)
        return backup_path.name

    def relink_paths(self, system_name: str, roms_base: str, mapping: Dict[str, str]):
        """Point entries at different ROM files: {old rom path: new rom path}."""
        def apply(root):
            changed = 0
            for old, new in mapping.items():
                game_elem = self._find_game(root, old)
                if game_elem is not None:
                    self._set_or_update(game_elem, 'path', f"./{self._normalize_path(new)}")
                    changed += 1
            return changed
        return self._bulk_edit(system_name, roms_base, apply)

    def set_media_fields(self, system_name: str, roms_base: str, updates: Dict[str, Dict[str, str]]):
        """Set <image>/<thumbnail>/<video>: {rom path: {field: media-relative path}}."""
        def apply(root):
            changed = 0
            for rom_path, fields in updates.items():
                game_elem = self._find_game(root, rom_path)
                if game_elem is None:
                    continue
                for field, media_path in fields.items():
                    if field in ('image', 'thumbnail', 'video'):
                        self._set_or_update(game_elem, field, self._to_xml_media_path(media_path))
                changed += 1
            return changed
        return self._bulk_edit(system_name, roms_base, apply)

    def remove_entries(self, system_name: str, roms_base: str, rom_paths: Iterable[str]):
        """Remove entries from the gamelist (ROM and media files are untouched)."""
        def apply(root):
            changed = 0
            for rom_path in rom_paths:
                game_elem = self._find_game(root, rom_path)
                if game_elem is not None:
                    root.remove(game_elem)
                    changed += 1
            return changed
        return self._bulk_edit(system_name, roms_base, apply)

    def merge_disc_parts(self, system_name: str, roms_base: str, parts: Dict[str, str]):
        """Fold entries for disc tracks into their disc's entry: {track path: .cue path}.
        Details the disc entry lacks are copied from the track entry first; if the
        disc has no entry yet, the track entry becomes it."""
        import copy

        def apply(root):
            changed = 0
            for part_path, disc_path in parts.items():
                part_elem = self._find_game(root, part_path)
                if part_elem is None:
                    continue
                disc_elem = self._find_game(root, disc_path)
                if disc_elem is None:
                    self._set_or_update(part_elem, 'path', f"./{self._normalize_path(disc_path)}")
                else:
                    for child in part_elem:
                        if child.tag == 'path':
                            continue
                        existing = disc_elem.find(child.tag)
                        if existing is None or not (existing.text or '').strip():
                            if existing is not None:
                                disc_elem.remove(existing)
                            disc_elem.append(copy.deepcopy(child))
                    root.remove(part_elem)
                changed += 1
            return changed
        return self._bulk_edit(system_name, roms_base, apply)

    def set_names(self, system_name: str, roms_base: str, names: Dict[str, str]):
        """Rename entries: {rom path: new name}."""
        def apply(root):
            changed = 0
            for rom_path, name in names.items():
                game_elem = self._find_game(root, rom_path)
                if game_elem is not None and name:
                    self._set_or_update(game_elem, 'name', name)
                    changed += 1
            return changed
        return self._bulk_edit(system_name, roms_base, apply)

    def add_entries(self, system_name: str, roms_base: str, games: List[Game]):
        """Add entries for ROMs that have none (existing entries are skipped)."""
        def apply(root):
            changed = 0
            for game in games:
                if self._find_game(root, game.path) is None:
                    root.append(self._create_game_element(game))
                    changed += 1
            return changed
        return self._bulk_edit(system_name, roms_base, apply, create=True)

    # Internal Helpers

    def _bulk_edit(self, system_name: str, roms_base: str, apply, create: bool = False):
        gamelist_path = Path(roms_base) / system_name / 'gamelist.xml'
        if gamelist_path.exists():
            tree = etree.parse(str(gamelist_path), self.parser)
        elif create:
            tree = etree.ElementTree(etree.Element('gameList'))
        else:
            raise FileNotFoundError(f"gamelist.xml not found for {system_name}")

        changed = apply(tree.getroot())
        backup_name = None
        if changed:
            backup_name = self.backup(system_name, roms_base)
            self._write_xml_atomic(tree, gamelist_path)
        return changed, backup_name

    def _find_game(self, root: etree.Element, rom_path: str) -> Optional[etree.Element]:
        """Find a <game> by ROM path: exact match first, then ignoring case."""
        target = self._normalize_path(rom_path)
        fallback = None
        for game_elem in root.findall('.//game'):
            path_text = self._normalize_path(game_elem.findtext('path'))
            if path_text == target:
                return game_elem
            if fallback is None and path_text.lower() == target.lower():
                fallback = game_elem
        return fallback

    def _create_game_element(self, game: Game) -> etree.Element:
        game_elem = etree.Element('game')
        self._set_element(game_elem, 'path', f"./{self._normalize_path(game.path)}")
        self._set_element(game_elem, 'name', game.name)
        if game.desc:
            self._set_element(game_elem, 'desc', game.desc)
        for field in ('image', 'thumbnail', 'video'):
            xml_path = self._to_xml_media_path(getattr(game, field))
            if xml_path:
                self._set_element(game_elem, field, xml_path)
        # other fields
        if game.rating is not None:
            self._set_element(game_elem, 'rating', str(game.rating))
        if game.releasedate:
            self._set_element(game_elem, 'releasedate', game.releasedate)
        if game.developer:
            self._set_element(game_elem, 'developer', game.developer)
        if game.publisher:
            self._set_element(game_elem, 'publisher', game.publisher)
        if game.genre:
            self._set_element(game_elem, 'genre', game.genre)
        if game.players:
            self._set_element(game_elem, 'players', game.players)
        if game.favorite:
            self._set_element(game_elem, 'favorite', 'true')
        if game.playcount and game.playcount > 0:
            self._set_element(game_elem, 'playcount', str(game.playcount))
        if game.lastplayed:
            self._set_element(game_elem, 'lastplayed', game.lastplayed)
        return game_elem

    def _update_game_element(self, game_elem: etree.Element, game: Game):
        self._set_or_update(game_elem, 'path', f"./{self._normalize_path(game.path)}")
        self._set_or_update(game_elem, 'name', game.name)
        self._set_or_update(game_elem, 'desc', game.desc)
        for field in ('image', 'thumbnail', 'video'):
            self._set_or_update(game_elem, field, self._to_xml_media_path(getattr(game, field)))
        self._set_or_update(game_elem, 'rating', str(game.rating) if game.rating is not None else None)
        self._set_or_update(game_elem, 'releasedate', game.releasedate)
        self._set_or_update(game_elem, 'developer', game.developer)
        self._set_or_update(game_elem, 'publisher', game.publisher)
        self._set_or_update(game_elem, 'genre', game.genre)
        self._set_or_update(game_elem, 'players', game.players)
        self._set_or_update(game_elem, 'favorite', 'true' if game.favorite else None)
        self._set_or_update(game_elem, 'playcount', str(game.playcount) if game.playcount is not None and game.playcount > 0 else None)
        self._set_or_update(game_elem, 'lastplayed', game.lastplayed)

    def _set_element(self, parent: etree.Element, tag: str, text: str):
        elem = etree.SubElement(parent, tag)
        elem.text = text

    def _set_or_update(self, parent: etree.Element, tag: str, text: Optional[str]):
        elem = parent.find(tag)
        if text is None or text == '':
            if elem is not None:
                parent.remove(elem)
        else:
            if elem is None:
                elem = etree.SubElement(parent, tag)
            elem.text = text

    def _write_xml_atomic(self, tree: etree.ElementTree, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix('.xml.tmp')
        backup_path = path.with_suffix('.xml.bak')
        tree.write(str(temp_path), encoding='UTF-8', xml_declaration=True, pretty_print=True)
        if path.exists():
            shutil.copy2(path, backup_path)
        temp_path.replace(path)
        if backup_path.exists():
            try:
                backup_path.unlink()
            except Exception:
                pass

    @staticmethod
    def _normalize_path(path: str) -> str:
        return strip_dot_slash(path)

    def _to_xml_media_path(self, media_path) -> Optional[str]:
        """Media path as the app holds it -> the form written to gamelist.xml.

        "Nintendo 3DS/images/x.png" -> "../../media/Nintendo 3DS/images/x.png".
        Paths already in XML form ("../../media/...", "./...") are kept as they are,
        and absolute paths under the media mount are made relative first.
        """
        if not media_path or not isinstance(media_path, str):
            return None
        p = media_path.replace('\\', '/')
        if self.media_root and p.startswith(self.media_root.as_posix().rstrip('/') + '/'):
            p = p[len(self.media_root.as_posix().rstrip('/')) + 1:]
        elif p.startswith(('../', './', '/', '~')):
            return p
        return f"{XML_MEDIA_PREFIX}/{p}"
