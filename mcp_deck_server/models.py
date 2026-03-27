from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class DeckBaseModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class Owner(DeckBaseModel):
    id: int | str | None = None
    displayname: str | None = None
    type: str | int | None = None
    primaryKey: str | None = None
    uid: str | None = None


class Label(DeckBaseModel):
    id: int | None = None
    title: str | None = None
    color: str | None = None
    archived: bool | None = None
    boardId: int | None = None
    cardId: int | None = None
    lastModified: int | None = None
    ETag: str | None = None


class Card(DeckBaseModel):
    id: int | None = None
    title: str | None = None
    description: str | None = None
    duedate: str | None = None
    type: str | int | None = None
    owner: Owner | str | None = None
    labels: list[Label] | None = None
    archived: bool | None = None
    order: int | None = None
    stackId: int | None = None
    lastModified: int | None = None
    lastEditor: Owner | str | None = None
    createdAt: int | None = None
    assignedUsers: list[Owner] | None = None
    attachments: list[Any] | None = None
    attachmentCount: int | None = None
    done: bool | None = None
    deletedAt: int | None = None
    commentsUnread: int | None = None
    commentsCount: int | None = None
    ETag: str | None = None
    overdue: int | None = None
    referenceData: Any | None = None


class Stack(DeckBaseModel):
    id: int | None = None
    title: str | None = None
    cards: list[Card] | None = None
    order: int | None = None
    boardId: int | None = None
    deletedAt: int | None = None
    lastModified: int | None = None
    ETag: str | None = None


class Board(DeckBaseModel):
    id: int | None = None
    title: str | None = None
    stacks: list[Stack] | None = None
    color: str | None = None
    archived: bool | None = None
    labels: list[Label] | None = None
    acl: list[Any] | None = None
    permissions: dict[str, Any] | None = None
    users: list[Owner] | None = None
    shared: int | None = None
    activeSessions: list[Any] | None = None
    deletedAt: int | None = None
    lastModified: int | None = None
    settings: list[Any] | dict[str, Any] | None = None
    ETag: str | None = None
    owner: Owner | None = None
