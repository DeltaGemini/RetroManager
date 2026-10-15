"""
Profiles and signing in.

A profile is a person the app already knows by their saves folder
(saves/<name>/, savestates/<name>/). Each has a role, admin or player, and
admins a PIN. With login switched on, a device says who's using it (a signed
cookie, kept until they switch or sign out); play status, the want list,
achievements and preferences are then that person's, and only an admin can
change the library. With it off, the app is as it was: one shared set of
everything, and anyone can do anything.

Kept in DATA_PATH/accounts.json:
    enabled   whether login is on
    people    the profiles' names, in order (to begin with, the SAVE_PROFILES setting)
    profiles  name -> {role, pin (hashed), pin_version, photo, prefs, prefs_at}
    secret    what the cookies are signed with

A file called "reset-login" put in DATA_PATH switches login off (for a
forgotten PIN): it's noticed on the next request, and removed.
"""

import base64
import hashlib
import hmac
import json
import re
import secrets
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

from werkzeug.security import check_password_hash, generate_password_hash

ROLES = ('admin', 'player')
NAME_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_\-]{0,23}$')
PIN_RE = re.compile(r'^\d{4,8}$')
MAX_TRIES = 5        # wrong PINs before a wait
LOCKOUT = 60         # seconds
MAX_PREFS_BYTES = 64 * 1024


