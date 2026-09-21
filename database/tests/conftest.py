import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


def pytest_configure(config):
    config.addinivalue_line("markers", "integration: needs TEST_POSTGRES_ADMIN_URL (skipped otherwise)")
