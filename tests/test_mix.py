"""Generating Mix pictures: the layout arithmetic, the drawing, and the routes
(inventory, previews, commit) against a system of its own in the throwaway library."""

import copy
import json
import os
import tarfile
import time
from pathlib import Path

import pytest
from PIL import Image, ImageChops, ImageDraw, ImageStat

from backend import mix_generator as mg

GOLDEN = Path(__file__).parent / "golden"
CLASSIC = mg.load_templates()["classic"]
W, H = CLASSIC["canvas"]["width"], CLASSIC["canvas"]["height"]
# Screenshot shapes a Mix has to cope with
SCREENSHOTS = {
    "4x3": (320, 240), "10x9": (160, 144), "3x2": (240, 160), "vertical": (224, 320),
    "ds": (256, 384), "16x9": (1920, 1080), "ultrawide": (2560, 1080),
}
BOX, MEDIA, WHEEL = (300, 420), (400, 380), (800, 300)


# --- Fixture pictures, drawn here so no artwork is kept in the repository ---

def screenshot(size, path=None):
    image = Image.new("RGB", size, (30, 60, 140))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, size[1] * 2 // 3, size[0], size[1]), fill=(40, 150, 60))
    draw.rectangle((size[0] // 4, size[1] // 3, size[0] // 2, size[1] * 2 // 3), fill=(220, 60, 50))
    return _saved(image, path)


def art(size, colour, padding=0, path=None):
    """A box, cartridge or logo: a solid shape, with a see-through border when padded."""
    image = Image.new("RGBA", (size[0] + padding * 2, size[1] + padding * 2), (0, 0, 0, 0))
    ImageDraw.Draw(image).rectangle((padding, padding, padding + size[0] - 1, padding + size[1] - 1), fill=colour + (255,))
    return _saved(image, path)


def _saved(image, path):
    if path:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        image.save(path)
    return image


def sources(tmp_path, shot=(320, 240), box=True, media=True, wheel=True):
    files = {"screenshot": [("screenshot", tmp_path / "shot.png")]}
    screenshot(shot, tmp_path / "shot.png")
    if box:
        art(BOX, (200, 40, 40), 0, tmp_path / "box.png")
        files["box"] = [("box3d", tmp_path / "box.png")]
    if media:
        art(MEDIA, (120, 120, 130), 0, tmp_path / "cart.png")
        files["media"] = [("support", tmp_path / "cart.png")]
    if wheel:
        art(WHEEL, (240, 200, 40), 60, tmp_path / "wheel.png")
        files["wheel"] = [("wheel", tmp_path / "wheel.png")]
    return files


def layout(roles, shot=(320, 240), template=CLASSIC, canvas=None):
    sizes = {"screenshot": shot, "box": BOX, "media": MEDIA, "wheel": WHEEL}
    return mg.compute_layout(template, {r: sizes[r] for r in roles}, canvas)


def inside(rect, outer, slack=0):
    return (rect[0] >= outer[0] - slack and rect[1] >= outer[1] - slack
            and rect[0] + rect[2] <= outer[0] + outer[2] + slack and rect[1] + rect[3] <= outer[1] + outer[3] + slack)


# --- Layout arithmetic ---

@pytest.mark.parametrize("shape", SCREENSHOTS)
def test_screenshot_fits_its_panel_whatever_its_shape(shape):
    size = SCREENSHOTS[shape]
    placed = layout(["screenshot"], size)["screenshot"]
    x, y, w, h = placed["rect"]
    panel = placed["panel"]
    assert placed["clip"] is None and inside(placed["rect"], panel)
    # Same shape as the screenshot, touching the panel on one axis, centred on the other
    assert abs(w / h - size[0] / size[1]) < 0.01
    assert w == panel[2] or h == panel[3]
    assert abs((x - panel[0]) - (panel[0] + panel[2] - x - w)) <= 1
    assert abs((y - panel[1]) - (panel[1] + panel[3] - y - h)) <= 1


@pytest.mark.parametrize("shape", SCREENSHOTS)
def test_screenshot_can_cover_its_panel_instead(shape):
    template = {**CLASSIC, "screenshot_fit": "cover"}
    placed = layout(["screenshot"], SCREENSHOTS[shape], template)["screenshot"]
    assert placed["clip"] == placed["panel"] and inside(placed["panel"], placed["rect"])


def test_the_classic_layout_with_everything():
    placed = layout(["screenshot", "box", "media", "wheel"])
    panel = placed["screenshot"]["panel"]
    assert panel == (round(0.04 * W), round(0.04 * H), round(0.92 * W), round(0.67 * H))
    bx, by, bw, bh = placed["box"]["rect"]
    assert (bx, by + bh) == (round(0.02 * W), round(0.975 * H)) and bh == round(0.55 * H)
    mx, my, mw, mh = placed["media"]["rect"]
    # The cartridge stands at the bottom, in front of the box
    assert (mx, my + mh) == (round(0.26 * W), round(0.99 * H)) and mx < bx + bw
    assert mw <= round(0.26 * W) and mh <= round(0.19 * H)
    wx, wy, ww, wh = placed["wheel"]["rect"]
    # The logo sits low on the right, across the bottom of the screen
    assert wx + ww == round(0.975 * W) and abs(wy + wh / 2 - 0.795 * H) <= 1
    assert ww <= round(0.56 * W) and wh <= round(0.2 * H) and wy < panel[1] + panel[3] < wy + wh
    # The box overlaps the screen
    assert bx + bw > panel[0] and by < panel[1] + panel[3]
    assert CLASSIC["layers"].index("box") < CLASSIC["layers"].index("wheel") < CLASSIC["layers"].index("media")


def test_missing_elements_leave_the_others_where_they_were():
    full = layout(["screenshot", "box", "media", "wheel"])
    no_media = layout(["screenshot", "box", "wheel"])
    assert "media" not in no_media and no_media["box"] == full["box"]
    no_wheel = layout(["screenshot", "box", "media"])
    assert "wheel" not in no_wheel and no_wheel["screenshot"] == full["screenshot"] and no_wheel["media"] == full["media"]
    assert layout(["screenshot", "wheel"])["screenshot"] == full["screenshot"]


def test_media_takes_the_boxs_place_when_there_is_no_box():
    placed = layout(["screenshot", "media", "wheel"])
    x, y, w, h = placed["media"]["rect"]
    assert (x, y + h) == (round(0.02 * W), round(0.975 * H))
    assert w <= round(0.26 * W) and h <= round(0.19 * H) and (w == round(0.26 * W) or h == round(0.19 * H))


def test_the_layout_is_the_templates_to_change():
    template = copy.deepcopy(CLASSIC)
    template["elements"]["wheel"] = {"anchor": "top-center", "margin": [0.01, 0.01], "max": [0.55, 0.22]}
    x, y, w, h = layout(["screenshot", "wheel"], template=template)["wheel"]["rect"]
    assert abs(x + w / 2 - W / 2) <= 1 and y == round(0.01 * H)
    template["elements"]["box"] = {"anchor": "bottom-right", "margin": [0.01, 0.01], "max": [0.2, 0.2]}
    x, y, w, h = layout(["screenshot", "box"], template=template)["box"]["rect"]
    assert (x + w, y + h) == (round(0.99 * W), round(0.99 * H)) and h <= round(0.2 * H)
    # A media element can stand against the box's right edge instead
    template["elements"]["box"] = dict(CLASSIC["elements"]["box"])
    template["elements"]["media"]["attach"] = {"to": "box", "overlap": 0.03}
    placed = layout(["screenshot", "box", "media"], template=template)
    assert placed["media"]["rect"][0] == placed["box"]["rect"][0] + placed["box"]["rect"][2] - round(0.03 * W)


def test_the_layout_scales_with_the_canvas():
    small = layout(["screenshot", "box", "media", "wheel"])
    large = layout(["screenshot", "box", "media", "wheel"], canvas=(W * 3 // 2, H * 3 // 2))
    for role in small:
        assert all(abs(b - a * 1.5) <= 2 for a, b in zip(small[role]["rect"], large[role]["rect"]))


def test_tiers_and_which_media_is_used():
    assert mg.classify(["screenshot", "box", "media", "wheel"]) == ("full", None)
    assert mg.classify(["screenshot", "wheel"]) == ("partial", None)
    assert mg.classify(["box", "wheel"]) == ("ineligible", "no_screenshot")
    assert mg.classify(["screenshot"]) == ("ineligible", "screenshot_only")
    assert mg.classify(["screenshot", "media"]) == ("ineligible", "no_box_or_wheel")
    have = {"screenshot": "s", "screenshottitle": "t", "box2d": "b2", "box3d": "b3", "wheel": "w"}
    first = lambda options=None: {role: paths[0][0] for role, paths in mg.candidates(CLASSIC, have, options).items()}
    assert first() == {"screenshot": "screenshot", "box": "box3d", "wheel": "wheel"}
    assert first({"box_type": "2d", "screenshot": "title", "wheel": False}) == {"screenshot": "screenshottitle", "box": "box2d"}
    assert mg.candidates(CLASSIC, {"screenshottitle": "t", "box2d": "b"})["screenshot"] == [("screenshottitle", "t")]


# --- Drawing ---

def test_sharp_scaling_keeps_pixels_square():
    tiny = Image.new("RGBA", (2, 2), (0, 0, 0, 255))
    tiny.putpixel((0, 0), (255, 255, 255, 255))
    tiny.putpixel((1, 1), (255, 255, 255, 255))
    sharp = mg.scale_image(tiny, (8, 8), "sharp")
    assert sharp.size == (8, 8) and {p[:3] for p in sharp.getdata()} == {(0, 0, 0), (255, 255, 255)}
    assert len({p[:3] for p in mg.scale_image(tiny, (8, 8), "smooth").getdata()}) > 2
    # Not a whole number of times: still the size asked for
    assert mg.scale_image(tiny, (7, 7), "sharp").size == (7, 7)


def test_see_through_borders_are_trimmed(tmp_path):
    art(WHEEL, (240, 200, 40), 200, tmp_path / "padded.png")
    assert mg._open(tmp_path / "padded.png", True).size == WHEEL
    assert mg._open(tmp_path / "padded.png", False).size == (WHEEL[0] + 400, WHEEL[1] + 400)
    Image.new("RGBA", (10, 10), (0, 0, 0, 0)).save(tmp_path / "empty.png")
    with pytest.raises(ValueError):
        mg._open(tmp_path / "empty.png", True)


@pytest.mark.parametrize("shape", SCREENSHOTS)
def test_a_mix_is_drawn_for_every_screenshot_shape(tmp_path, shape):
    picture, used, warnings = mg.render_mix(CLASSIC, sources(tmp_path, SCREENSHOTS[shape]))
    assert picture.size == (W, H) and picture.mode == "RGBA" and not warnings
    assert used == {"screenshot": "screenshot", "box": "box3d", "media": "support", "wheel": "wheel"}
    # Something was drawn, and the canvas is still see-through where nothing is
    panel = mg.compute_layout(CLASSIC, {"screenshot": SCREENSHOTS[shape]})["screenshot"]
    x, y, w, h = panel["rect"]
    assert picture.getpixel((x + w // 2, y + h * 9 // 10))[3] == 255
    assert picture.getpixel((W - 2, H - 2))[3] == 0
    # The screen is framed: its panel is filled, and has a bezel outside it
    px, py = panel["panel"][:2]
    assert picture.getpixel((px + 3, py + 30))[3] == 255 and picture.getpixel((px - 10, py + 30))[:3] == tuple(CLASSIC["elements"]["screenshot"]["frame"]["color"][:3])


def test_an_unreadable_file_is_skipped_or_fails_only_what_needs_it(tmp_path):
    files = sources(tmp_path)
    (tmp_path / "bad.png").write_bytes(b"not a picture")
    # A bad box falls back to the next one, then to none
    files["box"] = [("box3d", tmp_path / "bad.png"), ("box2d", tmp_path / "box.png")]
    _, used, warnings = mg.render_mix(CLASSIC, files)
    assert used["box"] == "box2d" and len(warnings) == 1 and warnings[0].startswith("box3d")
    files["box"] = [("box3d", tmp_path / "bad.png")]
    _, used, _ = mg.render_mix(CLASSIC, files)
    assert "box" not in used
    files["screenshot"] = [("screenshot", tmp_path / "bad.png")]
    with pytest.raises(mg.MixError) as failed:
        mg.render_mix(CLASSIC, files)
    assert failed.value.reason == "asset_unreadable"
    with pytest.raises(mg.MixError) as failed:
        mg.render_mix(CLASSIC, {"screenshot": [("screenshot", tmp_path / "shot.png")]})
    assert failed.value.reason == "screenshot_only"


def test_the_record_is_written_into_the_png(tmp_path):
    picture, used, _ = mg.render_mix(CLASSIC, sources(tmp_path))
    record = mg.provenance(CLASSIC, used, {"screenshot": "nes/screenshot/x.png"})
    mg.save_png(picture, tmp_path / "mix.png", record)
    read = mg.read_provenance(tmp_path / "mix.png")
    assert read["mix_source"] == "generated" and read["template"] == "classic" and read["template_version"] == str(CLASSIC["version"])
    assert read["assets"] == {"screenshot": "nes/screenshot/x.png"} and read["generated_at"] == record["generated_at"]
    assert mg.read_provenance(tmp_path / "shot.png") is None and mg.read_provenance(tmp_path / "nope.png") is None


@pytest.mark.parametrize("name,parts", [
    ("full", dict()), ("no-media", dict(media=False)), ("no-box", dict(box=False)), ("wheel-only", dict(box=False, media=False)),
])
def test_the_classic_template_looks_as_it_did(tmp_path, name, parts):
    """Compared scaled down and with some give, so a different Pillow version's
    rounding doesn't fail it. MIX_UPDATE_GOLDEN=1 saves the pictures anew."""
    picture, _, _ = mg.render_mix(CLASSIC, sources(tmp_path, **parts))
    small = picture.resize((W // 4, H // 4), Image.BOX)
    golden = GOLDEN / f"classic-{name}.png"
    if os.environ.get("MIX_UPDATE_GOLDEN") == "1":
        GOLDEN.mkdir(exist_ok=True)
        small.save(golden)
    with Image.open(golden) as expected:
        difference = ImageChops.difference(small, expected.convert("RGBA"))
    assert max(ImageStat.Stat(difference).mean) < 2.0


# --- The routes ---

SYSTEM = "mixsys"
GAMES = ["Full Game (USA)", "Partial Game", "No Shot", "Shot Only", "Broken Shot", "Has Mix"]


@pytest.fixture(scope="module")
def library(root):
    """A system of its own: games with different sets of media, one of which already has a scraped Mix."""
    roms, media = root / "roms" / SYSTEM, root / "media" / SYSTEM
    roms.mkdir(parents=True, exist_ok=True)
    for number, name in enumerate(GAMES):
        (roms / f"{name}.nes").write_bytes(bytes([0x40 + number]) * 4096)
    for name in ("Full Game (USA)", "Partial Game", "Shot Only", "Has Mix"):
        screenshot((256, 240), media / "screenshot" / f"{name}.png")
    for name in ("Full Game (USA)", "Partial Game", "No Shot", "Broken Shot", "Has Mix"):
        art(BOX, (200, 40, 40), 20, media / "box2d" / f"{name}.png")
    art(MEDIA, (120, 120, 130), 0, media / "support" / "Full Game (USA).png")
    art(WHEEL, (240, 200, 40), 40, media / "wheel" / "Full Game (USA).png")
    (media / "screenshot" / "Broken Shot.png").write_bytes(b"\x89PNG but not really")
    screenshot((640, 480), media / "mix" / "Has Mix.jpg")
    (roms / "gamelist.xml").write_text(
        "<gameList><game><path>./Full Game (USA).nes</path><name>Full Game</name></game></gameList>")
    return root


def tree(folder):
    return sorted((str(p.relative_to(folder)), p.stat().st_size) for p in Path(folder).rglob("*") if p.is_file())


def finished(client, job):
    for _ in range(200):
        job = client.get(f"/api/mix/jobs/{job['id']}").get_json()["job"]
        if not job["running"]:
            return job
        time.sleep(0.05)
    raise AssertionError("the previews never finished")


def by_name(job):
    return {item["name"] if item["name"] != "Full Game" else "Full Game (USA)": item for item in job["items"]}


def test_templates_are_listed(client):
    listed = client.get("/api/mix/templates").get_json()
    assert listed["default"] == "classic" and [t["name"] for t in listed["templates"]] == ["classic"]


def test_inventory_counts_tiers_and_writes_nothing(client, library):
    before = tree(library)
    report = client.post("/api/mix/inventory", json={"system": SYSTEM}).get_json()
    assert report["success"] and tree(library) == before
    assert report["systems"] == [{"system": SYSTEM, "full_name": report["systems"][0]["full_name"],
                                  "total": 5, "full": 1, "partial": 2, "ineligible": 2}]
    games = {g["rom_path"]: g for g in report["games"]}
    assert "Has Mix.nes" not in games  # it has one already
    assert games["Full Game (USA).nes"]["tier"] == "full"
    assert games["Full Game (USA).nes"]["roles"] == {"screenshot": "screenshot", "box": "box2d", "media": "support", "wheel": "wheel"}
    assert (games["No Shot.nes"]["tier"], games["No Shot.nes"]["reason"]) == ("ineligible", "no_screenshot")
    assert games["Shot Only.nes"]["reason"] == "screenshot_only"
    # Asked for by name, a game with a Mix is described too
    named = client.post("/api/mix/inventory", json={"games": [
        {"system": SYSTEM, "rom_path": "./Has Mix.nes"}, {"system": SYSTEM, "rom_path": "Nope.nes"}]}).get_json()
    assert [(g["rom_path"], g["has_mix"], g["mix_generated"]) for g in named["games"]] == [("Has Mix.nes", True, False)]
    assert named["unknown"] == [{"system": SYSTEM, "rom_path": "Nope.nes"}]
    assert not client.post("/api/mix/inventory", json={"system": SYSTEM, "template": "nope"}).get_json()["success"]


def test_previews_go_to_staging_and_commit_puts_them_in_the_library(client, library):
    media_before = tree(library / "media")
    job = finished(client, client.post("/api/mix/jobs", json={"system": SYSTEM}).get_json()["job"])
    items = by_name(job)
    assert tree(library / "media") == media_before  # nothing in the library yet
    assert (job["ready"], job["failed"], job["ineligible"], job["total"]) == (2, 1, 2, 3)
    # One bad file fails its own game and no other
    assert (items["Broken Shot"]["status"], items["Broken Shot"]["reason"]) == ("failed", "asset_unreadable")
    assert items["Full Game (USA)"]["used"] == {"screenshot": "screenshot", "box": "box2d", "media": "support", "wheel": "wheel"}
    full, partial = items["Full Game (USA)"]["index"], items["Partial Game"]["index"]
    staged = library / "data" / "mix-staging" / job["id"]
    assert (staged / f"{full}.png").is_file()
    preview = client.get(f"/api/mix/preview/{job['id']}/{full}")
    assert preview.status_code == 200 and preview.data[:4] == b"\x89PNG"
    assert client.get(f"/api/mix/preview/{job['id']}/{items['Broken Shot']['index']}").status_code == 404

    # Made again without the box
    again = finished(client, client.post(f"/api/mix/jobs/{job['id']}/regenerate",
                                         json={"items": [{"index": full, "options": {"box": False}}]}).get_json()["job"])
    assert "box" not in again["items"][full]["used"] and again["items"][full]["rev"] == 2
    again = finished(client, client.post(f"/api/mix/jobs/{job['id']}/regenerate",
                                         json={"items": [{"index": full, "options": {}}]}).get_json()["job"])
    assert again["items"][full]["used"]["box"] == "box2d"

    done = client.post(f"/api/mix/jobs/{job['id']}/commit", json={"approve": [full, items["Broken Shot"]["index"]], "reject": [partial]}).get_json()
    assert {r["index"]: r["status"] for r in done["results"]} == {full: "committed", items["Broken Shot"]["index"]: "not_ready"}
    assert done["backup"] is None and done["linked"] == 1
    mix = library / "media" / SYSTEM / "mix" / "Full Game (USA).png"
    assert mix.is_file() and not (staged / f"{full}.png").exists() and not (staged / f"{partial}.png").exists()
    assert not (library / "media" / SYSTEM / "mix" / "Partial Game.png").exists()
    with Image.open(mix) as picture:
        assert picture.size == (W, H) and picture.text["mix_source"] == "generated" and picture.text["mix_template"] == "classic"
        assert json.loads(picture.text["mix_assets"])["wheel"] == f"{SYSTEM}/wheel/Full Game (USA).png"
    assert [i["status"] for i in done["job"]["items"] if i["index"] in (full, partial)] == ["committed", "rejected"]

    # The library sees it: no longer missing, marked as generated, linked in the gamelist
    report = client.get(f"/api/missing-media?system={SYSTEM}").get_json()["systems"][0]
    assert {g["name"]: bool(g["media"]["mix"]) for g in report["games"]}["Full Game"]
    listed = {g["path"]: g for g in client.get(f"/api/systems/{SYSTEM}/games").get_json()["games"]}
    assert listed["./Full Game (USA).nes"]["mix_generated"] and not listed["./Has Mix.nes"]["mix_generated"]
    assert listed["./Full Game (USA).nes"]["image"] == f"{SYSTEM}/mix/Full Game (USA).png"
    assert "Full Game (USA).nes" not in {g["rom_path"] for g in client.post("/api/mix/inventory", json={"system": SYSTEM}).get_json()["games"]}

    assert client.delete(f"/api/mix/jobs/{job['id']}").get_json()["success"] and not staged.exists()
    assert client.get(f"/api/mix/jobs/{job['id']}").status_code == 404


def test_a_scraped_mix_is_only_replaced_when_told_to(client, library):
    scraped = library / "media" / SYSTEM / "mix" / "Has Mix.jpg"
    original = scraped.read_bytes()
    backups = library / "data" / "mix-backups"
    had = set(backups.glob("*.tar.gz")) if backups.is_dir() else set()
    job = finished(client, client.post("/api/mix/jobs", json={"games": [{"system": SYSTEM, "rom_path": "Has Mix.nes"}]}).get_json()["job"])
    assert (job["items"][0]["status"], job["items"][0]["has_mix"]) == ("ready", True)

    refused = client.post(f"/api/mix/jobs/{job['id']}/commit", json={"approve": [0]}).get_json()
    assert refused["results"] == [{"index": 0, "status": "needs_overwrite", "existing": f"{SYSTEM}/mix/Has Mix.jpg"}]
    assert scraped.read_bytes() == original and not (scraped.parent / "Has Mix.png").exists()
    assert (set(backups.glob("*.tar.gz")) if backups.is_dir() else set()) == had

    done = client.post(f"/api/mix/jobs/{job['id']}/commit", json={"approve": [0], "overwrite": True}).get_json()
    assert done["results"][0]["status"] == "committed" and done["results"][0]["replaced"]
    assert not scraped.exists() and (scraped.parent / "Has Mix.png").is_file()
    with tarfile.open(backups / done["backup"]) as archive:
        assert archive.getnames() == [f"{SYSTEM}/mix/Has Mix.jpg"]
        assert archive.extractfile(f"{SYSTEM}/mix/Has Mix.jpg").read() == original


def test_a_generated_mix_can_be_made_again_without_being_told(client, library):
    target = library / "media" / SYSTEM / "mix" / "Full Game (USA).png"
    job = finished(client, client.post("/api/mix/jobs", json={
        "games": [{"system": SYSTEM, "rom_path": "Full Game (USA).nes", "options": {"wheel": False}}]}).get_json()["job"])
    assert job["items"][0]["mix_generated"] and "wheel" not in job["items"][0]["used"]
    done = client.post(f"/api/mix/jobs/{job['id']}/commit", json={"approve": [0]}).get_json()
    assert done["results"][0]["status"] == "committed" and done["backup"]
    with Image.open(target) as picture:
        assert "wheel" not in json.loads(picture.text["mix_assets"])


def test_generated_mixes_can_be_found_and_made_again(client, library):
    report = client.get(f"/api/missing-media?system={SYSTEM}").get_json()["systems"][0]
    assert report["mix_generated"] == 2  # Full Game and, since it was replaced, Has Mix
    again = client.post("/api/mix/inventory", json={"system": SYSTEM, "generated": True}).get_json()
    assert sorted(g["rom_path"] for g in again["games"]) == ["Full Game (USA).nes", "Has Mix.nes"]
    assert all(g["has_mix"] and g["mix_generated"] for g in again["games"])
    job = finished(client, client.post("/api/mix/jobs", json={"system": SYSTEM, "generated": True}).get_json()["job"])
    assert job["ready"] == 2
    done = client.post(f"/api/mix/jobs/{job['id']}/commit", json={"approve": [0, 1]}).get_json()
    # Replaced without being told to, since RetroManager made them; the old ones are backed up
    assert [r["status"] for r in done["results"]] == ["committed", "committed"] and done["backup"]
    client.delete(f"/api/mix/jobs/{job['id']}")


def test_uploading_a_mix_over_a_generated_one_drops_the_mark(client, library):
    import io
    picture = io.BytesIO()
    screenshot((64, 48)).save(picture, "PNG")
    picture.seek(0)
    sent = client.post(f"/api/systems/{SYSTEM}/media/upload", data={
        "rom_path": "Full Game (USA).nes", "folder": "mix", "file": (picture, "mine.png")}, content_type="multipart/form-data")
    assert sent.get_json()["success"]
    listed = {g["path"]: g for g in client.get(f"/api/systems/{SYSTEM}/games").get_json()["games"]}
    assert listed["./Full Game (USA).nes"]["mix"] and not listed["./Full Game (USA).nes"]["mix_generated"]
