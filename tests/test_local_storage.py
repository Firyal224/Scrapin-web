import pytest

from scraper.storage.local_storage import place_key, save_image


@pytest.mark.parametrize("place_id", ["osm:node/1234567890", "osm:way/5", "ChIJj61dQgK6j4AR4GeTYWZsKWw"])
def test_place_key_is_windows_and_url_safe(place_id):
    key = place_key("Kopi A: Cabang/Kemang <b>", place_id)
    assert not set(key) & set(':/\\<>"|?* ')
    assert key.startswith("Kopi_A_Cabang_Kemang_b")


def test_save_image_uses_sanitized_stem(tmp_path):
    name = save_image(b"data", "../../evil name", tmp_path)
    assert name == "evil_name.jpg"
    assert (tmp_path / "images" / name).read_bytes() == b"data"
