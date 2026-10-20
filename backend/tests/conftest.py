import pytest

from tests import helpers


@pytest.fixture
def settings(tmp_path):
    return helpers.make_settings(tmp_path)


@pytest.fixture
def make_video(tmp_path):
    return lambda name="clip.mp4", **kw: helpers.make_video(tmp_path / name, **kw)
