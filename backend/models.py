"""
Data models for RetroManager
Represents EmulationStation systems, games, and media
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict
from pathlib import Path
import re


@dataclass
class MediaAsset:
    """Represents a single media asset"""
    type: str  # image, video, marquee, screenshot, etc.
    path: Optional[str] = None
    exists: bool = False
    
    def to_dict(self):
        return {
            'type': self.type,
            'path': self.path,
            'exists': self.exists
        }


@dataclass
class Game:
    """Represents a game entry in EmulationStation"""
    path: str  # Relative path to ROM file
    name: str
    desc: Optional[str] = None
    image: Optional[str] = None
    video: Optional[str] = None
    marquee: Optional[str] = None
    thumbnail: Optional[str] = None
    screenshot: Optional[str] = None
    screenshottitle: Optional[str] = None
    wheel: Optional[str] = None
    manuals: Optional[str] = None
    videos: Optional[str] = None
    mix: Optional[str] = None
    box2d: Optional[str] = None
    box3d: Optional[str] = None
    fanart: Optional[str] = None
    images: Optional[str] = None
    posters: Optional[str] = None
    boxside: Optional[str] = None
    rating: Optional[float] = None
    releasedate: Optional[str] = None
    developer: Optional[str] = None
    publisher: Optional[str] = None
    genre: Optional[str] = None
    players: Optional[str] = None
    favorite: bool = False
    playcount: int = 0
    lastplayed: Optional[str] = None
    
    # Metadata status
    has_metadata: bool = True
    rom_exists: bool = True
    media_assets: List[MediaAsset] = field(default_factory=list)
    
    @staticmethod
    def from_filename(rom_path: str) -> 'Game':
        """Create a game with minimal metadata from filename"""
        filename = Path(rom_path).stem
        
        # Clean up filename: remove region codes, version info, etc.
        name = re.sub(r'\[.*?\]', '', filename)
        name = re.sub(r'\(.*?\)', '', name)
        name = re.sub(r'_+', ' ', name)
        name = re.sub(r'\s+', ' ', name).strip(' -')
        
        return Game(
            path=f'./{rom_path}',
            name=name or filename,
            has_metadata=False,
            rom_exists=True
        )
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
        return {
            'path': self.path,
            'name': self.name,
            'desc': self.desc,
            'image': self.image,
            'video': self.video,
            'marquee': self.marquee,
            'thumbnail': self.thumbnail,
            'screenshot': self.screenshot,
            'screenshottitle': self.screenshottitle,
            'wheel': self.wheel,
            'manuals': self.manuals,
            'videos': self.videos,
            'mix': self.mix,
            'box2d': self.box2d,
            'box3d': self.box3d,
            'fanart': self.fanart,
            'images': self.images,
            'posters': self.posters,
            'boxside': self.boxside,
            'rating': self.rating,
            'releasedate': self.releasedate,
            'developer': self.developer,
            'publisher': self.publisher,
            'genre': self.genre,
            'players': self.players,
            'favorite': self.favorite,
            'playcount': self.playcount,
            'lastplayed': self.lastplayed,
            'has_metadata': self.has_metadata,
            'rom_exists': self.rom_exists,
            'media_assets': [m.to_dict() for m in self.media_assets]
        }
    
    @staticmethod
    def from_dict(data: Dict) -> 'Game':
        """Create Game from dictionary"""
        return Game(
            path=data['path'],
            name=data['name'],
            desc=data.get('desc'),
            image=data.get('image'),
            video=data.get('video'),
            marquee=data.get('marquee'),
            thumbnail=data.get('thumbnail'),
            screenshot=data.get('screenshot'),
            screenshottitle=data.get('screenshottitle'),
            wheel=data.get('wheel'),
            manuals=data.get('manuals'),
            videos=data.get('videos'),
            mix=data.get('mix'),
            box2d=data.get('box2d'),
            box3d=data.get('box3d'),
            fanart=data.get('fanart'),
            images=data.get('images'),
            posters=data.get('posters'),
            boxside=data.get('boxside'),
            rating=data.get('rating'),
            releasedate=data.get('releasedate'),
            developer=data.get('developer'),
            publisher=data.get('publisher'),
            genre=data.get('genre'),
            players=data.get('players'),
            favorite=data.get('favorite', False),
            playcount=data.get('playcount', 0),
            lastplayed=data.get('lastplayed'),
            has_metadata=data.get('has_metadata', True),
            rom_exists=data.get('rom_exists', True)
        )


@dataclass
class System:
    """Represents an EmulationStation system"""
    name: str
    path: str
    rom_count: int = 0
    game_count: int = 0
    missing_metadata_count: int = 0
    has_gamelist: bool = False
    
    # Static mapping of system short names to full display names (with manufacturer)
    SYSTEM_FULL_NAMES = {
        '3ds': 'Nintendo 3DS',
        'dos': 'Microsoft DOS',
        'coleco': 'ColecoVision',
        'snes': 'Nintendo SNES',
        'nds': 'Nintendo DS',
        'nsw': 'Nintendo Switch',
        'pokemini': 'Nintendo PokéMini',
        'gc': 'Nintendo GameCube',
        'wii': 'Nintendo Wii',
        'channelf': 'Fairchild Channel F',
        'fba': 'Final Burn Alpha Arcade',
        'steam': 'PC Steam',
        'nvb': 'Nintendo Virtual Boy',
        'nes': 'Nintendo Entertainment System',
        'n64': 'Nintendo 64',
        'gba': 'Nintendo Game Boy Advance',
        'gb': 'Nintendo Game Boy',
        'gbc': 'Nintendo Game Boy Color',
        'gamegear': 'Sega Game Gear',
        'genesis': 'Sega Genesis',
        'megadrive': 'Sega Mega Drive',
        'mastersystem': 'Sega Master System',
        'dreamcast': 'Sega Dreamcast',
        'saturn': 'Sega Saturn',
        'psx': 'Sony PlayStation',
        'ps2': 'Sony PlayStation 2',
        'psp': 'Sony PlayStation Portable',
        'atari2600': 'Atari 2600',
        'atari5200': 'Atari 5200',
        'atari7800': 'Atari 7800',
        'atari800': 'Atari 800',
        'atarilynx': 'Atari Lynx',
        'atarijaguar': 'Atari Jaguar',
        'atarijaguarcd': 'Atari Jaguar CD',
        'colecovision': 'Coleco ColecoVision',
        'intellivision': 'Mattel Intellivision',
        'vectrex': 'GCE Vectrex',
        'c64': 'Commodore 64',
        'amiga': 'Commodore Amiga',
        'amstradcpc': 'Amstrad CPC',
        'apple2': 'Apple II',
        'msx': 'MSX',
        'pcengine': 'NEC PC Engine',
        'pcfx': 'NEC PC-FX',
        'tg16': 'NEC TurboGrafx-16',
        'tg-cd': 'NEC TurboGrafx-CD',
        'x68000': 'Sharp X68000',
        'zxspectrum': 'Sinclair ZX Spectrum',
        'fds': 'Nintendo Famicom Disk System',
        'famicom': 'Nintendo Famicom',
        'ngp': 'SNK Neo Geo Pocket',
        'ngpc': 'SNK Neo Geo Pocket Color',
        'neogeo': 'SNK Neo Geo',
        'neogeocd': 'SNK Neo Geo CD',
        'daphne': 'Daphne Laserdisc',
        'scummvm': 'ScummVM',
        'residualvm': 'ResidualVM',
        'mame': 'MAME Arcade',
        'mame-libretro': 'MAME (Libretro)',
        'arcade': 'Arcade',
        'wonderswan': 'Bandai WonderSwan',
        'wonderswancolor': 'Bandai WonderSwan Color',
        'virtualboy': 'Nintendo Virtual Boy',
        'odyssey2': 'Magnavox Odyssey 2',
        'ody2': 'Magnavox Odyssey 2',
        'sg-1000': 'Sega SG-1000',
        'sega32x': 'Sega 32X',
        'segacd': 'Sega CD',
        'box3d': '3D Box',
        'box2d': '2D Box',
        # Add more as needed
    }

    def get_full_name(self):
        return self.SYSTEM_FULL_NAMES.get(self.name.lower(), self.name)

    def to_dict(self) -> Dict:
        return {
            'name': self.name,
            'full_name': self.get_full_name(),
            'path': self.path,
            'rom_count': self.rom_count,
            'game_count': self.game_count,
            'missing_metadata_count': self.missing_metadata_count,
            'has_gamelist': self.has_gamelist
        }


@dataclass
class ScanResult:
    """Results of a system scan operation"""
    system: str
    new_roms: List[str] = field(default_factory=list)
    removed_roms: List[str] = field(default_factory=list)
    orphaned_metadata: List[str] = field(default_factory=list)
    orphaned_media: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        return {
            'system': self.system,
            'new_roms': self.new_roms,
            'removed_roms': self.removed_roms,
            'orphaned_metadata': self.orphaned_metadata,
            'orphaned_media': self.orphaned_media
        }
