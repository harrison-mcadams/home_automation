import pytest

from vision import phone

ADB_OUTPUT = (
    "List of devices attached\n"
    "1A2B3C4D       device usb:1-1 product:oriole model:Pixel_6 device:oriole transport_id:1\n"
)


@pytest.fixture
def fake_adb(monkeypatch):
    calls = []

    def run(args):
        calls.append(args[1:])
        if args[1:3] == ["devices", "-l"]:
            return run.devices
        return ""

    run.devices = ADB_OUTPUT
    monkeypatch.setattr(phone, "_run", run)
    return run, calls


def test_lists_pixel(fake_adb):
    devices = phone.list_devices(adb="adb")
    assert devices == [{"serial": "1A2B3C4D", "state": "device", "model": "Pixel_6"}]


def test_forward_runs_adb_forward(fake_adb):
    _, calls = fake_adb
    base = phone.forward(8080, adb="adb")
    assert base == "http://localhost:8080"
    assert ["-s", "1A2B3C4D", "forward", "tcp:8080", "tcp:8080"] in calls
    assert phone.urls(base)["photo"] == "http://localhost:8080/photo.jpg"


def test_forward_explains_unauthorized_phone(fake_adb):
    run, _ = fake_adb
    run.devices = "List of devices attached\n1A2B3C4D       unauthorized usb:1-1 transport_id:1\n"
    with pytest.raises(phone.PhoneError, match="USB debugging"):
        phone.forward(adb="adb")


def test_find_adb_falls_back_to_sdk_folder(tmp_path, monkeypatch):
    tools = tmp_path / "platform-tools"
    tools.mkdir()
    name = "adb.exe" if phone.os.name == "nt" else "adb"
    (tools / name).write_text("")
    monkeypatch.setattr(phone.shutil, "which", lambda _: None)
    monkeypatch.setenv("ANDROID_HOME", str(tmp_path))
    assert phone.find_adb() == str(tools / name)


def test_urls_take_login_from_env_then_dotenv(monkeypatch, tmp_path):
    for var in ("IPWEBCAM_USER", "IPWEBCAM_PASS"):
        monkeypatch.delenv(var, raising=False)
    env = tmp_path / ".env"
    env.write_text('# camera\nIPWEBCAM_USER=cam\nIPWEBCAM_PASS="s3cret"\nOTHER=1\n')
    monkeypatch.setattr(phone, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(phone.Path, "home", lambda: tmp_path / "nohome")
    assert phone.urls("http://localhost:8080")["video"] == "http://cam:s3cret@localhost:8080/video"
    monkeypatch.setenv("IPWEBCAM_PASS", "fromenv")  # real env var wins over .env
    assert phone.credentials() == ("cam", "fromenv")
    env.unlink()
    monkeypatch.delenv("IPWEBCAM_PASS")
    assert phone.urls("http://localhost:8080")["photo"] == "http://localhost:8080/photo.jpg"


def test_credentials_fall_back_to_home_folder(monkeypatch, tmp_path):
    for var in ("IPWEBCAM_USER", "IPWEBCAM_PASS"):
        monkeypatch.delenv(var, raising=False)
    (tmp_path / ".ipwebcam").mkdir()
    (tmp_path / ".ipwebcam" / "credentials.txt").write_text("IPWEBCAM_USER=pixelcam\nIPWEBCAM_PASS=x\n")
    monkeypatch.setattr(phone, "REPO_ROOT", tmp_path / "repo-without-env")
    monkeypatch.setattr(phone.Path, "home", lambda: tmp_path)
    assert phone.credentials() == ("pixelcam", "x")
