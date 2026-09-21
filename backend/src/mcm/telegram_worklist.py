"""An opt-in, one-card-at-a-time Telegram front end to MCM's existing work queues."""

import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, cast

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .crates import CrateService
from .decide import DecideItem, DecideService
from .imports import ImportItem, ImportsService
from .models import TelegramWorklistOffer, TelegramWorklistState

log = logging.getLogger(__name__)

TaskType = Literal["decide", "import", "crate"]


@dataclass(frozen=True)
class Button:
    text: str
    action: str


@dataclass(frozen=True)
class Card:
    task_type: TaskType
    resource_id: str
    text: str
    buttons: list[Button]


class WorklistStore:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sf = session_factory

    def offset(self) -> int:
        with self._sf() as session:
            row = session.get(TelegramWorklistState, 1)
            return row.update_offset if row else 0

    def advance_offset(self, offset: int) -> None:
        with self._sf() as session:
            row = session.get(TelegramWorklistState, 1)
            if row is None:
                session.add(TelegramWorklistState(id=1, update_offset=offset))
            elif offset > row.update_offset:
                row.update_offset = offset
            session.commit()

    def active(self, chat_id: str) -> bool:
        with self._sf() as session:
            return (
                session.scalar(
                    select(TelegramWorklistOffer.token).where(
                        TelegramWorklistOffer.chat_id == chat_id,
                        TelegramWorklistOffer.completed_at.is_(None),
                    )
                )
                is not None
            )

    def create(self, chat_id: str, card: Card) -> str:
        token = secrets.token_urlsafe(18)
        with self._sf() as session:
            session.add(
                TelegramWorklistOffer(
                    token=token,
                    chat_id=chat_id,
                    task_type=card.task_type,
                    resource_id=card.resource_id,
                )
            )
            session.commit()
        return token

    def consume(self, chat_id: str, token: str) -> TelegramWorklistOffer | None:
        """Claim exactly one active offer. Duplicate and old callback buttons cannot win."""
        with self._sf() as session:
            row = session.get(TelegramWorklistOffer, token)
            if row is None or row.chat_id != chat_id or row.completed_at is not None:
                return None
            row.completed_at = datetime.now(UTC)
            session.commit()
            return row


class WorklistService:
    """Picks categories uniformly, then acts through the services that own the real data."""

    def __init__(
        self,
        *,
        store: WorklistStore,
        decide: DecideService,
        imports: ImportsService,
        crates: CrateService,
    ) -> None:
        self._store = store
        self._decide = decide
        self._imports = imports
        self._crates = crates

    def next(self, chat_id: str) -> Card | None:
        if self._store.active(chat_id):
            return None
        cards = [self._decide_card(), self._import_card(), self._crate_card()]
        available = [card for card in cards if card is not None]
        if not available:
            return None
        # Token randomness makes the category selection independent of queue ordering while
        # retaining an exactly equal chance for every currently eligible category.
        return available[secrets.randbelow(len(available))]

    def offer(self, chat_id: str) -> tuple[Card | None, str | None]:
        card = self.next(chat_id)
        return (card, self._store.create(chat_id, card)) if card else (None, None)

    def act(self, chat_id: str, token: str, action: str) -> bool:
        offer = self._store.consume(chat_id, token)
        if offer is None:
            return False
        if offer.task_type == "decide" and action in {"keep", "drop", "snooze"}:
            album_id = int(offer.resource_id)
            if album_id not in {item.id for item in self._decide.queue()}:
                return False
            if action == "keep":
                self._decide.keep(album_id)
            elif action == "drop":
                self._decide.drop(album_id)
            else:
                self._decide.snooze(album_id)
            return True
        if offer.task_type == "import" and action in {"import", "discard"}:
            import_id = int(offer.resource_id)
            if import_id not in {item.id for item in self._imports.pending()}:
                return False
            if action == "import":
                self._imports.enqueue(import_id)
            else:
                self._imports.discard(import_id)
            return True
        if offer.task_type == "crate" and action.startswith("file:"):
            box_id = int(action.removeprefix("file:"))
            root = self._crates.view(None)
            if offer.resource_id not in {record.beets_id for record in root.records}:
                return False
            if box_id not in {box.id for box in root.children}:
                return False
            self._crates.file_down(root.id, [offer.resource_id], child_box_id=box_id)
            return True
        return False

    def _decide_card(self) -> Card | None:
        items = self._decide.queue()
        if not items:
            return None
        item: DecideItem = items[0]
        spotify = (
            f"\nSpotify: https://open.spotify.com/album/{item.spotify_id}"
            if item.spotify_id
            else ""
        )
        return Card(
            "decide",
            str(item.id),
            f"Spotify save\n{item.artist} — {item.title}\n{item.reason}{spotify}",
            [Button("Want", "keep"), Button("Drop", "drop"), Button("Later", "snooze")],
        )

    def _import_card(self) -> Card | None:
        items = [
            item
            for item in self._imports.pending()
            if item.import_target != "review" and not item.missing
        ]
        if not items:
            return None
        item: ImportItem = items[0]
        matched = f"\nMatches: {item.matched}" if item.matched else ""
        return Card(
            "import",
            str(item.id),
            f"Import\n{item.name}{matched}",
            [Button("Import", "import"), Button("Discard", "discard")],
        )

    def _crate_card(self) -> Card | None:
        root = self._crates.view(None)
        if not root.records or not root.children:
            return None
        record = root.records[0]
        return Card(
            "crate",
            record.beets_id,
            f"Crate\nWhich box for {record.artist} — {record.title}?",
            [Button(box.name, f"file:{box.id}") for box in root.children],
        )


