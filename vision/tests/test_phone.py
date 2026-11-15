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