class Accounts:
    def __init__(self, data_dir: Path, people: List[str]):
        """people: the list of profile names the rest of the app uses
        (core.SAVE_PROFILES); it's kept in step with what's stored here."""
        self.file = Path(data_dir) / 'accounts.json'
        self.reset_file = Path(data_dir) / 'reset-login'
        self.photo_dir = Path(data_dir) / 'profiles'
        self._people = people
        self._lock = threading.RLock()
        self._tries: Dict[str, List[float]] = {}
        try:
            data = json.loads(self.file.read_text())
        except (OSError, ValueError):
            data = {}
        self._data = {
            'enabled': bool(data.get('enabled')),
            'secret': data.get('secret') or secrets.token_hex(32),
            'profiles': data.get('profiles') if isinstance(data.get('profiles'), dict) else {},
        }
        stored = [p for p in data.get('people') or [] if isinstance(p, str) and NAME_RE.match(p)]
        if stored:
            self._people[:] = stored
        if 'secret' not in data:
            self._save()

    def _save(self):
        try:
            self.file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.file.with_suffix('.tmp')
            tmp.write_text(json.dumps({**self._data, 'people': list(self._people)}, indent=1))
            tmp.replace(self.file)
        except OSError:
            pass

    # ------------------------------------------------------------------
    @property
    def enabled(self) -> bool:
        if self._data['enabled'] and self.reset_file.exists():
            with self._lock:
                self._data['enabled'] = False
                self._save()
            try:
                self.reset_file.unlink()
            except OSError:
                pass
        return self._data['enabled']

    def people(self) -> List[str]:
        return list(self._people)

    def _profile(self, name: str) -> Dict:
        return self._data['profiles'].setdefault(name, {})

    def role(self, name: str) -> str:
        role = (self._data['profiles'].get(name) or {}).get('role')
        return role if role in ROLES else 'player'

    def describe(self) -> List[Dict]:
        """Every profile as the pages need it: nothing secret."""
        with self._lock:
            return [{'name': name, 'role': self.role(name), 'has_pin': bool((self._data['profiles'].get(name) or {}).get('pin')),
                     'photo': (self._data['profiles'].get(name) or {}).get('photo')} for name in self._people]

    # ------------------------------------------------------------------
    # Changing profiles
    # ------------------------------------------------------------------
    def add_person(self, name: str):
        name = (name or '').strip()
        if not NAME_RE.match(name):
            raise ValueError("A name is up to 24 letters, digits, - or _ (it becomes a folder name)")
        if name.lower() in ('shared', 'users'):
            raise ValueError(f'"{name}" means something else here: choose another name')
        with self._lock:
            if any(p.lower() == name.lower() for p in self._people):
                raise ValueError(f'There is already a profile called "{name}"')
            self._people.append(name)
            self._save()

    def set_role(self, name: str, role: str):
        if name not in self._people or role not in ROLES:
            raise ValueError("Unknown profile or role")
        with self._lock:
            if role != 'admin' and self._data['enabled'] and self.role(name) == 'admin' and not any(
                    self.role(p) == 'admin' and (self._data['profiles'].get(p) or {}).get('pin') for p in self._people if p != name):
                raise ValueError("That's the only admin with a PIN: make someone else one first, or switch login off")
            self._profile(name)['role'] = role
            self._save()

    def set_pin(self, name: str, pin: Optional[str]):
        if name not in self._people:
            raise ValueError("Unknown profile")
        if pin and not PIN_RE.match(pin):
            raise ValueError("A PIN is 4 to 8 digits")
        with self._lock:
            profile = self._profile(name)
            if not pin and self._data['enabled'] and self.role(name) == 'admin':
                raise ValueError("An admin needs a PIN while login is on")
            profile['pin'] = generate_password_hash(pin) if pin else None
            # Signed-in devices for this profile are signed out
            profile['pin_version'] = int(profile.get('pin_version') or 0) + 1
            self._save()

    def set_enabled(self, enabled: bool):
        with self._lock:
            if enabled and not any(self.role(p) == 'admin' and (self._data['profiles'].get(p) or {}).get('pin') for p in self._people):
                raise ValueError("Make someone an admin and give them a PIN first")
            self._data['enabled'] = bool(enabled)
            self._save()

    def set_photo(self, name: str, filename: Optional[str]):
        with self._lock:
            self._profile(name)['photo'] = filename
            self._save()

    # ------------------------------------------------------------------
    # Signing in
    # ------------------------------------------------------------------
    def check_pin(self, name: str, pin: str) -> Optional[str]:
        """None if the PIN is right, else what to say."""
        now = time.time()
        with self._lock:
            tries = [t for t in self._tries.get(name, []) if now - t < LOCKOUT]
            if len(tries) >= MAX_TRIES:
                return f"Too many wrong PINs. Try again in {int(LOCKOUT - (now - tries[0])) + 1} seconds."
            stored = (self._data['profiles'].get(name) or {}).get('pin')
            if stored and check_password_hash(stored, pin or ''):
                self._tries.pop(name, None)
                return None
            self._tries[name] = tries + [now]
            return "That's not the PIN."

    def _sign(self, body: bytes) -> str:
        return hmac.new(self._data['secret'].encode(), body, hashlib.sha256).hexdigest()

    def token_for(self, name: str) -> str:
        """What a signed-in device keeps: who, and which PIN they signed in under."""
        body = base64.urlsafe_b64encode(json.dumps({
            'p': name, 'v': int((self._data['profiles'].get(name) or {}).get('pin_version') or 0), 't': int(time.time())}).encode())
        return f"{body.decode()}.{self._sign(body)}"

    def who(self, token: Optional[str]) -> Optional[str]:
        """The profile a cookie is for, or None if it's missing, forged or out of date."""
        if not token or '.' not in token:
            return None
        body, _, signature = token.rpartition('.')
        if not hmac.compare_digest(self._sign(body.encode()), signature):
            return None
        try:
            claim = json.loads(base64.urlsafe_b64decode(body.encode()))
        except (ValueError, TypeError):
            return None
        name = claim.get('p')
        if name not in self._people:
            return None
        if int(claim.get('v') or 0) != int((self._data['profiles'].get(name) or {}).get('pin_version') or 0):
            return None
        return name

    # ------------------------------------------------------------------
    # Preferences that follow a person from one device to the next
    # ------------------------------------------------------------------
    def prefs(self, name: str) -> Dict:
        profile = self._data['profiles'].get(name) or {}
        return {'prefs': profile.get('prefs') or {}, 'prefs_at': profile.get('prefs_at') or 0}

    def set_prefs(self, name: str, prefs: Dict) -> float:
        clean = {str(k): str(v) for k, v in prefs.items() if isinstance(k, str) and k.startswith('retromanager.') and isinstance(v, str)}
        if len(json.dumps(clean)) > MAX_PREFS_BYTES:
            raise ValueError("Too many preferences")
        with self._lock:
            profile = self._profile(name)
            profile['prefs'], profile['prefs_at'] = clean, time.time()
            self._save()
            return profile['prefs_at']