class TelegramClient:
    """Small Telegram Bot API adapter. Long polling means no webhook/callback URL to expose."""

    def __init__(self, token: str) -> None:
        self._base_url = f"https://api.telegram.org/bot{token}"

    def updates(self, offset: int) -> list[dict[str, object]]:
        try:
            with httpx.Client(timeout=35) as client:
                response = client.get(
                    f"{self._base_url}/getUpdates", params={"offset": offset, "timeout": 30}
                )
                response.raise_for_status()
                body = cast(dict[str, Any], response.json())
        except httpx.HTTPError:
            # HTTPX includes the token-bearing Bot API URL in its exception rendering.
            raise RuntimeError("Telegram getUpdates request failed") from None
        if not body.get("ok"):
            raise RuntimeError(f"Telegram getUpdates failed: {body}")
        return cast(list[dict[str, object]], body["result"])

    def send(self, chat_id: str, card: Card, token: str) -> None:
        keyboard = [
            [{"text": button.text, "callback_data": f"w:{token}:{button.action}"}]
            for button in card.buttons
        ]
        self._post(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": card.text,
                "reply_markup": {"inline_keyboard": keyboard},
            },
        )

    def message(self, chat_id: str, text: str) -> None:
        self._post("sendMessage", {"chat_id": chat_id, "text": text})

    def answer(self, callback_id: str, text: str = "") -> None:
        self._post("answerCallbackQuery", {"callback_query_id": callback_id, "text": text})

    def _post(self, method: str, payload: dict[str, object]) -> None:
        try:
            with httpx.Client(timeout=15) as client:
                response = client.post(f"{self._base_url}/{method}", json=payload)
                response.raise_for_status()
                body = cast(dict[str, Any], response.json())
        except httpx.HTTPError:
            # Do not let a worker log expose this token-bearing URL.
            raise RuntimeError(f"Telegram {method} request failed") from None
        if not body.get("ok"):
            raise RuntimeError(f"Telegram {method} failed")


class TelegramWorklistPoller:
    def __init__(
        self,
        *,
        client: TelegramClient,
        service: WorklistService,
        store: WorklistStore,
        chats: set[str],
    ) -> None:
        self._client = client
        self._service = service
        self._store = store
        self._chats = chats

    def poll(self) -> None:
        for update in self._client.updates(self._store.offset()):
            update_id = update.get("update_id")
            if not isinstance(update_id, int):
                continue
            try:
                self._handle(update)
            except Exception:
                log.exception("Telegram worklist update %s failed; it will retry", update_id)
                break
            self._store.advance_offset(update_id + 1)

    def _handle(self, update: dict[str, object]) -> None:
        message = update.get("message")
        if isinstance(message, dict):
            chat = message.get("chat")
            text = message.get("text")
            if (
                isinstance(chat, dict)
                and isinstance(chat.get("id"), int)
                and text in {"/work", "/start"}
            ):
                self._offer(str(chat["id"]))
            return
        callback = update.get("callback_query")
        if not isinstance(callback, dict) or not isinstance(callback.get("id"), str):
            return
        message = callback.get("message")
        data = callback.get("data")
        if not isinstance(message, dict) or not isinstance(data, str):
            return
        chat = message.get("chat")
        if not isinstance(chat, dict) or not isinstance(chat.get("id"), int):
            return
        chat_id = str(chat["id"])
        if chat_id not in self._chats or not data.startswith("w:"):
            return
        parts = data.split(":", 2)
        if len(parts) != 3:
            self._client.answer(callback["id"], "Invalid task button")
            return
        _, token, action = parts
        applied = self._service.act(chat_id, token, action)
        self._client.answer(callback["id"], "Done" if applied else "That task has already moved on")
        self._offer(chat_id)

    def _offer(self, chat_id: str) -> None:
        if chat_id not in self._chats:
            return
        if self._store.active(chat_id):
            self._client.message(chat_id, "You already have a worklist card above.")
            return
        card, token = self._service.offer(chat_id)
        if card is not None and token is not None:
            self._client.send(chat_id, card, token)
        elif not self._store.active(chat_id):
            self._client.message(chat_id, "Worklist clear.")
