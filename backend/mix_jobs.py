"""
Generating Mix pictures for games that have none: what can be made (the
inventory), making previews in the background, and putting the approved ones in
the library.

Previews go to a staging folder in DATA_PATH, never the media folders; only a
commit writes to the library. A commit doesn't replace a Mix that's already
there unless told to (overwrite), except one RetroManager generated itself, and
whatever it replaces is put in a tarball in DATA_PATH/mix-backups first.

Which Mix pictures were generated is kept in DATA_PATH/mix-generated.json,
keyed by "system/rom path", and written into each PNG as well.
"""

import json
import logging
import os
import shutil
import tarfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from backend import mix_generator
from backend.media_index import strip_dot_slash
from backend.mix_generator import MixError

logger = logging.getLogger(__name__)

# Media folders a Mix can be made from
ASSET_FOLDERS = ('screenshot', 'screenshottitle', 'box3d', 'box2d', 'support', 'wheel')
IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}
# Few at a time: the backend may be a Raspberry Pi, and each one holds a few pictures in memory
DEFAULT_WORKERS = 2
# Previews nobody committed are cleared away after this long
DEFAULT_MAX_AGE_HOURS = 24
OPTION_KEYS = ('box', 'media', 'wheel', 'box_type', 'screenshot')


def _clean_options(options) -> Dict:
    return {k: v for k, v in (options or {}).items() if k in OPTION_KEYS and v is not None} if isinstance(options, dict) else {}


class MixProvenance:
    """Which games' Mix pictures RetroManager generated, and from what."""

    def __init__(self, data_dir: Path):
        self.state_file = Path(data_dir) / 'mix-generated.json'
        self._lock = threading.Lock()
        try:
            self._games: Dict[str, Dict] = json.loads(self.state_file.read_text())
        except (OSError, ValueError):
            self._games = {}

    def _save(self):
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.state_file.with_suffix('.tmp')
            tmp.write_text(json.dumps(self._games, indent=1))
            tmp.replace(self.state_file)
        except OSError as e:
            logger.warning(f"Couldn't save the generated Mix list: {e}")

    @staticmethod
    def key(system: str, rom_path: str) -> str:
        return f"{system}/{strip_dot_slash(rom_path)}"

    def get(self, system: str, rom_path: str) -> Optional[Dict]:
        with self._lock:
            return self._games.get(self.key(system, rom_path))

    def is_generated(self, system: str, rom_path: str) -> bool:
        return self.get(system, rom_path) is not None

    def record(self, system: str, rom_path: str, info: Dict):
        with self._lock:
            self._games[self.key(system, rom_path)] = info
            self._save()

    def forget(self, system: str, rom_path: str):
        """The game's Mix was replaced by one from somewhere else, or removed."""
        with self._lock:
            if self._games.pop(self.key(system, rom_path), None) is not None:
                self._save()

    def game_moved(self, system: str, old: str, new: Optional[str]):
        with self._lock:
            info = self._games.pop(self.key(system, old), None)
            if info is None:
                return
            if new:
                self._games[self.key(system, new)] = info
            self._save()


