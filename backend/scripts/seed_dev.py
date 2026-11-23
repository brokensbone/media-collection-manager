# ruff: noqa: E501
"""Fill a development database with plausible data so every view has something to show.

Usage (from backend/, with MCM_DATABASE_URL pointing at a throwaway database):

    uv run python scripts/seed_dev.py --rich            # refuse if albums already exist
    uv run python scripts/seed_dev.py --rich --reset    # wipe every app table, then reseed

Without --rich only a handful of rows per view are written. Nothing here runs unless invoked,
and no external integration is contacted: the worker-owned caches (beets catalogue, job
heartbeats, activity feed) are written directly, as the worker would have left them.
"""

import argparse
import hashlib
import random
import struct
import sys
import zlib
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from mcm.config import Settings
from mcm.db import make_engine, make_session_factory
from mcm.models import (
    Album,
    AlbumArt,
    AlbumState,
    BeetsAlbumCache,
    BeetsTrackCache,
    Box,
    ImportSource,
    ImportState,
    ImportTarget,
    JobRun,
    LinkSource,
    MediaKind,
    PendingImport,
    PlayHistory,
    Provenance,
    RadioNavidromeSync,
    RecordBox,
    SeenRelease,
    SpotifyAuth,
    WorkerEvent,
)
from mcm.radio_schedules import (
    RadioScheduleService,
    ScheduleInput,
    ScheduleItemInput,
    ScheduleSessionInput,
)

# Every table the app owns, children first. alembic_version is deliberately absent.
_TABLES = (
    "radio_navidrome_sync",
    "radio_schedule_item",
    "radio_schedule_session",
    "radio_schedule",
    "beets_track_cache",
    "record_box",
    "box",
    "beets_album_cache",
    "worker_event",
    "pending_import",
    "album_art",
    "play_history",
    "seen_release",
    "job_run",
    "album",
    "notification_state",
    "spotify_auth",
    "telegram_worklist_offer",
    "telegram_worklist_state",
)

