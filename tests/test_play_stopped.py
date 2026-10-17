"""Playing in the browser: where a person stopped (a save state made as they leave), kept apart from their own."""


def test_where_they_stopped_is_kept_apart_and_offered(client, root):
    who = {"system": "gba", "rom": "Pocket Game.gba", "profile": "guest"}
    assert client.put("/api/play/state", query_string=who, data=b"STATE-SAVED").get_json()["success"]
    assert client.put("/api/play/state", query_string={**who, "auto": "1"}, data=b"STATE-STOPPED").get_json()["success"]
    assert client.get("/api/play/state", query_string=who).data == b"STATE-SAVED"          # their own, untouched
    assert client.get("/api/play/state", query_string={**who, "auto": "1"}).data == b"STATE-STOPPED"
    info = client.get("/api/play/info", query_string={"system": "gba", "rom": "Pocket Game.gba"}).get_json()
    guest = next(p for p in info["profiles"] if p["name"] == "guest")
    assert guest["has_state"] and guest["stopped"]
    # Not one of RetroArch's states, to load as the Pi's
    states = client.get("/api/play/pi-states", query_string={"system": "gba", "rom": "Pocket Game.gba"}).get_json()["states"]
    assert not any("Browser" in s["path"] for s in states)
