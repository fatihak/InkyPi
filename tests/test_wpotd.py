from unittest.mock import Mock, patch

import pytest

from plugins.wpotd.wpotd import Wpotd


@pytest.fixture
def plugin():
    p = Wpotd.__new__(Wpotd)
    p.image_loader = Mock()
    return p


@pytest.mark.parametrize(
    "url",
    [
        "https://upload.wikimedia.org/wikipedia/commons/6/6d/Le_Voyage_dans_la_Lune_%281902%29.webm",
        "https://upload.wikimedia.org/wikipedia/commons/a/ab/Clip.OGV?download=1",
        "https://upload.wikimedia.org/wikipedia/commons/a/ab/Song.ogg",
        "https://upload.wikimedia.org/wikipedia/commons/a/ab/Movie.mp4",
    ],
)
@pytest.mark.parametrize("resize", [True, False])
def test_non_image_urls_are_rejected_before_download(plugin, url, resize):
    with patch("plugins.wpotd.wpotd.get_http_session") as session:
        with pytest.raises(RuntimeError):
            plugin._download_image(url, dimensions=(800, 480), resize=resize)
    session.assert_not_called()
    plugin.image_loader.from_url.assert_not_called()


def test_image_url_with_query_still_downloads(plugin):
    url = "https://upload.wikimedia.org/wikipedia/commons/a/ab/Photo.jpg?x=1"
    plugin.image_loader.from_url.return_value = "img"
    assert plugin._download_image(url, dimensions=(800, 480), resize=True) == "img"
    plugin.image_loader.from_url.assert_called_once()