# --- the beets library: (artist, title, year, genre, label, media, country, secondary) -------
# fmt: off
LIBRARY: list[tuple[str, str, int, str, str, str, str, str | None]] = [
    ("Radiohead", "In Rainbows", 2007, "Rock", "XL Recordings", "Digital Media", "GB", None),
    ("Radiohead", "OK Computer", 1997, "Rock", "Parlophone", "CD", "GB", None),
    ("Boards of Canada", "Music Has the Right to Children", 1998, "Electronic", "Warp", "CD", "GB", None),
    ("Aphex Twin", "Selected Ambient Works 85-92", 1992, "Electronic", "Apollo", "12\" Vinyl", "BE", None),
    ("Burial", "Untrue", 2007, "Electronic", "Hyperdub", "CD", "GB", None),
    ("Burial", "Rival Dealer", 2013, "Electronic", "Hyperdub", "12\" Vinyl", "GB", None),
    ("Massive Attack", "Mezzanine", 1998, "Electronic", "Virgin", "CD", "GB", None),
    ("Portishead", "Dummy", 1994, "Electronic", "Go! Beat", "CD", "GB", None),
    ("Björk", "Homogenic", 1997, "Electronic", "One Little Indian", "CD", "GB", None),
    ("Miles Davis", "Kind of Blue (Legacy Edition)", 1959, "Jazz", "Columbia", "CD", "US", None),
    ("John Coltrane", "A Love Supreme", 1965, "Jazz", "Impulse!", "12\" Vinyl", "US", None),
    ("Alice Coltrane", "Journey in Satchidananda", 1971, "Jazz", "Impulse!", "12\" Vinyl", "US", None),
    ("Pharoah Sanders", "Karma", 1969, "Jazz", "Impulse!", "12\" Vinyl", "US", None),
    ("Kamasi Washington", "The Epic", 2015, "Jazz", "Brainfeeder", "Digital Media", "US", None),
    ("Floating Points, Pharoah Sanders & The London Symphony Orchestra", "Promises", 2021, "Jazz", "Luaka Bop", "12\" Vinyl", "US", None),
    ("Kendrick Lamar", "To Pimp a Butterfly", 2015, "Hip-Hop", "Top Dawg Entertainment", "Digital Media", "US", None),
    ("A Tribe Called Quest", "The Low End Theory", 1991, "Hip-Hop", "Jive", "CD", "US", None),
    ("J Dilla", "Donuts", 2006, "Hip-Hop", "Stones Throw", "CD", "US", None),
    ("Madvillain", "Madvillainy", 2004, "Hip-Hop", "Stones Throw", "12\" Vinyl", "US", None),
    ("Mos Def", "Black on Both Sides", 1999, "Hip-Hop", "Rawkus", "CD", "US", None),
    ("Wu-Tang Clan", "Enter the Wu-Tang (36 Chambers)", 1993, "Hip-Hop", "Loud", "CD", "US", None),
    ("The Beatles", "Revolver", 1966, "Rock", "Parlophone", "12\" Vinyl", "GB", None),
    ("The Velvet Underground & Nico", "The Velvet Underground & Nico", 1967, "Rock", "Verve", "CD", "US", None),
    ("Talking Heads", "Remain in Light", 1980, "Rock", "Sire", "12\" Vinyl", "US", None),
    ("Joy Division", "Unknown Pleasures", 1979, "Rock", "Factory", "12\" Vinyl", "GB", None),
    ("New Order", "Power, Corruption & Lies", 1983, "Electronic", "Factory", "12\" Vinyl", "GB", None),
    ("The Cure", "Disintegration (Deluxe Edition)", 1989, "Rock", "Fiction", "CD", "GB", None),
    ("My Bloody Valentine", "Loveless", 1991, "Rock", "Creation", "CD", "GB", None),
    ("Slowdive", "Souvlaki", 1993, "Rock", "Creation", "CD", "GB", None),
    ("Cocteau Twins", "Heaven or Las Vegas", 1990, "Rock", "4AD", "CD", "GB", None),
    ("Pixies", "Doolittle", 1989, "Rock", "4AD", "CD", "GB", None),
    ("Sonic Youth", "Daydream Nation", 1988, "Rock", "Enigma", "CD", "US", None),
    ("Pavement", "Slanted and Enchanted", 1992, "Rock", "Matador", "CD", "US", None),
    ("Yo La Tengo", "I Can Hear the Heart Beating as One", 1997, "Rock", "Matador", "CD", "US", None),
    ("Arcade Fire", "Funeral", 2004, "Rock", "Merge", "CD", "CA", None),
    ("LCD Soundsystem", "Sound of Silver", 2007, "Electronic", "DFA", "CD", "US", None),
    ("Daft Punk", "Discovery", 2001, "Electronic", "Virgin", "CD", "FR", None),
    ("Daft Punk", "Random Access Memories", 2013, "Electronic", "Columbia", "12\" Vinyl", "FR", None),
    ("Four Tet", "Rounds", 2003, "Electronic", "Domino", "CD", "GB", None),
    ("Caribou", "Swim", 2010, "Electronic", "City Slang", "CD", "DE", None),
    ("Jon Hopkins", "Immunity", 2013, "Electronic", "Domino", "Digital Media", "GB", None),
    ("Bonobo", "Black Sands", 2010, "Electronic", "Ninja Tune", "CD", "GB", None),
    ("The Avalanches", "Since I Left You", 2000, "Electronic", "Modular", "CD", "AU", None),
    ("DJ Shadow", "Endtroducing.....", 1996, "Electronic", "Mo' Wax", "CD", "GB", None),
    ("Fela Ransome Kuti & Africa 70", "Expensive Shit", 1975, "Afrobeat", "Sound Workshop", "12\" Vinyl", "NG", None),
    ("Khruangbin", "Con Todo El Mundo", 2018, "Funk", "Dead Oceans", "12\" Vinyl", "US", None),
    ("Nick Drake", "Pink Moon", 1972, "Folk", "Island", "12\" Vinyl", "GB", None),
    ("Joni Mitchell", "Blue", 1971, "Folk", "Reprise", "12\" Vinyl", "US", None),
    ("Leonard Cohen", "Songs of Leonard Cohen", 1967, "Folk", "Columbia", "CD", "US", None),
    ("Bob Dylan", "Highway 61 Revisited", 1965, "Folk", "Columbia", "CD", "US", None),
    ("Marvin Gaye", "What's Going On", 1971, "Soul", "Tamla", "12\" Vinyl", "US", None),
    ("Stevie Wonder", "Songs in the Key of Life", 1976, "Soul", "Tamla", "12\" Vinyl", "US", None),
    ("Prince", "Sign o' the Times", 1987, "Funk", "Paisley Park", "CD", "US", None),
    ("D'Angelo", "Voodoo", 2000, "Soul", "Virgin", "CD", "US", None),
    ("Erykah Badu", "Baduizm", 1997, "Soul", "Kedar", "CD", "US", None),
    ("Frank Ocean", "Blonde", 2016, "Soul", "Boys Don't Cry", "Digital Media", "US", None),
    ("Sufjan Stevens", "Carrie & Lowell", 2015, "Folk", "Asthmatic Kitty", "CD", "US", None),
    ("Bon Iver", "For Emma, Forever Ago", 2007, "Folk", "Jagjaguwar", "CD", "US", None),
    ("Fleet Foxes", "Fleet Foxes", 2008, "Folk", "Sub Pop", "CD", "US", None),
    ("Big Thief", "Dragon New Mountain I Believe in You", 2022, "Folk", "4AD", "Digital Media", "US", None),
    ("Phoebe Bridgers", "Punisher", 2020, "Rock", "Dead Oceans", "Digital Media", "US", None),
    ("Brian Eno", "Ambient 1: Music for Airports", 1978, "Ambient", "Polydor", "12\" Vinyl", "GB", None),
    ("William Basinski", "The Disintegration Loops", 2002, "Ambient", "2062", "CD", "US", None),
    ("Stars of the Lid", "And Their Refinement of the Decline", 2007, "Ambient", "Kranky", "CD", "US", None),
    ("Grouper", "Dragging a Dead Deer Up a Hill", 2008, "Ambient", "Type", "CD", "GB", None),
    ("Tim Hecker", "Ravedeath, 1972", 2011, "Ambient", "Kranky", "CD", "US", None),
    ("Steve Reich", "Music for 18 Musicians", 1978, "Classical", "ECM", "CD", "DE", None),
    ("Arvo Pärt", "Tabula Rasa", 1984, "Classical", "ECM", "CD", "DE", None),
    ("Nils Frahm", "Spaces", 2013, "Ambient", "Erased Tapes", "Digital Media", "DE", "live"),
    ("Moodymann", "DJ-Kicks", 2016, "Electronic", "!K7", "Digital Media", "DE", "compilation; dj-mix"),
    ("Bonobo", "Late Night Tales: Bonobo", 2013, "Electronic", "Late Night Tales", "CD", "GB", "compilation; dj-mix"),
    ("Floating Points", "Fabric Presents Floating Points", 2023, "Electronic", "fabric", "Digital Media", "GB", "compilation; dj-mix"),
    ("Various Artists", "Studio One Rockers", 2001, "Reggae", "Soul Jazz Records", "CD", "GB", "compilation"),
    ("Various Artists", "Nuggets: Original Artyfacts from the First Psychedelic Era", 1972, "Rock", "Elektra", "CD", "US", "compilation"),
    ("Various Artists", "Kompakt Total 20", 2020, "Electronic", "Kompakt", "Digital Media", "DE", "compilation"),
    ("Talk Talk", "Spirit of Eden", 1988, "Rock", "Parlophone", "CD", "GB", None),
    ("Kate Bush", "Hounds of Love", 1985, "Rock", "EMI", "12\" Vinyl", "GB", None),
    ("Beach House", "Teen Dream", 2010, "Rock", "Sub Pop", "CD", "US", None),
    ("Tame Impala", "Currents", 2015, "Rock", "Modular", "Digital Media", "AU", None),
    ("Fred again..", "Actual Life (April 14 – December 17 2020)", 2021, "Electronic", "Atlantic", "Digital Media", "GB", None),
    ("Jamie xx", "In Colour", 2015, "Electronic", "Young Turks", "CD", "GB", None),
    ("Mount Kimbie", "Crooks & Lovers", 2010, "Electronic", "Hotflush", "CD", "GB", None),
    ("Vangelis", "Blade Runner", 1994, "Soundtrack", "East West", "CD", "GB", "soundtrack"),
    ("Mica Levi", "Under the Skin", 2014, "Soundtrack", "Milan", "Digital Media", "GB", "soundtrack"),
    ("Ryuichi Sakamoto", "async", 2017, "Ambient", "Milan", "CD", "JP", None),
    ("Bicep", "Isles", 2021, "Electronic", "Ninja Tune", "Digital Media", "GB", None),
    ("Overmono", "Good Lies", 2023, "Electronic", "XL Recordings", "Digital Media", "GB", None),
    ("Talking Heads", "Stop Making Sense", 1984, "Rock", "Sire", "CD", "US", "live; soundtrack"),
    ("Nina Simone", "Live at Town Hall", 1959, "Jazz", "Colpix", "12\" Vinyl", "US", "live"),
]

