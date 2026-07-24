from sqlalchemy.orm import Session, sessionmaker

from wantlist.adapters.beets import BeetsAlbum
from wantlist.adapters.beets_cache import BeetsCatalogCache


def test_replace_then_read_round_trips(clean_album_tables: sessionmaker[Session]) -> None:
    cache = BeetsCatalogCache(clean_album_tables)
    assert cache.all_albums() == []  # cold: empty until the worker fills it
    albums = [
        BeetsAlbum("b1", "Artist", "One", "rg-1"),
        BeetsAlbum("b2", "Other", "Two", None),
    ]
    cache.replace(albums)
    got = {a.beets_id: a for a in cache.all_albums()}
    assert set(got) == {"b1", "b2"}
    assert got["b1"].mb_releasegroup_id == "rg-1"
    assert got["b2"].mb_releasegroup_id is None


def test_replace_is_a_full_swap_not_an_append(clean_album_tables: sessionmaker[Session]) -> None:
    cache = BeetsCatalogCache(clean_album_tables)
    cache.replace([BeetsAlbum("old", "A", "Gone", None)])
    cache.replace([BeetsAlbum("new", "B", "Here", "rg-9")])
    ids = {a.beets_id for a in cache.all_albums()}
    assert ids == {"new"}  # the previous snapshot is gone, not accumulated
