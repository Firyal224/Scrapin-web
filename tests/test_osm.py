import pytest

from scraper.models import SourceError
from scraper.service import ScrapeRequest
from scraper.sources.osm import AreaFilter, OsmClient, build_query, element_to_place


class FakeResponse:
    def __init__(self, status: int, payload) -> None:
        self.status_code = status
        self.ok = 200 <= status < 300
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.headers = {}
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0)


AREA = AreaFilter("area(3605802438)->.a", "Jakarta Selatan")
NOMINATIM_RELATION = [{"osm_type": "relation", "osm_id": "5802438", "name": "Jakarta Selatan", "lat": "-6.2", "lon": "106.8"}]


def test_build_query_known_keyword_uses_tags_only():
    query = build_query("Salon", AREA)
    assert 'area(3605802438)->.a;' in query
    assert 'nwr["shop"~"^(hairdresser|beauty)$"]["name"](area.a);' in query
    assert '"name"~' not in query


def test_build_query_can_require_website():
    query = build_query("cafe", AREA, require_website=True)
    assert 'nwr["amenity"~"^(cafe)$"]["name"][~"^(website|contact:website|url)$"~"."](area.a);' in query
    assert "website" not in build_query("cafe", AREA)


def test_build_query_unknown_keyword_matches_name():
    query = build_query("seblak", AREA)
    assert 'nwr["amenity"]["name"~"seblak",i](area.a);' in query


def test_build_query_sanitizes_free_text():
    query = build_query('toko "kue" (enak)', AREA)
    assert '"toko kue enak"' in query
    assert '(enak)' not in query


def test_build_query_around_for_point_area():
    query = build_query("cafe", AreaFilter("(around:3000,-6.2,106.8)", "Kemang"))
    assert "area.a" not in query
    assert '(around:3000,-6.2,106.8);' in query


def test_element_to_place_maps_contacts():
    place = element_to_place({
        "type": "node", "id": 1,
        "tags": {"name": "Kopi A", "contact:phone": "0812 1111 2222;021 123", "website": "https://kopia.id",
                 "contact:instagram": "@kopia", "addr:street": "Jl. Kemang", "image": "javascript:alert(1)"},
    }, "Jakarta Selatan")
    assert place.phone == "0812 1111 2222"
    assert place.instagram == "https://www.instagram.com/kopia/"
    assert place.photos == ()
    assert "Kopi+A%2C+Jl.+Kemang%2C+Jakarta+Selatan" in place.maps_url
    assert element_to_place({"type": "node", "id": 2, "tags": {}}, "X") is None


def test_element_to_place_uses_instagram_website():
    place = element_to_place({"type": "node", "id": 3, "tags": {"name": "B", "website": "https://instagram.com/bbb"}}, "X")
    assert place.instagram == "https://www.instagram.com/bbb/"


def test_search_ranks_by_completeness_and_dedupes():
    elements = [
        {"type": "node", "id": 1, "tags": {"name": "Polos"}},
        {"type": "node", "id": 2, "tags": {"name": "Lengkap", "phone": "08121112222", "website": "https://a.id"}},
        {"type": "way", "id": 3, "tags": {"name": "lengkap"}},
    ]
    session = FakeSession([FakeResponse(200, NOMINATIM_RELATION), FakeResponse(200, {"elements": elements})])
    places = list(OsmClient(session).search(ScrapeRequest.create("cafe", "Jaksel", 5)))

    assert [p.name for p in places] == ["Lengkap", "Polos"]
    assert session.calls[0][2]["params"]["q"] == "jakarta selatan"
    assert "area(3605802438)" in session.calls[1][2]["data"]["data"]


def test_search_falls_back_to_mirror_when_busy():
    session = FakeSession([
        FakeResponse(200, NOMINATIM_RELATION),
        FakeResponse(504, "busy"),
        FakeResponse(200, {"elements": [{"type": "node", "id": 1, "tags": {"name": "A"}}]}),
    ])
    places = list(OsmClient(session).search(ScrapeRequest.create("cafe", "Jakarta Selatan", 5)))
    assert [p.name for p in places] == ["A"]
    assert "mail.ru" in session.calls[2][1]


def test_unknown_area_has_clear_message():
    session = FakeSession([FakeResponse(200, [])])
    with pytest.raises(SourceError, match="tidak ditemukan"):
        list(OsmClient(session).search(ScrapeRequest.create("cafe", "Antah Berantah", 5)))
