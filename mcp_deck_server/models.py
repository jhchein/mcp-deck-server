from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel


class Owner(BaseModel):
    id: Optional[Union[int, str]] = None
    displayName: Optional[str] = None
    type: Optional[Union[str, int]] = None
    primaryKey: Optional[str] = None
    uid: Optional[str] = None


class Label(BaseModel):
    id: Optional[int] = None
    title: Optional[str] = None
    color: Optional[str] = None
    archived: Optional[bool] = None
    boardId: Optional[int] = None
    cardId: Optional[int] = None
    lastModified: Optional[int] = None
    ETag: Optional[str] = None


class Card(BaseModel):
    id: Optional[int] = None
    title: Optional[str] = None
    description: Optional[str] = None
    duedate: Optional[str] = None
    type: Optional[Union[str, int]] = None
    owner: Optional[Union[Owner, str]] = None
    labels: Optional[List[Label]] = None
    archived: Optional[bool] = None
    order: Optional[int] = None
    stackId: Optional[int] = None
    lastModified: Optional[int] = None
    lastEditor: Optional[Owner] = None
    createdAt: Optional[int] = None
    assignedUsers: Optional[List[Owner]] = None
    attachments: Optional[List[Any]] = None
    attachmentCount: Optional[int] = None
    done: Optional[bool] = None
    deletedAt: Optional[int] = None
    commentsUnread: Optional[int] = None
    commentsCount: Optional[int] = None
    ETag: Optional[str] = None
    overdue: Optional[int] = None
    referenceData: Optional[Any] = None


class Stack(BaseModel):
    id: Optional[int] = None
    title: Optional[str] = None
    cards: Optional[List[Card]] = None
    order: Optional[int] = None
    boardId: Optional[int] = None
    deletedAt: Optional[int] = None
    lastModified: Optional[int] = None
    ETag: Optional[str] = None


class Board(BaseModel):
    id: Optional[int] = None
    title: Optional[str] = None
    stacks: Optional[List[Stack]] = None
    color: Optional[str] = None
    archived: Optional[bool] = None
    labels: Optional[List[Label]] = None
    acl: Optional[List[Any]] = None
    permissions: Optional[Dict[str, Any]] = None
    users: Optional[List[Owner]] = None
    shared: Optional[int] = None
    activeSessions: Optional[List[Any]] = None
    deletedAt: Optional[int] = None
    lastModified: Optional[int] = None
    settings: Optional[List[Any]] = None
    ETag: Optional[str] = None
    owner: Optional[Owner] = None
