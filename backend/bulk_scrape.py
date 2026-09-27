"""
Match many ROMs to ScreenScraper games at once, for the Bulk scrape panel.

Each ROM is first identified by its file name (ScreenScraper keeps a database of
ROM file names), then, if that fails or looks wrong, by a title search. Every
match gets a confidence the UI uses to decide what's pre-ticked:
    exact   ScreenScraper recognised this exact ROM file
    likely  the game's name closely matches the ROM's title
    unsure  a match was found but the names differ; check it
    none    nothing found
"""

import re
from collections import OrderedDict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Optional

from backend.media_index import title_key
from backend.models import Game
from backend.scraper import ScreenscraperAPI, ScreenscraperNotFound
from backend.systems import screenscraper_system_id

LIKELY_SCORE = 0.85
MAX_ALTERNATIVES = 6

_DIGITS_RE = re.compile(r'\d+')


class JeuCache:
    """Recently seen ScreenScraper games, so applying a match needs no second lookup."""

    def __init__(self, size: int = 1000):
        self.size = size
        self.items: "OrderedDict[str, Dict]" = OrderedDict()

    def put(self, jeu: Dict):
        key = str(jeu.get('id'))
        self.items[key] = jeu
        self.items.move_to_end(key)
        while len(self.items) > self.size:
            self.items.popitem(last=False)

    def get(self, game_id) -> Optional[Dict]:
        return self.items.get(str(game_id))


def name_score(rom_stem: str, jeu: Dict) -> float:
    """0-1 similarity between the ROM's title and the game's best-matching name.
    Different numbers ("2" vs "3") are penalised so sequels don't match."""
    key = title_key(rom_stem)
    if not key:
        return 0.0
    best = 0.0
    for entry in jeu.get('noms') or []:
        name_key = title_key((entry or {}).get('text', ''))
        if not name_key:
            continue
        score = SequenceMatcher(None, key, name_key).ratio()
        if _DIGITS_RE.findall(key) != _DIGITS_RE.findall(name_key):
            score *= 0.7
        best = max(best, score)
    return best


def _search_title(rom_stem: str) -> str:
    """Search text for a ROM: its file name without tags, underscores or extra spaces."""
    return Game.from_filename(rom_stem + '.x').name


class BulkMatcher:
    def __init__(self, scraper: ScreenscraperAPI, cache: JeuCache):
        self.scraper = scraper
        self.cache = cache

    def _summary(self, jeu: Dict, score: float) -> Dict:
        summary = self.scraper.summarize_search_result(jeu)
        summary.pop('jeu', None)
        summary['score'] = round(score, 2)
        return summary

    def match(self, system: str, rom_path: str, rom_file: Optional[Path], query: Optional[str] = None,
              title: Optional[str] = None, md5: Optional[str] = None) -> Dict:
        """Best ScreenScraper match for one ROM, plus alternatives.
        With `query`, skip the file-name lookup and search that text instead.
        `title` replaces the file name as the game's title for searching and
        scoring (a PC game's folder name rather than "STARTREK.EXE")."""
        rom_name = Path(rom_path).name
        rom_stem = title or Path(rom_path).stem
        system_id = screenscraper_system_id(system)
        size = rom_file.stat().st_size if rom_file and rom_file.is_file() else None

        # A search you typed is what results are compared with
        basis = query.strip() if query else rom_stem
        candidates = {}  # jeu id -> (jeu, score)
        confidence = 'none'
        best_id = None

        # 1. Identify by ROM file name
        try:
            if query:
                raise ScreenscraperNotFound("custom search")
            jeu = self.scraper.identify_rom(rom_name, system_id, size, md5)
            self.cache.put(jeu)
            matched_file = ((jeu.get('rom') or {}).get('romfilename') or '').lower()
            # A checksum match is exact whatever the file is called (ScreenScraper
            # can fall back to the name, so check the checksum it matched)
            matched_md5 = str((jeu.get('rom') or {}).get('rommd5') or '').lower()
            exact = (bool(md5) and matched_md5 == md5.lower()) or matched_file == rom_name.lower() \
                or Path(matched_file).stem == rom_stem.lower()
            score = 1.0 if exact else name_score(rom_stem, jeu)
            candidates[str(jeu['id'])] = (jeu, score)
            best_id = str(jeu['id'])
            confidence = 'exact' if exact else ('likely' if score >= LIKELY_SCORE else 'unsure')
        except ScreenscraperNotFound:
            pass

        # 2. Title search when the file name wasn't recognised, or the result looks off
        if confidence not in ('exact', 'likely'):
            query = query or _search_title(rom_stem)
            try:
                # ScreenScraper refuses searches under 3 characters
                results = self.scraper.search_game(query, system_id) if query and len(query.strip()) >= 3 else []
            except ScreenscraperNotFound:
                results = []
            for jeu in results:
                self.cache.put(jeu)
                score = name_score(basis, jeu)
                if 'hack' in ((jeu.get('systeme') or {}).get('text') or '').lower():
                    score *= 0.8  # an original beats a ROM hack with the same name
                candidates.setdefault(str(jeu['id']), (jeu, score))
            if candidates:
                top_id = max(candidates, key=lambda k: candidates[k][1])
                if best_id is None or candidates[top_id][1] > candidates[best_id][1]:
                    best_id = top_id
                    top_score = candidates[top_id][1]
                    confidence = 'likely' if top_score >= LIKELY_SCORE else 'unsure'

        ranked = sorted(candidates.items(), key=lambda kv: kv[1][1], reverse=True)
        alternatives = [self._summary(jeu, score) for _, (jeu, score) in ranked[:MAX_ALTERNATIVES]]
        return {
            'rom_path': rom_path,
            'confidence': confidence,
            'match_id': best_id,
            'alternatives': alternatives,
        }
