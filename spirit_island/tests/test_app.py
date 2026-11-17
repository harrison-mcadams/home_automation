import pytest

flask = pytest.importorskip("flask")

from spirit_island.app import create_app  # noqa: E402


@pytest.fixture
def client(tmp_path):
    app = create_app(str(tmp_path), vision_url="")
    return app.test_client()


def test_state_and_actions_round_trip(client, tmp_path):
    r = client.get("/api/state")
    assert r.status_code == 200 and r.json["state"]["step"] == "setup.welcome"
    r = client.post("/api/action", json={"type": "configure", "players": [{"name": "H", "spirit": "Thunderspeaker"}]})
    assert r.status_code == 200 and r.json["state"]["boards"] == ["A"]
    r = client.post("/api/action", json={"type": "land_info", "land": "A4", "terrain": "S"})
    assert r.status_code == 200
    assert (tmp_path / "current.json").exists()
    assert '"A4": "S"' in (tmp_path / "board_terrains.json").read_text()


def test_printed_terrains_win_over_old_hand_tags(client):
    client.post("/api/action", json={"type": "configure", "players": [{}]})
    client.post("/api/action", json={"type": "land_info", "land": "A7", "terrain": "W"})
    client.post("/api/action", json={"type": "new_game"})
    r = client.post("/api/action", json={"type": "configure", "players": [{}]})
    assert r.json["state"]["lands"]["A7"]["terrain"] == "S"  # as printed on board A


def test_errors_are_400(client):
    r = client.post("/api/action", json={"type": "nope"})
    assert r.status_code == 400 and "unknown action" in r.json["error"]


def test_index_and_health(client):
    assert b"Spirit Island" in client.get("/").data
    assert client.get("/health").json["ok"] is True


def test_tv_and_phone_pages(client):
    assert b"tv.js" in client.get("/tv").data
    assert b"app.js" in client.get("/phone").data
    links = client.get("/api/links").json
    assert links["tv"][0].endswith("/tv") and links["phone"][0].endswith("/phone")


def test_camera_counts_can_be_copied_in(tmp_path):
    app = create_app(str(tmp_path), vision_url="http://camera.invalid", start_vision=False)
    c = app.test_client()
    v = app.config["STORE"].vision
    c.post("/api/action", json={"type": "configure", "players": [{}], "boards": ["C"]})
    v.raw = {"status": "ok", "settled": "settled", "stamp": "12:00:00", "pieces": [{}, {}],
             "board_state": {"2": {"city": 1, "presence (yellow)": 1}, "ocean": {"explorer": 1}, "7": {"energy": 1}}}
    v.error = None
    snap = c.get("/api/state").json
    assert snap["vision"]["board"] == "C" and snap["vision"]["settled"]
    assert [d["land"] for d in snap["vision"]["diffs"]] == ["C2"]
    r = c.post("/api/vision", json={"accept": "C2"})
    assert r.status_code == 200
    assert r.json["state"]["lands"]["C2"]["cities"] == 1 and r.json["state"]["lands"]["C2"]["presence"] == 1
    assert r.json["vision"]["diffs"] == []
    assert r.json["state"]["log"][-1]["source"] == "camera"
