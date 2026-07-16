from wantlist.domain.bandcamp import bandcamp_search_url


def test_bandcamp_search_url_encodes_artist_and_title() -> None:
    url = bandcamp_search_url("Floating Points", "Cascade")
    assert url == "https://bandcamp.com/search?q=Floating+Points+Cascade"


def test_bandcamp_search_url_escapes_specials() -> None:
    url = bandcamp_search_url("Sigur Rós", "( )")
    assert url.startswith("https://bandcamp.com/search?q=")
    assert " " not in url  # fully url-encoded
