import pytest

flask = pytest.importorskip("flask")

from spirit_island.app import create_app  # noqa: E402


@pytest.fixture
def client(tmp_path):
    app = create_app(str(tmp_path))
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


def test_terrain_tags_carry_into_next_game(client):
    client.post("/api/action", json={"type": "configure", "players": [{}]})
    client.post("/api/action", json={"type": "land_info", "land": "A7", "terrain": "W"})
    client.post("/api/action", json={"type": "new_game"})
    r = client.post("/api/action", json={"type": "configure", "players": [{}]})
    assert r.json["state"]["lands"]["A7"]["terrain"] == "W"


def test_errors_are_400(client):
    r = client.post("/api/action", json={"type": "nope"})
    assert r.status_code == 400 and "unknown action" in r.json["error"]


def test_index_and_health(client):
    assert b"Spirit Island" in client.get("/").data
    assert client.get("/health").json["ok"] is True
