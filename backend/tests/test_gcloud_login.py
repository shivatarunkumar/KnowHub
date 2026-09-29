import os

import pytest

from app.core import gcp_credentials
from app.services.gcloud_login import URL_RE, from_this_machine


@pytest.fixture
def adc_file(tmp_path, monkeypatch):
    path = tmp_path / "adc.json"
    path.write_text("{}")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(path))
    return path


def test_per_login_builds_again_after_a_new_sign_in(adc_file):
    built = []

    @gcp_credentials.per_login
    def client():
        built.append(1)
        return len(built)

    assert client() == 1
    assert client() == 1  # cached while the credentials file is unchanged

    stat = adc_file.stat()
    os.utime(adc_file, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
    assert client() == 2

    client.cache_clear()
    assert client() == 3


def test_per_login_without_a_credentials_file(tmp_path, monkeypatch):
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(tmp_path / "missing.json"))
    calls = gcp_credentials.per_login(lambda: object())
    assert calls() is calls()


@pytest.mark.parametrize(
    ("client", "forwarded", "expected"),
    [
        ("127.0.0.1", None, True),  # curl / make api on this machine
        ("127.0.0.1", "127.0.0.1", True),  # the web app's proxy, browser on this machine
        ("127.0.0.1", "::1", True),
        ("127.0.0.1", "::ffff:127.0.0.1", True),
        ("127.0.0.1", "192.168.1.20", False),  # a colleague on the network
        ("127.0.0.1", "127.0.0.1, 192.168.1.20", False),
        ("192.168.1.20", None, False),
        (None, None, False),
    ],
)
def test_only_offered_to_a_browser_on_this_machine(client, forwarded, expected):
    assert from_this_machine(client, forwarded) is expected


def test_finds_the_sign_in_url_in_gcloud_output():
    line = "    https://accounts.google.com/o/oauth2/auth?response_type=code&state=abc\n"
    assert URL_RE.search(line).group(0) == line.strip()
