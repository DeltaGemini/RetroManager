"""Spines and 3D boxes made from a game's cover (backend/box_generator.py), and put in by Fill the gaps."""

from pathlib import Path

from PIL import Image

from backend.box_generator import case_for, make_box3d, make_spine


def _cover(size, colour=(240, 200, 20)):
    return Image.new('RGBA', size, colour + (255,))


def test_a_cardboard_spine_takes_the_covers_edge_colour_and_a_case_spine_its_systems():
    cover = _cover((500, 700))
    spine = make_spine(cover, None, 'Plain Game', 'nes')
    assert spine.height == 700 and spine.width < 150                   # standing, for a standing box
    assert spine.convert('RGB').getpixel((spine.width // 2, 690))[:2] == (240, 200)   # yellow, like the cover's edge
    disc = make_spine(cover, None, 'Disc Game', 'ps2')
    assert disc.convert('RGB').getpixel((disc.width // 2, 400))[0] < 40  # a keep case's black


def test_a_landscape_box_lies_down_but_a_jewel_case_stands():
    snes = make_spine(_cover((700, 500)), None, 'Wide Game', 'snes')
    assert snes.width == 700 and snes.height < 150                     # along the bottom
    assert case_for('PlayStation')['case'] == 'jewel'
    psx = make_spine(_cover((790, 680)), None, 'Disc Game', 'psx')
    assert psx.height == 680                                           # a PS1 cover is wider than tall; its case still stands


def test_a_3d_box_is_the_cover_turned_with_its_spine():
    cover = _cover((500, 700))
    box = make_box3d(cover, make_spine(cover, None, 'Game', 'gc'), 'gc', size=300)
    assert max(box.size) <= 300 and box.mode == 'RGBA'
    assert box.getpixel((0, 0))[3] == 0                                # transparent round it


def test_fill_the_gaps_puts_a_made_spine_in(client, root):
    from backend.core import _invalidate_caches, scanner
    (root / "roms" / "snes" / "Boxed Game.sfc").write_bytes(b"\x09" * 4096)
    folder = Path(root / "media") / scanner.media_index("snes").media_system
    (folder / "box2d").mkdir(parents=True, exist_ok=True)
    _cover((700, 500), (30, 90, 200)).save(folder / "box2d" / "Boxed Game.png")
    _invalidate_caches()

    made = client.post("/api/boxes/make", json={"system_name": "snes", "rom_path": "Boxed Game.sfc", "kind": "boxside"}).get_json()
    assert made["success"], made
    assert client.get(made["url"]).status_code == 200
    done = client.post("/api/fill/apply", json={"system_name": "snes", "rom_path": "Boxed Game.sfc", "pictures": {"boxside": f"made:{made['token']}"}}).get_json()
    assert done["success"] and done["downloaded"] == ["boxside"], done
    assert (folder / "boxside" / "Boxed Game.png").is_file()

    (root / "roms" / "snes" / "Coverless Game.sfc").write_bytes(b"\x0a" * 4096)
    _invalidate_caches()
    nothing = client.post("/api/boxes/make", json={"system_name": "snes", "rom_path": "Coverless Game.sfc", "kind": "box3d"}).get_json()
    assert not nothing["success"] and "cover" in nothing["error"]      # no cover to make one from
    bad = client.post("/api/fill/apply", json={"system_name": "snes", "rom_path": "Coverless Game.sfc", "pictures": {"boxside": "made:../../etc"}}).get_json()
    assert bad["errors"] and not bad["downloaded"]


def test_a_picture_pasted_in_is_kept_and_put_in(client, root):
    import io
    from backend.core import _invalidate_caches, scanner
    (root / "roms" / "snes" / "Pasted Game.sfc").write_bytes(b"\x0b" * 4096)
    _invalidate_caches()
    jpeg = io.BytesIO()
    Image.new('RGB', (40, 60), (200, 30, 30)).save(jpeg, 'JPEG')
    kept = client.post("/api/fill/picture", data=jpeg.getvalue(), headers={"Content-Type": "application/octet-stream"}).get_json()
    assert kept["success"] and client.get(kept["url"]).status_code == 200
    done = client.post("/api/fill/apply", json={"system_name": "snes", "rom_path": "Pasted Game.sfc", "pictures": {"box2d": f"made:{kept['token']}"}}).get_json()
    assert done["downloaded"] == ["box2d"]
    folder = Path(root / "media") / scanner.media_index("snes").media_system
    assert (folder / "box2d" / "Pasted Game.jpg").is_file()                  # kept as the JPEG it was
    junk = client.post("/api/fill/picture", data=b"not a picture", headers={"Content-Type": "application/octet-stream"}).get_json()
    assert not junk["success"]