# Tracked Spotify albums, by funnel state: (artist, title, year, album_type)
SAVED = [
    ("Sault", "Untitled (Black Is)", 2020, "album"),
    ("Little Simz", "Sometimes I Might Be Introvert", 2021, "album"),
    ("Black Country, New Road", "Ants from Up There", 2022, "album"),
    ("Wednesday", "Rat Saw God", 2023, "album"),
    ("Mk.gee", "Two Star & the Dream Police", 2024, "album"),
    ("Nala Sinephro", "Endlessness", 2024, "album"),
    ("Jessica Pratt", "Here in the Pitch", 2024, "album"),
    ("Floating Points", "Cascade", 2024, "album"),
    ("Kelly Lee Owens", "Dreamstate", 2024, "album"),
    ("Kendrick Lamar", "GNX", 2024, "album"),
    ("Japanese Breakfast", "For Melancholy Brunettes (& Sad Women)", 2025, "album"),
    ("Turnstile", "Never Enough", 2025, "album"),
    ("Sudan Archives", "The BPM", 2025, "album"),
    ("Panda Bear", "Sinister Grift", 2025, "album"),
    ("FKA twigs", "Eusexua", 2025, "album"),
    ("Caribou", "Honey", 2024, "album"),
    ("Jamie xx", "In Waves", 2024, "album"),
    ("Four Tet", "Three", 2024, "album"),
    ("Big Thief", "Double Infinity", 2025, "album"),
    ("Fred again..", "USB002", 2026, "album"),
    ("Sampha", "Hollow Ground", 2026, "album"),
    ("Nilüfer Yanya", "Common Ground", 2026, "album"),
    ("Loraine James", "Stillness Returns", 2026, "album"),
    ("Bicep", "Chroma 004", 2026, "single"),
    ("Erika de Casier", "Lucky", 2026, "single"),
    ("Yaeji", "Pinball Summer", 2026, "single"),
    ("Arooj Aftab", "Night Reign", 2024, "album"),
    ("Various Artists", "Bristol Archive Records: Dub Plates 1979–1984", 2025, "compilation"),
    ("Beth Gibbons", "Lives Outgrown", 2024, "album"),
    ("Cleo Sol", "Gold", 2023, "album"),
]
WANTED = [
    ("Andy Stott", "Luxury Problems", 2012, "album"),
    ("Actress", "R.I.P.", 2012, "album"),
    ("Burial", "Antidawn", 2022, "single"),
    ("Shabaka", "Perceive Its Beauty, Acknowledge Its Grace", 2024, "album"),
    ("Yussef Dayes", "Black Classical Music", 2023, "album"),
    ("Moses Sumney", "græ", 2020, "album"),
    ("Arthur Russell", "World of Echo", 1986, "album"),
    ("Sade", "Love Deluxe", 1992, "album"),
    ("Boards of Canada", "Geogaddi", 2002, "album"),
    ("Can", "Tago Mago", 1971, "album"),
    ("Laurie Spiegel", "The Expanding Universe", 1980, "album"),
    ("Mary Lattimore", "Goodbye, Hotel Arkada", 2023, "album"),
    ("The Cure", "Disintegration", 1989, "album"),
    ("Talk Talk", "Laughing Stock", 1991, "album"),
    ("Cleo Sol", "Mother", 2021, "album"),
    ("Alice Coltrane", "The Carnegie Hall Concert", 2024, "album"),
]
SUGGESTED = [
    ("Radiohead", "Hail to the Thief (Live Recordings 2003–2009)", 2025, "album"),
    ("Burial", "Dreamfear / Boy Sent From Above", 2024, "single"),
    ("Kamasi Washington", "Lazarus (Original Soundtrack)", 2025, "album"),
    ("Four Tet", "Into Bloom", 2026, "single"),
    ("Caribou", "Broke My Heart (Remixes)", 2026, "single"),
    ("Jon Hopkins", "Ritual (Live at the Barbican)", 2026, "album"),
    ("Bon Iver", "SABLE, fABLE", 2025, "album"),
    ("Sufjan Stevens", "Javelin", 2023, "album"),
    ("Beach House", "Become", 2026, "single"),
    ("Floating Points", "Del Oro", 2026, "single"),
    ("Big Thief", "Grandmother", 2026, "single"),
    ("Phoebe Bridgers", "Tour Diary, Vol. 2", 2026, "album"),
    ("Little Simz", "Lotus", 2025, "album"),
    ("Kendrick Lamar", "Luther (Remix)", 2026, "single"),
    ("Jamie xx", "Dafodil (Edit)", 2026, "single"),
    ("Bicep", "Takkui", 2026, "single"),
    ("Overmono", "Cold Blooded", 2026, "single"),
    ("Mount Kimbie", "The Sunset Violent", 2024, "album"),
    ("Khruangbin", "A La Sala", 2024, "album"),
    ("Bonobo", "Fragments Live", 2026, "compilation"),
    ("The Avalanches", "Since I Left You (25th Anniversary Edition)", 2026, "album"),
    ("Grouper", "Shade", 2021, "album"),
]
DISMISSED = [
    ("Coldplay", "Moon Music", 2024, "album"),
    ("Imagine Dragons", "Loom", 2024, "album"),
    ("Ed Sheeran", "Play", 2025, "album"),
    ("Kings of Leon", "Can We Please Have Fun", 2024, "album"),
    ("Muse", "Will of the People", 2022, "album"),
    ("Radiohead", "In Rainbows Disk 2", 2007, "single"),
    ("Daft Punk", "Random Access Memories (Drumless Edition)", 2023, "album"),
    ("Tame Impala", "Deadbeat", 2025, "album"),
    ("Arcade Fire", "Pink Elephant", 2025, "album"),
    ("Bonobo", "Migration (Remixes)", 2017, "compilation"),
    ("The Killers", "Rebel Diamonds", 2023, "compilation"),
    ("Foals", "Life Is Yours", 2022, "album"),
    ("Royal Blood", "Back to the Water Below", 2023, "album"),
]
# fmt: on

_TRACK_WORDS = (
    "Glass Harbour Low Light Northern Line Pale Fire Static Bloom Night Bus Halfway Tides "
    "Silver Room Drift Lantern Open Field After Hours Sodium Orange Heatwave Paper Moon Echo "
    "Chamber Slow Motion Rooftop Signal Fade Afterglow Morning Glass Velvet Rain Cold Water "
    "Undertow Satellite Hollow Gold Weather Station Long Way Home Blue Hour Small Hours Wire "
    "Kingfisher Marrow Ember Cathedral Fog Tunnel Vision Daybreak Avalanche Polaroid Dust"
).split()
_EVENTS_MESSAGES_NO_MATCH = "No MusicBrainz release group found for '{a} — {t}'"


