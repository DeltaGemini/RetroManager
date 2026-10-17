"""What keeps RetroManager to itself: another site's page can't change it, a path can't reach out of
its folders, and it only downloads from the internet, not from the home network."""

import pytest

from backend.net_guard import NotPublic, check_public


def test_a_change_sent_by_another_sites_page_is_refused(client):
    body = {"system": "snes", "rom_path": "Game One (USA).sfc", "status": "playing"}
    assert client.put("/api/play-status", json=body, headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert client.put("/api/play-status", json=body, headers={"Origin": "http://evil.example"}).status_code == 403
    # Its own pages, and what isn't a browser (the phone app, curl), are let through
    assert client.put("/api/play-status", json=body, headers={"Sec-Fetch-Site": "same-origin"}).get_json()["success"]
    assert client.put("/api/play-status", json=body, headers={"Origin": "http://localhost"}).get_json()["success"]
    assert client.put("/api/play-status", json={**body, "status": None}).get_json()["success"]
    # Reading is still fine (another site's page can't read the answer: no CORS)
    response = client.get("/api/health", headers={"Origin": "http://evil.example"})
    assert response.status_code == 200 and "Access-Control-Allow-Origin" not in response.headers


def test_a_path_cant_reach_a_folder_beside_the_media_one(client, root):
    beside = root / "media-beside"
    beside.mkdir(exist_ok=True)
    (beside / "secret.png").write_bytes(b"\x89PNG not yours")
    response = client.get("/api/media/snes/box2d/../../../media-beside/secret.png")
    assert response.status_code in (403, 404) and b"not yours" not in response.data


@pytest.mark.parametrize("url", ["http://127.0.0.1/x.png", "http://localhost:8080/x.png", "http://192.168.1.1/admin",
                                 "http://10.0.0.5/x.png", "http://169.254.169.254/latest/meta-data", "http://[::1]/x.png",
                                 "file:///etc/passwd", "ftp://example.com/x.png"])
def test_only_the_internet_is_downloaded_from(url):
    with pytest.raises(NotPublic):
        check_public(url)


def test_a_public_address_is_let_through():
    check_public("https://1.1.1.1/x.png")


def test_fill_the_gaps_wont_fetch_from_the_home_network(client):
    done = client.post("/api/fill/apply", json={"system_name": "snes", "rom_path": "Game One (USA).sfc",
                                                "pictures": {"box2d": "http://192.168.1.1/router.png"}}).get_json()
    assert not done["downloaded"] and any("not the internet" in e for e in done["errors"])
