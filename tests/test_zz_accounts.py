"""Profiles and login: who may do what once it's switched on. Run last (the
file is named to sort after the others), and login is switched off again at the
end, as the other tests expect it."""

import io


def test_login_off_everyone_is_an_admin(client):
    me = client.get("/api/accounts/me").get_json()
    assert me["enabled"] is False and me["admin"] is True and me["profile"] is None
    assert {p["name"] for p in me["profiles"]} >= {"family", "guest"}


def test_switching_login_on_needs_an_admin_with_a_pin(client):
    assert client.put("/api/accounts/enabled", json={"enabled": True, "profile": "family", "pin": "1234"}).status_code == 400
    assert client.put("/api/accounts/profile", json={"name": "family", "role": "admin", "pin": "12"}).status_code == 400   # too short
    assert client.put("/api/accounts/profile", json={"name": "family", "role": "admin", "pin": "1234"}).get_json()["success"]
    assert client.put("/api/accounts/enabled", json={"enabled": True, "profile": "family", "pin": "9999"}).status_code == 403


def test_login_on(client, root):
    # A status kept while login is off becomes the first admin's
    client.put("/api/play-status", json={"system": "gba", "rom_path": "Pocket Game.gba", "status": "backlog"})
    on = client.put("/api/accounts/enabled", json={"enabled": True, "profile": "family", "pin": "1234"}).get_json()
    assert on["enabled"] and on["profile"] == "family" and on["admin"]
    games = {g["path"]: g for g in client.get("/api/systems/gba/games").get_json()["games"]}
    assert games["./Pocket Game.gba"]["play_status"] == "backlog"

    try:
        # Signed out: the pages still load (they send you to sign in), the API doesn't answer
        client.post("/api/accounts/logout")
        assert client.get("/").status_code == 200 and client.get("/login").status_code == 200
        refused = client.get("/api/systems")
        assert refused.status_code == 401 and refused.get_json()["sign_in"]
        assert client.get("/api/accounts/me").get_json()["profile"] is None

        # A player signs in with a tap; an admin needs the PIN
        assert client.post("/api/accounts/login", json={"profile": "family"}).status_code == 403
        assert client.post("/api/accounts/login", json={"profile": "nobody"}).status_code == 404
        me = client.post("/api/accounts/login", json={"profile": "guest"}).get_json()
        assert me["profile"] == "guest" and me["role"] == "player" and me["admin"] is False

        # A player reads, and changes only what's theirs
        assert client.get("/api/systems").status_code == 200
        games = {g["path"]: g for g in client.get("/api/systems/gba/games").get_json()["games"]}
        assert games["./Pocket Game.gba"]["play_status"] is None                      # family's backlog isn't guest's
        assert client.put("/api/play-status", json={"system": "gba", "rom_path": "Pocket Game.gba", "status": "playing"}).get_json()["play_status"] == "playing"
        assert client.put("/api/favorite", json={"system": "gba", "rom_path": "Pocket Game.gba", "favorite": True}).status_code == 200
        for method, url, body in (("put", "/api/systems/gba/games/Pocket%20Game.gba", {"name": "Hacked"}), ("delete", "/api/systems/gba/games/Pocket%20Game.gba", None),
                                  ("post", "/api/systems/gba/scan", None), ("post", "/api/collections", {"name": "Mine"}), ("put", "/api/settings", {"values": {}}),
                                  ("put", "/api/accounts/profile", {"name": "guest", "role": "admin"}), ("put", "/api/accounts/enabled", {"enabled": False}),
                                  ("post", "/api/accounts/people", {"name": "sneaky"})):
            assert getattr(client, method)(url, json=body).status_code == 403, url
        assert client.get("/api/settings").status_code == 403
        # ...including saves: their own, not someone else's
        assert client.put("/api/play/save?system=gba&rom=Pocket%20Game.gba&profile=family", data=b"\x05" * 64).status_code == 403
        assert client.put("/api/play/save?system=gba&rom=Pocket%20Game.gba&profile=guest", data=b"\x05" * 64).get_json()["success"]
        assert (root / "saves/guest/gba/Pocket Game.srm").read_bytes() == b"\x05" * 64

        # Preferences follow the person
        assert client.put("/api/accounts/prefs", json={"prefs": {"retromanager.theme": "sepia", "other.key": "x"}}).get_json()["success"]
        assert client.get("/api/accounts/me").get_json()["prefs"] == {"retromanager.theme": "sepia"}

        # Switching back to the admin asks for the PIN again; five wrong ones mean a wait
        assert client.post("/api/accounts/login", json={"profile": "family", "pin": "0000"}).status_code == 403
        back = client.post("/api/accounts/login", json={"profile": "family", "pin": "1234"}).get_json()
        assert back["profile"] == "family" and back["admin"]
        games = {g["path"]: g for g in client.get("/api/systems/gba/games").get_json()["games"]}
        assert games["./Pocket Game.gba"]["play_status"] == "backlog"
        assert client.get("/api/settings").status_code == 200

        # A new person gets their folders; a photo is kept small and square
        assert client.post("/api/accounts/people", json={"name": "bad name!"}).status_code == 400
        assert client.post("/api/accounts/people", json={"name": "kim"}).get_json()["success"]
        assert (root / "saves/kim").is_dir() and (root / "savestates/kim").is_dir()
        from PIL import Image
        picture = io.BytesIO()
        Image.new("RGB", (400, 200), "red").save(picture, "PNG")
        picture.seek(0)
        photo = next(p["photo"] for p in client.post("/api/accounts/photo", data={"name": "kim", "file": (picture, "me.png")}).get_json()["profiles"] if p["name"] == "kim")
        assert Image.open(io.BytesIO(client.get(f"/api/accounts/photo/{photo}").data)).size == (256, 256)

        # A changed PIN signs that profile's other devices out; a forged cookie is nobody
        other = client.application.test_client()
        other.post("/api/accounts/login", json={"profile": "family", "pin": "1234"})
        assert client.put("/api/accounts/profile", json={"name": "family", "pin": "4321"}).get_json()["profile"] == "family"
        assert other.get("/api/systems").status_code == 401
        other.set_cookie("rm_profile", "eyJwIjogImZhbWlseSJ9.deadbeef")
        assert other.get("/api/systems").status_code == 401

        # The way back in after a forgotten PIN
        (root / "data/reset-login").write_text("")
        assert client.get("/api/accounts/me").get_json()["enabled"] is False
        assert not (root / "data/reset-login").exists()
    finally:
        (root / "data/reset-login").write_text("")
        client.get("/api/accounts/me")
        client.post("/api/accounts/logout")
    assert client.get("/api/systems").status_code == 200