class MixJobs:
    def __init__(self, data_dir: Path, scanner, gamelist_mgr, roms_base, media_base, provenance: MixProvenance,
                 workers: int = DEFAULT_WORKERS, max_age_hours: float = DEFAULT_MAX_AGE_HOURS):
        self.staging_dir = Path(data_dir) / 'mix-staging'
        self.backup_dir = Path(data_dir) / 'mix-backups'
        self.template_dirs = (mix_generator.TEMPLATE_DIR, Path(data_dir) / 'mix_templates')
        self.scanner = scanner
        self.gamelist_mgr = gamelist_mgr
        self.roms_base = roms_base
        self.media_base = Path(media_base)
        self.provenance = provenance
        self.max_age_hours = max_age_hours
        self._pool = ThreadPoolExecutor(max_workers=max(1, workers), thread_name_prefix='mix')
        self._lock = threading.RLock()
        self._jobs: Dict[str, Dict] = {}
        self._load_jobs()

    # --- Templates ---

    def templates(self) -> Dict[str, Dict]:
        """Read from disk each time, so an edited template is used straight away."""
        return mix_generator.load_templates(self.template_dirs)

    def default_template(self, system: str, templates: Dict[str, Dict]) -> Optional[str]:
        return mix_generator.default_template(system, templates, self.template_dirs)

    # --- Inventory: what can be made (reads only) ---

    def _system_names(self) -> Dict[str, str]:
        return {s.name: s.get_full_name() for s in self.scanner.discover_systems()}

    def _describe(self, system: str, system_name: str, game, template: Dict, options: Dict) -> Dict:
        available = {f: getattr(game, f) for f in ASSET_FOLDERS if getattr(game, f, None)}
        found = mix_generator.candidates(template, available, options)
        tier, reason = mix_generator.classify(found)
        return {'system': system, 'system_name': system_name, 'rom_path': strip_dot_slash(game.path), 'name': game.name,
                'tier': tier, 'reason': reason, 'roles': {role: paths[0][0] for role, paths in found.items()},
                'available': available, 'has_mix': bool(game.mix),
                'mix_generated': bool(game.mix) and self.provenance.is_generated(system, game.path),
                'template': template['name'], 'options': options}

    def inventory(self, systems: Optional[List[str]] = None, games: Optional[List[Dict]] = None,
                  template: Optional[str] = None, options: Optional[Dict] = None, generated: bool = False) -> Dict:
        """What a job for these would make. With games ([{system, rom_path,
        template?, options?}]), exactly those; otherwise every game without a
        Mix on the systems named (all of them when none are), or with
        generated, every game whose Mix RetroManager made, to make it again. Returns
        {'systems': [{system, full_name, total, full, partial, ineligible}],
         'games': [...], 'unknown': games asked for that aren't in the library}."""
        templates = self.templates()
        if not templates:
            raise MixError('template', "No Mix templates found")
        if template and template not in templates:
            raise MixError('template', f"There's no Mix template called {template}")
        names = self._system_names()
        wanted: Dict[str, Optional[Dict[str, Dict]]] = {}
        if games is not None:
            for g in games:
                if isinstance(g, dict) and g.get('system') in names and g.get('rom_path'):
                    wanted.setdefault(g['system'], {})[strip_dot_slash(g['rom_path'])] = g
        else:
            wanted = {name: None for name in (systems or sorted(names)) if name in names}

        described, counts = [], []
        for system, picked in wanted.items():
            try:
                library = self.scanner.get_games_for_system(system)
            except Exception as e:
                logger.warning(f"Mix inventory: couldn't list {system}: {e}")
                continue
            entries = []
            for game in sorted(library, key=lambda g: (g.name or '').lower()):
                if not game.rom_exists:
                    continue
                asked = picked.get(strip_dot_slash(game.path)) if picked is not None else None
                if picked is not None and asked is None:
                    continue
                if picked is None and (not (game.mix and self.provenance.is_generated(system, game.path)) if generated else game.mix):
                    continue
                name = (asked or {}).get('template') or template or self.default_template(system, templates)
                if name not in templates:
                    raise MixError('template', f"There's no Mix template called {name}")
                chosen = {**_clean_options(options), **_clean_options((asked or {}).get('options'))}
                entries.append(self._describe(system, names[system], game, templates[name], chosen))
            if entries:
                counts.append({'system': system, 'full_name': names[system], 'total': len(entries),
                               **{tier: sum(1 for e in entries if e['tier'] == tier) for tier in ('full', 'partial', 'ineligible')}})
            described.extend(entries)
        found = {(e['system'], e['rom_path']) for e in described}
        unknown = [{'system': g.get('system'), 'rom_path': g.get('rom_path')} for g in games or []
                   if isinstance(g, dict) and (g.get('system'), strip_dot_slash(g.get('rom_path'))) not in found]
        return {'systems': counts, 'games': described, 'unknown': unknown}

    # --- Jobs ---

    def _job_dir(self, job_id: str) -> Path:
        return self.staging_dir / job_id

    def preview_file(self, job_id: str, index: int) -> Optional[Path]:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job or not 0 <= index < len(job['items']) or job['items'][index]['status'] != 'ready':
                return None
        path = self._job_dir(job_id) / f"{index}.png"
        return path if path.is_file() else None

    def _save_job(self, job: Dict):
        try:
            folder = self._job_dir(job['id'])
            folder.mkdir(parents=True, exist_ok=True)
            tmp = folder / 'job.json.tmp'
            tmp.write_text(json.dumps(job))
            tmp.replace(folder / 'job.json')
        except OSError as e:
            logger.warning(f"Couldn't save Mix job {job['id']}: {e}")

    def _load_jobs(self):
        """Previews made before a restart can still be reviewed and committed."""
        try:
            folders = [f for f in self.staging_dir.iterdir() if f.is_dir()]
        except OSError:
            return
        for folder in folders:
            try:
                job = json.loads((folder / 'job.json').read_text())
            except (OSError, ValueError):
                continue
            for item in job.get('items') or []:
                if item['status'] in ('pending', 'rendering'):
                    item.update(status='failed', reason='interrupted', error="A restart interrupted this one. Regenerate it.")
            self._jobs[job['id']] = job

    @staticmethod
    def _summary(job: Dict) -> Dict:
        statuses = [item['status'] for item in job['items']]
        count = statuses.count
        return {'id': job['id'], 'created': job['created'], 'running': bool(count('pending') or count('rendering')),
                'total': len(statuses) - count('ineligible'),
                'done': count('ready') + count('failed') + count('committed') + count('rejected'),
                'ready': count('ready'), 'failed': count('failed'), 'ineligible': count('ineligible'),
                'committed': count('committed'), 'rejected': count('rejected')}

    def list_jobs(self) -> List[Dict]:
        with self._lock:
            return sorted((self._summary(j) for j in self._jobs.values()), key=lambda j: j['created'], reverse=True)

    def get(self, job_id: str) -> Optional[Dict]:
        with self._lock:
            job = self._jobs.get(job_id)
            return {**self._summary(job), 'items': json.loads(json.dumps(job['items']))} if job else None

    def start(self, systems: Optional[List[str]] = None, games: Optional[List[Dict]] = None,
              template: Optional[str] = None, options: Optional[Dict] = None, generated: bool = False) -> Dict:
        """Start making previews. Games that can't have one are kept in the job
        with the reason, so the review can list them."""
        self.cleanup()
        report = self.inventory(systems, games, template, options, generated)
        items = []
        for index, entry in enumerate(report['games']):
            eligible = entry['tier'] != 'ineligible'
            items.append({**entry, 'index': index, 'status': 'pending' if eligible else 'ineligible',
                          'error': None, 'warnings': [], 'used': {}, 'template_version': None, 'rev': 0})
        job = {'id': uuid.uuid4().hex[:12], 'created': datetime.now().isoformat(timespec='seconds'), 'items': items}
        with self._lock:
            self._jobs[job['id']] = job
            self._save_job(job)
        for item in items:
            if item['status'] == 'pending':
                self._pool.submit(self._render, job['id'], item['index'])
        return self.get(job['id'])

    def regenerate(self, job_id: str, changes: List[Dict]) -> Optional[Dict]:
        """Make some of a job's previews again: [{index, template?, options?}]."""
        templates = self.templates()
        again = []
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            for change in changes:
                index = change.get('index') if isinstance(change, dict) else None
                if not isinstance(index, int) or not 0 <= index < len(job['items']):
                    continue
                item = job['items'][index]
                if item['status'] in ('pending', 'rendering', 'committed'):
                    continue
                name = change.get('template') or item['template']
                if name not in templates:
                    raise MixError('template', f"There's no Mix template called {name}")
                if 'options' in change:
                    item['options'] = _clean_options(change['options'])
                found = mix_generator.candidates(templates[name], item['available'], item['options'])
                tier, reason = mix_generator.classify(found)
                item.update(template=name, tier=tier, reason=reason, error=None, warnings=[],
                            roles={role: paths[0][0] for role, paths in found.items()},
                            status='ineligible' if tier == 'ineligible' else 'pending')
                if item['status'] == 'pending':
                    again.append(index)
            self._save_job(job)
        for index in again:
            self._pool.submit(self._render, job_id, index)
        return self.get(job_id)

    def _render(self, job_id: str, index: int):
        """One game's preview, in a worker. A failure is that game's alone."""
        with self._lock:
            job = self._jobs.get(job_id)
            if not job or job['items'][index]['status'] != 'pending':
                return
            item = job['items'][index]
            item['status'] = 'rendering'
            name, options, available = item['template'], dict(item['options']), dict(item['available'])
        result = {}
        try:
            template = self.templates().get(name)
            if not template:
                raise MixError('template', f"There's no Mix template called {name}")
            sources = {role: [(folder, self.media_base / path) for folder, path in paths]
                       for role, paths in mix_generator.candidates(template, available, options).items()}
            picture, used, warnings = mix_generator.render_mix(template, sources)
            try:
                folder = self._job_dir(job_id)
                folder.mkdir(parents=True, exist_ok=True)
                record = mix_generator.provenance(template, used, {role: available[f] for role, f in used.items()})
                tmp = folder / f"{index}.png.part"
                mix_generator.save_png(picture, tmp, record)
                os.replace(tmp, folder / f"{index}.png")
            finally:
                picture.close()
            result = dict(status='ready', used=used, warnings=warnings, record=record,
                          template_version=template.get('version', 1), tier=mix_generator.classify(used)[0])
        except MixError as e:
            result = dict(status='failed', reason=e.reason, error=str(e))
        except Exception as e:
            logger.exception(f"Mix preview failed for job {job_id} item {index}")
            result = dict(status='failed', reason='render_error', error=str(e))
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return  # discarded while this one was being made
            item = job['items'][index]
            item.update(result, rev=item['rev'] + 1)
            if not self._summary(job)['running']:
                self._save_job(job)

    def discard(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.pop(job_id, None)
        shutil.rmtree(self._job_dir(job_id), ignore_errors=True)
        return job is not None

    def cleanup(self):
        """Clear away sets of previews untouched for max_age_hours."""
        cutoff = time.time() - self.max_age_hours * 3600
        try:
            folders = [f for f in self.staging_dir.iterdir() if f.is_dir()]
        except OSError:
            return
        for folder in folders:
            with self._lock:
                job = self._jobs.get(folder.name)
                if job and self._summary(job)['running']:
                    continue
            try:
                if folder.stat().st_mtime < cutoff:
                    self.discard(folder.name)
            except OSError:
                pass

    # --- Commit: approved previews into the library ---

    def _existing(self, mix_dir: Path) -> Dict[str, List[Path]]:
        """{file name without extension, lowercased: the Mix files with that name}."""
        found: Dict[str, List[Path]] = {}
        try:
            for f in mix_dir.iterdir():
                if f.is_file() and not f.name.startswith('.') and f.suffix.lower() in IMAGE_EXTENSIONS:
                    found.setdefault(f.stem.lower(), []).append(f)
        except OSError:
            pass
        return found

    def _back_up(self, files: List[Path]) -> Optional[str]:
        if not files:
            return None
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        target = self.backup_dir / f"mix-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4]}.tar.gz"
        tmp = target.with_suffix('.part')
        with tarfile.open(tmp, 'w:gz') as archive:
            for f in files:
                archive.add(f, arcname=str(f.relative_to(self.media_base)))
        tmp.replace(target)
        return target.name

    def commit(self, job_id: str, approve: List[int], overwrite: bool = False, reject: Optional[List[int]] = None) -> Optional[Dict]:
        """Put the approved previews in the library as <media system>/mix/<ROM
        name>.png and throw the rejected ones away. Returns {'results': [{index,
        status: committed | needs_overwrite | not_ready | failed, ...}],
        'backup': the tarball of replaced files, 'linked': gamelist entries whose
        <image> was filled}."""
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            valid = lambda i: isinstance(i, int) and 0 <= i < len(job['items'])
            items = [dict(job['items'][i]) for i in dict.fromkeys(approve) if valid(i)]
            rejected = [i for i in reject or [] if valid(i) and job['items'][i]['status'] in ('ready', 'failed')]

        results, plans, replaced = [], [], []
        listings: Dict[str, Dict[str, List[Path]]] = {}
        for item in items:
            staged = self._job_dir(job_id) / f"{item['index']}.png"
            if item['status'] != 'ready' or not staged.is_file():
                results.append({'index': item['index'], 'status': 'not_ready'})
                continue
            media_system = self.scanner._resolve_media_system(item['system'])
            mix_dir = self.media_base / media_system / 'mix'
            if media_system not in listings:
                listings[media_system] = self._existing(mix_dir)
            stem = Path(item['rom_path']).stem
            existing = listings[media_system].get(stem.lower(), [])
            # A Mix RetroManager made may be made again; anything else needs the say-so
            if not overwrite and any(mix_generator.read_provenance(f) is None for f in existing):
                results.append({'index': item['index'], 'status': 'needs_overwrite',
                                'existing': f"{media_system}/mix/{existing[0].name}"})
                continue
            plans.append((item, staged, mix_dir, stem, media_system, existing))
            replaced.extend(existing)

        backup = self._back_up(replaced) if replaced else None
        written: Dict[str, List[Dict]] = {}
        for item, staged, mix_dir, stem, media_system, existing in plans:
            try:
                mix_dir.mkdir(parents=True, exist_ok=True)
                final = mix_dir / f"{stem}.png"
                tmp = mix_dir / f".{stem}.png.part"
                try:
                    shutil.copyfile(staged, tmp)
                    os.replace(tmp, final)
                finally:
                    if tmp.exists():
                        tmp.unlink()
                # The same game's Mix in another format would be found ahead of the new one
                for old in existing:
                    if old != final and old.exists():
                        old.unlink()
                staged.unlink()
                path = f"{media_system}/mix/{final.name}"
                self.provenance.record(item['system'], item['rom_path'], {**(item.get('record') or {}), 'file': path})
                written.setdefault(item['system'], []).append(item)
                results.append({'index': item['index'], 'status': 'committed', 'path': path, 'replaced': bool(existing)})
            except OSError as e:
                logger.exception(f"Couldn't put the Mix for {item['system']}/{item['rom_path']} in the library")
                results.append({'index': item['index'], 'status': 'failed', 'error': str(e)})

        linked, gamelist_backups = self._link(written)
        outcome = {r['index']: r['status'] for r in results}
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                for index, status in outcome.items():
                    if status == 'committed':
                        job['items'][index].update(status='committed', has_mix=True, mix_generated=True)
                for index in rejected:
                    if outcome.get(index) != 'committed':
                        job['items'][index]['status'] = 'rejected'
                        (self._job_dir(job_id) / f"{index}.png").unlink(missing_ok=True)
                self._save_job(job)
        return {'results': results, 'backup': backup, 'linked': linked, 'gamelist_backups': gamelist_backups,
                'committed': sum(1 for r in results if r['status'] == 'committed')}

    def _link(self, written: Dict[str, List[Dict]]):
        """Fill <image> for the games whose entry has none (or one pointing at a
        file that's gone), as the Scan's Link media does. Each gamelist is backed
        up before it's changed."""
        linked, backups = 0, {}
        for system, items in written.items():
            try:
                games = {strip_dot_slash(g.path): g for g in self.scanner.get_games_for_system(system)}
                index = self.scanner.media_index(system)
                updates = {}
                for item in items:
                    game = games.get(item['rom_path'])
                    if not game or not game.has_metadata or (game.image and (self.media_base / game.image).is_file()):
                        continue
                    image = index.suggest_links(Path(item['rom_path']).stem).get('image')
                    if image:
                        updates[item['rom_path']] = {'image': image}
                if updates:
                    changed, backup = self.gamelist_mgr.set_media_fields(system, self.roms_base, updates)
                    linked += changed
                    if backup:
                        backups[system] = backup
            except Exception:
                logger.exception(f"Couldn't link the new Mix pictures in {system}'s gamelist")
        return linked, backups
