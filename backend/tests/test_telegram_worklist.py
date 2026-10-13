from types import SimpleNamespace

from mcm.decide import DecideItem
from mcm.telegram_worklist import WorklistService


class Store:
    def active(self, chat_id: str) -> bool:
        return False


class Decide:
    def queue(self) -> list[DecideItem]:
        return [
            DecideItem(
                id=17,
                artist="Autechre",
                title="Amber",
                reason="Not listened yet.",
                has_art=False,
                spotify_id="album-id",
                album_type="album",
            )
        ]


class Imports:
    def pending(self) -> list[object]:
        return []


class Crates:
    def view(self, box_id: None) -> object:
        return SimpleNamespace(records=[], children=[])


def test_spotify_card_includes_direct_album_link() -> None:
    service = WorklistService(store=Store(), decide=Decide(), imports=Imports(), crates=Crates())  # type: ignore[arg-type]

    card = service.next("-100123")

    assert card is not None
    assert card.task_type == "decide"
    assert "https://open.spotify.com/album/album-id" in card.text
    assert [button.action for button in card.buttons] == ["keep", "drop", "snooze"]