def _spotify_id(seed: str) -> str:
    alphabet = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    n = int(hashlib.sha256(seed.encode()).hexdigest(), 16)
    out = []
    for _ in range(22):
        n, r = divmod(n, 62)
        out.append(alphabet[r])
    return "".join(out)


def _rgid(seed: str) -> str:
    h = hashlib.md5(f"rg:{seed}".encode()).hexdigest()
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


def _png(seed: str, size: int = 300) -> bytes:
    """A deterministic two-colour diagonal-gradient cover, with an optional band, as a PNG.
    Pure Python (no Pillow): each row is a slice of one precomputed diagonal ramp."""
    rnd = random.Random(seed)

    def colour() -> tuple[int, int, int]:
        return (rnd.randrange(20, 236), rnd.randrange(20, 236), rnd.randrange(20, 236))

    c1, c2, band = colour(), colour(), colour()
    n = 2 * size
    ramp = bytearray()
    for i in range(n):
        t = i / (n - 1)
        ramp += bytes(round(a + (b - a) * t) for a, b in zip(c1, c2, strict=True))
    band_rows = range(0)
    if rnd.random() < 0.5:
        top = rnd.randrange(size // 5, size * 3 // 5)
        band_rows = range(top, top + rnd.randrange(size // 12, size // 4))
    band_row = bytes(band) * size
    raw = bytearray()
    for y in range(size):
        raw += b"\x00"
        raw += band_row if y in band_rows else ramp[y * 3 : (y + size) * 3]

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    header = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(bytes(raw), 6))
        + chunk(b"IEND", b"")
    )


def wipe(session: Session) -> None:
    session.execute(text(f"TRUNCATE {', '.join(_TABLES)} RESTART IDENTITY CASCADE"))
    # The migration seeds the root crate; put it back so the DB looks freshly migrated.
    session.add(Box(name="Collection", parent_id=None))
    session.commit()


class Seeder:
    def __init__(
        self,
        session: Session,
        *,
        rich: bool,
        now: datetime,
        today: date,
        watch_dir: Path | None = None,
    ) -> None:
        self.s = session
        self.rich = rich
        self.now = now
        self.today = today
        self.watch_dir = watch_dir
        self.rnd = random.Random(20261123)
        self.beets_ids: list[str] = []
        self.beets_by_key: dict[tuple[str, str], str] = {}
        self.tracks_by_album: dict[str, list[str]] = {}
        self.albums: dict[str, list[Album]] = {}

    def take[T](self, rows: list[T], small: int) -> list[T]:
        return rows if self.rich else rows[:small]

    def ago(self, **kw: float) -> datetime:
        return self.now - timedelta(**kw)

    # -- beets catalogue ------------------------------------------------------------------
    def library(self) -> None:
        item_id = 50_000
        for i, (artist, title, year, genre, label, media, country, secondary) in enumerate(
            self.take(LIBRARY, 12)
        ):
            beets_id = str(1001 + i)
            has_rg = i % 9 != 4  # a tail of as-is imports MusicBrainz never resolved
            self.s.add(
                BeetsAlbumCache(
                    beets_id=beets_id,
                    artist=artist,
                    title=title,
                    mb_releasegroup_id=_rgid(f"{artist}|{title}") if has_rg else None,
                    year=year,
                    media=media,
                    label=label,
                    country=country,
                    secondary_types=f"album; {secondary}" if secondary else "album",
                    genre=genre,
                    added_at=self.ago(days=self.rnd.uniform(2, 900)),
                    refreshed_at=self.ago(minutes=self.rnd.uniform(5, 50)),
                )
            )
            self.beets_ids.append(beets_id)
            self.beets_by_key[(artist, title)] = beets_id
        self.s.flush()
        for beets_id in self.beets_ids:
            album = self.s.get(BeetsAlbumCache, beets_id)
            assert album is not None
            count = self.rnd.randint(6, 14)
            discs = 2 if count >= 13 else 1
            names = self.rnd.sample(_TRACK_WORDS, count * 2)
            ids: list[str] = []
            for n in range(count):
                disc = 1 if discs == 1 or n < count // 2 else 2
                track = n + 1 if disc == 1 else n + 1 - count // 2
                name = f"{names[2 * n]} {names[2 * n + 1]}"
                item_id += 1
                self.s.add(
                    BeetsTrackCache(
                        item_id=str(item_id),
                        beets_id=beets_id,
                        disc=disc,
                        track=track,
                        title=name,
                        duration_seconds=round(self.rnd.uniform(150, 480), 1),
                        path=f"{album.artist}/{album.title}/{disc}-{track:02d} {name}.flac",
                    )
                )
                ids.append(str(item_id))
            self.tracks_by_album[beets_id] = ids
        self.s.flush()

    # -- tracked albums -------------------------------------------------------------------
    def _album(
        self,
        artist: str,
        title: str,
        year: int | None,
        album_type: str,
        state: AlbumState,
        provenance: Provenance,
        created: datetime,
        **extra: object,
    ) -> Album:
        album = Album(
            spotify_id=_spotify_id(f"{artist}|{title}"),
            artist=artist,
            artist_id=_spotify_id(f"artist|{artist}"),
            title=title,
            upc=str(self.rnd.randrange(10**11, 10**12)),
            art_url=f"https://i.scdn.co/image/ab67616d0000b273{hashlib.md5(title.encode()).hexdigest()[:24]}",
            album_type=album_type,
            release_year=year,
            state=state,
            provenance=provenance,
            created_at=created,
            updated_at=created,
            **extra,
        )
        self.s.add(album)
        self.albums.setdefault(state.value, []).append(album)
        return album

    def tracked(self) -> None:
        # Saved: the Decide queue. Oldest-first, spread over ~10 weeks; a few snoozed into the
        # future (hidden), a couple whose snooze lapsed (back in the queue).
        for i, (artist, title, year, kind) in enumerate(self.take(SAVED, 5)):
            saved = self.ago(days=70 - i * 2.3, hours=self.rnd.uniform(0, 12))
            snoozed = None
            if i in (3, 9, 14, 21):
                snoozed = self.now + timedelta(days=self.rnd.randint(2, 13))
            elif i in (6, 17):
                snoozed = self.ago(days=self.rnd.randint(1, 4))
            self._album(
                artist,
                title,
                year,
                kind,
                AlbumState.saved,
                Provenance.spotify_save,
                saved,
                saved_at=saved,
                snoozed_until=snoozed,
                mb_releasegroup_id=_rgid(f"{artist}|{title}") if i % 3 else None,
                resolution_attempts=0 if i % 3 else self.rnd.randint(1, 6),
            )
        for i, (artist, title, year, kind) in enumerate(self.take(WANTED, 4)):
            saved = self.ago(days=120 - i * 5)
            self._album(
                artist,
                title,
                year,
                kind,
                AlbumState.wanted,
                Provenance.manual if i == 7 else Provenance.spotify_save,
                saved,
                saved_at=saved,
                verdict_at=saved + timedelta(days=self.rnd.uniform(2, 20)),
                mb_releasegroup_id=_rgid(f"{artist}|{title}"),
            )
        for artist, title, year, kind in self.take(SUGGESTED, 5):
            created = self.ago(days=self.rnd.uniform(0.2, 21))
            self._album(
                artist,
                title,
                year,
                kind,
                AlbumState.suggested,
                Provenance.artist_watch,
                created,
            )
        for i, (artist, title, year, kind) in enumerate(self.take(DISMISSED, 3)):
            created = self.ago(days=40 + i * 6)
            from_watch = i % 2 == 0
            self._album(
                artist,
                title,
                year,
                kind,
                AlbumState.dismissed,
                Provenance.artist_watch if from_watch else Provenance.spotify_save,
                created,
                saved_at=None if from_watch else created,
                verdict_at=created + timedelta(days=self.rnd.uniform(0.5, 9)),
            )
        # Owned: the Spotify∩beets overlap. Most auto-linked by release group, a few by hand.
        owned_rows = [row for k, row in enumerate(self.take(LIBRARY, 12)) if k % 2 == 0]
        for i, (artist, title, year, *_rest) in enumerate(owned_rows):
            beets_id = self.beets_by_key[(artist, title)]
            cache = self.s.get(BeetsAlbumCache, beets_id)
            assert cache is not None
            saved = self.ago(days=self.rnd.uniform(60, 700))
            manual = cache.mb_releasegroup_id is None or i % 7 == 3
            self._album(
                artist,
                title,
                year,
                "album",
                AlbumState.owned,
                Provenance.spotify_save if i % 5 else Provenance.manual,
                saved,
                saved_at=saved,
                verdict_at=saved + timedelta(days=self.rnd.uniform(1, 30)),
                mb_releasegroup_id=cache.mb_releasegroup_id,
                owned_beets_id=beets_id,
                owned_link_source=LinkSource.manual if manual else LinkSource.auto,
            )
        self.s.flush()

    def art(self) -> None:
        for state_rows in self.albums.values():
            for album in state_rows:
                if self.rnd.random() < 0.1:
                    continue  # some albums never got art: exercise the placeholder
                image = _png(f"{album.artist}|{album.title}")
                self.s.add(
                    AlbumArt(
                        album_id=album.id,
                        content_type="image/png",
                        image=image,
                        size=300,
                        fetched_at=album.created_at,
                    )
                )
        self.s.flush()

    # -- play history, seen releases, auth --------------------------------------------------
    def plays(self) -> None:
        def play(album: Album, tracks: int, start: datetime, spread_days: float) -> None:
            assert album.spotify_id
            for t in range(tracks):
                at = start + timedelta(days=self.rnd.uniform(0, spread_days), seconds=t)
                self.s.add(
                    PlayHistory(
                        spotify_track_id=_spotify_id(f"track|{album.spotify_id}|{t}"),
                        spotify_album_id=album.spotify_id,
                        played_at=at,
                    )
                )

        for i, album in enumerate(self.albums.get("saved", [])):
            if i % 4 == 0:
                play(album, self.rnd.randint(5, 11), self.ago(days=6), 0.2)  # "N plays"
            elif i % 4 == 1:
                play(album, 2, self.ago(days=12), 7)  # "played over Nd"
            elif i % 4 == 2:
                play(album, 1, self.ago(days=2), 0)  # not enough for a hint
        for album in self.albums.get("owned", [])[:8]:
            play(album, self.rnd.randint(3, 10), self.ago(days=30), 25)

    def seen(self) -> None:
        artists = {
            a.artist_id: a.artist
            for state in ("owned", "wanted", "saved")
            for a in self.albums.get(state, [])
            if a.artist_id
        }
        for artist_id, artist in artists.items():
            for n in range(self.rnd.randint(3, 9)):
                self.s.add(
                    SeenRelease(
                        spotify_album_id=_spotify_id(f"seen|{artist}|{n}"),
                        artist_id=artist_id,
                        seen_at=self.ago(days=self.rnd.uniform(20, 200)),
                    )
                )
        for album in self.albums.get("suggested", []) + self.albums.get("dismissed", []):
            if album.provenance == Provenance.artist_watch and album.spotify_id:
                self.s.add(
                    SeenRelease(
                        spotify_album_id=album.spotify_id,
                        artist_id=album.artist_id or "",
                        seen_at=album.created_at,
                    )
                )

    def auth(self) -> None:
        # Status only reads the stored row, so a fake token shows "connected" without a call.
        self.s.add(
            SpotifyAuth(
                access_token="dev-seed-access-token",
                refresh_token="dev-seed-refresh-token",
                access_expires_at=self.now + timedelta(minutes=40),
                authorized_at=self.ago(days=97),
                scopes="user-library-read user-library-modify",
            )
        )

    def drop_path(self, name: str, state: ImportState) -> str:
        """A watch-folder drop's path. The Import view offers Import only while the drop is
        still on disk, so with --watch-dir the still-detected drops get placeholder files."""
        root = self.watch_dir or Path("/watch")
        path = root / f"{name}.zip"
        if self.watch_dir and state == ImportState.detected:
            root.mkdir(parents=True, exist_ok=True)
            path.touch()
        return str(path)

    # -- imports ----------------------------------------------------------------------------
    def imports(self) -> None:
        by_title = {a.title: a for rows in self.albums.values() for a in rows}

        def album_id(title: str) -> int | None:
            album = by_title.get(title)
            return album.id if album else None

        flac = [f"{n:02d} - {w}.flac" for n, w in enumerate(_TRACK_WORDS[:10], 1)]
        traceback = (
            "Traceback (most recent call last):\n"
            '  File "/app/src/mcm/imports.py", line 371, in _run_one\n'
            "    result = self._beets.import_dir(staged, copy=True)\n"
            '  File "/app/src/mcm/adapters/beets.py", line 212, in import_dir\n'
            "    raise BeetsError(proc.returncode, proc.stderr)\n"
        )
        rows: list[dict[str, object]] = [
            # Detected: the Import worklist.
            dict(
                name="Andy Stott - Luxury Problems (2012) [FLAC 24-44.1]",
                match="Luxury Problems",
                age=0.3,
            ),
            dict(name="Burial - Antidawn EP (2022) [WEB FLAC]", match="Antidawn", age=0.5),
            dict(
                name="Shabaka - Perceive Its Beauty, Acknowledge Its Grace (2024) [FLAC]",
                match="Perceive Its Beauty, Acknowledge Its Grace",
                age=1.2,
            ),
            dict(
                name="Sault - Untitled (Black Is) [2020] FLAC", match="Untitled (Black Is)", age=1.4
            ),
            dict(
                name="VA - Kompakt Total 25 (2025) [MP3 320]",
                age=1.6,
                detail="Audio files detected. No saved album matched.",
            ),
            dict(
                name="Mr Fingers - Amnesia (1989) Vinyl Rip 24-96",
                age=2.1,
                detail="Audio files detected. No saved album matched.",
            ),
            dict(
                name="Unknown Artist - Untitled Mix Tape Side A",
                age=3.5,
                detail="Audio files detected. No saved album matched.",
            ),
            dict(
                name="Nala Sinephro - Endlessness", source="watchdir", match="Endlessness", age=0.1
            ),
            dict(
                name="Mary Lattimore - Goodbye, Hotel Arkada",
                source="watchdir",
                match="Goodbye, Hotel Arkada",
                age=0.9,
            ),
            dict(
                name="Loraine James - Gentle Confrontation",
                source="watchdir",
                age=2.4,
                detail="Watch-folder audio drop.",
            ),
            dict(
                name="Severance.S02.1080p.ATVP.WEB-DL.DDP5.1.H.264",
                kind="tv",
                target="tv",
                age=0.7,
                detail="Detected TV episode pack for season 02.",
                dest="/media/tv/Severance/Season 02",
                audio=False,
                files=[f"Severance.S02E{e:02d}.1080p.ATVP.WEB-DL.mkv" for e in range(1, 11)],
            ),
            dict(
                name="Aftersun.2022.1080p.BluRay.x264-ROVERS",
                kind="film",
                target="film",
                age=1.1,
                detail="Detected a single-feature film.",
                dest="/media/films/Aftersun (2022)",
                audio=False,
                files=["Aftersun.2022.1080p.BluRay.x264-ROVERS.mkv", "Sample/aftersun.sample.mkv"],
            ),
            dict(
                name="Ableton Live Pack - Drone Lab v2.1",
                kind="workspace",
                target="workspace",
                age=2.9,
                detail="Manual override: workspace import.",
                dest="/media/workspace/Ableton Live Pack - Drone Lab v2.1",
                audio=False,
            ),
            dict(
                name="Mixed.Bag.2024.Collection",
                kind="unknown",
                target="review",
                age=3.2,
                detail="Video files found, but the title or type is ambiguous.",
                audio=False,
            ),
            dict(
                name="Slow.Horses.S04E01-E03.720p",
                kind="tv",
                target="review",
                age=4.0,
                detail="Detected TV episodes, but could not derive a single season destination.",
                audio=False,
            ),
            # Acted on: the Tasks view.
            dict(
                name="Yussef Dayes - Black Classical Music (2023) [FLAC]",
                match="Black Classical Music",
                state="queued",
                age=0.6,
                upd=0.02,
            ),
            dict(
                name="Arthur Russell - World of Echo (Remastered) [FLAC]",
                match="World of Echo",
                state="queued",
                age=0.8,
                upd=0.03,
            ),
            dict(
                name="Moses Sumney - græ (2020) [WEB FLAC]",
                match="græ",
                state="importing",
                age=0.9,
                upd=0.01,
            ),
            dict(
                name="Actress - R.I.P. (2012) [FLAC]",
                match="R.I.P.",
                state="failed",
                age=1.5,
                upd=0.2,
                error=traceback + "mcm.adapters.beets.BeetsError: beet import exited 1\n"
                "stderr: error: no matching release found for 14 tracks in /inbox/Actress - R.I.P. (2012) [FLAC]\n"
                "Skipping.",
            ),
            dict(
                name="Can - Tago Mago (40th Anniversary) [FLAC]",
                match="Tago Mago",
                state="failed",
                age=2.2,
                upd=0.9,
                error='rsync: [receiver] write failed on "/inbox/Can - Tago Mago (40th Anniversary) [FLAC]/04 - Halleluhwah.flac": '
                "No space left on device (28)\nrsync error: error in file IO (code 11) at receiver.c(381) [receiver=3.2.7]\n"
                "Transfer aborted after 1,204 MB of 1,876 MB.",
            ),
            dict(
                name="Laurie Spiegel - The Expanding Universe (2012 Reissue)",
                match="The Expanding Universe",
                state="failed",
                age=3.0,
                upd=2.5,
                error="TimeoutExpired: rsync from seedbox exceeded 21600s for 'Laurie Spiegel - The Expanding Universe (2012 Reissue)'",
            ),
            dict(
                name='Kompakt Speicher 128 (12") [WEB]',
                source="watchdir",
                state="failed",
                age=1.0,
                upd=0.4,
                error=traceback + "mcm.adapters.beets.BeetsError: beet import exited 2\n"
                "stderr: zipfile.BadZipFile: File is not a zip file\n",
            ),
            dict(
                name="Big Thief - Double Infinity (2025) [FLAC]",
                match="Double Infinity",
                state="imported",
                age=1.0,
                upd=0.3,
            ),
            dict(
                name="Kelly Lee Owens - Dreamstate [WEB FLAC]",
                match="Dreamstate",
                state="imported",
                age=2.0,
                upd=1.1,
            ),
            dict(
                name="Jessica Pratt - Here in the Pitch",
                source="watchdir",
                match="Here in the Pitch",
                state="imported",
                age=2.5,
                upd=1.8,
            ),
            dict(
                name="Beth Gibbons - Lives Outgrown (2024) [FLAC]",
                match="Lives Outgrown",
                state="imported",
                age=2.8,
                upd=2.6,
            ),
            dict(
                name="Radiohead - In Rainbows (2007) [FLAC]",
                state="skipped",
                age=1.3,
                upd=1.2,
                detail="Audio files detected.",
            ),
            dict(
                name="Four Tet - Rounds (10th Anniversary)",
                source="watchdir",
                state="skipped",
                age=2.2,
                upd=2.0,
            ),
            # Older completed: only the archive.
            *[
                dict(name=name, state="imported", age=age, upd=age - 0.2)
                for name, age in [
                    ("Caribou - Swim (2010) [FLAC]", 9),
                    ("Jon Hopkins - Immunity [FLAC 24-48]", 14),
                    ("Bicep - Isles (2021) [WEB FLAC]", 20),
                    ("Overmono - Good Lies (2023) [FLAC]", 31),
                    ("Mount Kimbie - Crooks & Lovers [FLAC]", 45),
                    ("Jamie xx - In Colour (2015) [FLAC]", 52),
                    ("Mica Levi - Under the Skin OST [FLAC]", 60),
                    ("Ryuichi Sakamoto - async (2017) [FLAC]", 77),
                ]
            ],
            dict(name="Beach House - Teen Dream (2010) [FLAC]", state="skipped", age=33, upd=32.8),
            # Dismissed: discarded or skipped as non-music.
            dict(
                name="ubuntu-24.04.1-desktop-amd64.iso",
                kind="unknown",
                target="review",
                state="dismissed",
                age=5,
                detail="No audio or video files detected.",
                audio=False,
                files=["ubuntu-24.04.1-desktop-amd64.iso"],
            ),
            dict(
                name="The.Bear.S03.1080p.WEB.h264-ETHEL",
                kind="tv",
                target="tv",
                state="dismissed",
                age=6,
                detail="Detected TV episode pack for season 03.",
                dest="/media/tv/The Bear/Season 03",
                audio=False,
            ),
            dict(name="Coldplay - Moon Music (2024) [MP3 320]", state="dismissed", age=8),
            dict(
                name="Linux ISO bundle (Fedora 41 Workstation)",
                kind="unknown",
                target="review",
                state="dismissed",
                age=11,
                detail="No audio or video files detected.",
                audio=False,
            ),
        ]
        if not self.rich:
            rows = rows[:3] + rows[15:17] + rows[22:24]
        for n, row in enumerate(rows):
            source = ImportSource(str(row.get("source", "transmission")))
            name = str(row["name"])
            created = self.ago(days=float(row["age"]))  # type: ignore[arg-type]
            upd = row.get("upd")
            state = ImportState(str(row.get("state", "detected")))
            files = row.get("files") or (flac if row.get("kind", "music") == "music" else [])
            self.s.add(
                PendingImport(
                    source=source,
                    source_key=(
                        hashlib.sha1(name.encode()).hexdigest()
                        if source == ImportSource.transmission
                        else self.drop_path(name, state)
                    ),
                    name=name,
                    download_dir="/downloads/complete"
                    if source == ImportSource.transmission
                    else None,
                    files=files,
                    archive_path=(
                        self.drop_path(name, state) if source == ImportSource.watchdir else None
                    ),
                    media_kind=MediaKind(str(row.get("kind", "music"))),
                    import_target=ImportTarget(str(row.get("target", "beets"))),
                    classification_detail=str(row.get("detail", "Audio files detected.")),
                    destination_path=row.get("dest"),  # type: ignore[arg-type]
                    matched_album_id=album_id(str(row["match"])) if "match" in row else None,
                    state=state,
                    has_audio=(
                        None if source == ImportSource.watchdir else bool(row.get("audio", True))
                    ),
                    error_detail=row.get("error"),  # type: ignore[arg-type]
                    created_at=created,
                    updated_at=(
                        self.ago(days=float(upd))  # type: ignore[arg-type]
                        if upd is not None
                        else (created if state != ImportState.detected or n % 2 else None)
                    ),
                )
            )

    # -- worker-owned state -------------------------------------------------------------------
    def jobs(self) -> None:
        for job, every_min, errors, last_error_h in [
            ("ingest_saves", 60, 3, 70.0),
            ("reconcile", 60, 1, 300.0),
            ("play_history", 30, 0, None),
            ("artist_watch", 1440, 2, 30.0),
            ("transmission", 60, 7, 0.4),
            ("watchdir", 5, 0, None),
            ("imports", 0.5, 12, 0.2),
            ("alerts", 60, 0, None),
            ("navidrome", 1, 4, 22.0),
        ]:
            runs = int(60 * 24 * 21 / every_min)
            last = self.ago(minutes=self.rnd.uniform(0, min(every_min, 50)))
            self.s.add(
                JobRun(
                    job=job,
                    last_run_at=last,
                    # artist_watch has been failing since its last error: a stale heartbeat.
                    last_success_at=self.ago(hours=31) if job == "artist_watch" else last,
                    last_error_at=self.ago(hours=last_error_h) if last_error_h else None,
                    runs=runs,
                    errors=errors,
                )
            )

    def events(self) -> None:
        tracked = [a for rows in self.albums.values() for a in rows]
        total = 150 if self.rich else 20
        stamps = sorted(self.ago(hours=self.rnd.uniform(0, 40)) for _ in range(total))
        for at in stamps:
            album = self.rnd.choice(tracked)
            label = f"{album.artist} — {album.title}"
            job, kind, message = self.rnd.choice(
                [
                    (
                        "resolution",
                        "resolved",
                        f"Resolved '{label}' to a MusicBrainz release group",
                    ),
                    (
                        "resolution",
                        "resolved",
                        f"Resolved '{label}' to a MusicBrainz release group",
                    ),
                    (
                        "resolution",
                        "no_match",
                        _EVENTS_MESSAGES_NO_MATCH.format(a=album.artist, t=album.title),
                    ),
                    ("resolution", "error", "Couldn't reach MusicBrainz: ReadTimeout after 10.0s"),
                    (
                        "reconcile",
                        "owned",
                        f"Now owned: '{label}' (matched beets album by release group)",
                    ),
                    ("ingest", "saved", f"New Spotify save: '{label}'"),
                    (
                        "artist_watch",
                        "suggested",
                        f"New release from {album.artist}: '{album.title}'",
                    ),
                    (
                        "import",
                        "detected",
                        f"Detected download: '{album.artist} - {album.title} [FLAC]'",
                    ),
                    ("import", "importing", f"Importing '{album.artist} - {album.title} [FLAC]'"),
                    (
                        "import",
                        "imported",
                        f"Imported '{album.artist} - {album.title} [FLAC]' into beets",
                    ),
                    (
                        "import",
                        "skipped",
                        f"Skipped '{album.artist} - {album.title}': already in the library",
                    ),
                    (
                        "import",
                        "failed",
                        f"Import failed for '{album.artist} - {album.title}': beet import exited 1",
                    ),
                    (
                        "watchdir",
                        "detected",
                        f"Detected drop: '{album.artist} - {album.title}.zip'",
                    ),
                    (
                        "transmission",
                        "added",
                        f"Added torrent '{album.artist} - {album.title} (FLAC)'",
                    ),
                    (
                        "transmission",
                        "duplicate",
                        f"Torrent '{album.artist} - {album.title}' was already in Transmission",
                    ),
                ]
            )
            self.s.add(
                WorkerEvent(
                    created_at=at,
                    job=job,
                    type=kind,
                    message=message,
                    album_id=album.id if job not in ("transmission", "watchdir") else None,
                )
            )

    def crates(self) -> None:
        root = self.s.scalar(select(Box).where(Box.parent_id.is_(None)))
        assert root is not None
        if not self.rich:
            return

        def box(name: str, parent: Box, age_days: float) -> Box:
            b = Box(name=name, parent_id=parent.id, created_at=self.ago(days=age_days))
            self.s.add(b)
            self.s.flush()
            return b

        electronic = box("Electronic", root, 120)
        ambient = box("Ambient & Drone", electronic, 90)
        dance = box("Dance floor", electronic, 88)
        jazz = box("Jazz", root, 118)
        spiritual = box("Spiritual jazz", jazz, 60)
        rock = box("Guitars", root, 115)
        shoegaze = box("Shoegaze & dream pop", rock, 40)
        hiphop = box("Hip-Hop", root, 110)
        box("Mixes", root, 20)  # empty, so a childless leaf the UI can delete
        folk = box("Folk & songwriters", root, 100)

        placement = {
            "Electronic": electronic,
            "Ambient": ambient,
            "Jazz": jazz,
            "Hip-Hop": hiphop,
            "Folk": folk,
            "Rock": rock,
        }
        cache = {c.beets_id: c for c in self.s.scalars(select(BeetsAlbumCache))}
        for n, beets_id in enumerate(self.beets_ids):
            c = cache[beets_id]
            if n % 6 == 5:
                continue  # leave a few loose in the root Collection
            target = placement.get(c.genre or "")
            if target is None:
                continue
            if c.genre == "Jazz" and c.label == "Impulse!":
                target = spiritual
            elif c.genre == "Electronic" and c.label in (
                "Ninja Tune",
                "XL Recordings",
                "Hotflush",
                "Domino",
            ):
                target = dance
            elif c.genre == "Rock" and c.label in ("Creation", "4AD") and "Pixies" not in c.artist:
                target = shoegaze
            self.s.add(RecordBox(beets_id=beets_id, box_id=target.id))

    def flush(self) -> None:
        self.s.commit()


def radio(service: RadioScheduleService, seeder: Seeder, session: Session) -> None:
    rnd = random.Random(7)
    ids = seeder.beets_ids
    cache = {c.beets_id: c for c in session.scalars(select(BeetsAlbumCache))}

    def tracks_for(n: int, genres: set[str] | None = None) -> list[ScheduleItemInput]:
        pool = [b for b in ids if genres is None or cache[b].genre in genres]
        chosen = []
        for _ in range(n):
            chosen.append(rnd.choice(seeder.tracks_by_album[rnd.choice(pool)]))
        return [ScheduleItemInput(kind="track", beets_id=None, item_id=t) for t in chosen]

    def albums_for(n: int) -> list[ScheduleItemInput]:
        return [
            ScheduleItemInput(kind="album", beets_id=b, item_id=None) for b in rnd.sample(ids, n)
        ]

    offsets = [-14, -7, -4, -3, -2, -1, 0, 1, 2] if seeder.rich else [-1, 0]
    notes = [
        "Rainy day — keep it gentle until lunch.",
        None,
        "Focus day: long instrumentals, no vocals before noon.",
        "Build towards something danceable.",
        None,
        "Guest in the office; nothing too abrasive.",
    ]
    for offset in offsets:
        day = seeder.today + timedelta(days=offset)
        sessions = [
            ScheduleSessionInput(
                "track_hour",
                "Morning warm-up",
                "09:00",
                "Soft starts and ambient openers.",
                tracks_for(rnd.randint(10, 15), {"Ambient", "Folk", "Jazz", "Classical"}),
            ),
            ScheduleSessionInput("album_session", "Album hour", "10:00", None, albums_for(1)),
            ScheduleSessionInput(
                "track_hour", "Late morning mix", "11:15", None, tracks_for(rnd.randint(12, 16))
            ),
            ScheduleSessionInput(
                "album_session",
                "Afternoon albums",
                "13:00",
                "Front to back, no skipping.",
                albums_for(rnd.randint(2, 3)),
            ),
            ScheduleSessionInput(
                "track_hour",
                "Wind-down",
                "16:30",
                None,
                tracks_for(rnd.randint(8, 12), {"Ambient", "Soul", "Electronic"}),
            ),
        ]
        if offset % 3 == 0:
            sessions = sessions[:4]
        service.replace(day, ScheduleInput(note=rnd.choice(notes), sessions=sessions))

    now = seeder.now
    statuses = {0: "synced", -1: "synced", -2: "error", 1: "pending", -3: "disabled"}
    from mcm.models import RadioSchedule

    for offset, status in statuses.items():
        sched = session.scalar(
            select(RadioSchedule).where(
                RadioSchedule.schedule_date == seeder.today + timedelta(days=offset)
            )
        )
        if sched is None:
            continue
        session.add(
            RadioNavidromeSync(
                schedule_id=sched.id,
                enabled=status != "disabled",
                status=status,
                playlist_id=f"pl-{sched.schedule_date:%Y%m%d}" if status == "synced" else None,
                last_synced_at=now - timedelta(hours=2 - offset) if status == "synced" else None,
                last_attempt_at=now - timedelta(minutes=30) if status != "disabled" else None,
                error="3 tracks had no exact path match in Navidrome"
                if status == "error"
                else None,
                unmatched_paths=(
                    [
                        "Talk Talk/Spirit of Eden/1-03 Ember Cathedral.flac",
                        "Grouper/Dragging a Dead Deer Up a Hill/1-07 Fog Tunnel.flac",
                        "Arvo Pärt/Tabula Rasa/1-02 Velvet Rain.flac",
                    ]
                    if status == "error"
                    else []
                ),
                track_count=rnd.randint(60, 90) if status == "synced" else 0,
            )
        )
    session.commit()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--rich", action="store_true", help="seed every view densely (else a handful of rows)"
    )
    parser.add_argument("--reset", action="store_true", help="truncate every app table first")
    parser.add_argument(
        "--watch-dir",
        type=Path,
        help="create placeholder files here for watch-folder drops awaiting import",
    )
    args = parser.parse_args()

    settings = Settings()
    engine = make_engine(settings.database_url)
    sf = make_session_factory(engine)
    now = datetime.now(UTC).replace(microsecond=0)

    with sf() as session:
        if args.reset:
            wipe(session)
        elif session.scalar(select(func.count()).select_from(Album)):
            print("Database already has albums; pass --reset to wipe and reseed.", file=sys.stderr)
            return 1

        seeder = Seeder(
            session, rich=args.rich, now=now, today=date.today(), watch_dir=args.watch_dir
        )
        seeder.library()
        seeder.tracked()
        seeder.art()
        seeder.plays()
        seeder.seen()
        seeder.auth()
        seeder.imports()
        seeder.jobs()
        seeder.events()
        seeder.crates()
        seeder.flush()
        radio(RadioScheduleService(sf), seeder, session)

        counts = {table: session.scalar(text(f"SELECT count(*) FROM {table}")) for table in _TABLES}
    print("Seeded:", ", ".join(f"{t}={n}" for t, n in counts.items() if n))
    return 0


if __name__ == "__main__":
    sys.exit(main())
