"""Cloud document models — re-exports for Beanie init."""

from __future__ import annotations

from ee.cloud.models.agent import Agent, AgentConfig
from ee.cloud.models.comment import Comment, CommentAuthor, CommentTarget
from ee.cloud.models.file import FileObj
from ee.cloud.models.group import Group, GroupAgent
from ee.cloud.models.invite import Invite
from ee.cloud.models.message import Attachment, Mention, Message, Reaction
from ee.cloud.models.notification import Notification, NotificationSource
from ee.cloud.models.pocket import Pocket, Widget, WidgetPosition
from ee.cloud.models.session import Session
from ee.cloud.models.user import OAuthAccount, User, WorkspaceMembership
from ee.cloud.models.workspace import Workspace, WorkspaceSettings

__all__ = [
    "Agent",
    "AgentConfig",
    "Attachment",
    "Comment",
    "CommentAuthor",
    "CommentTarget",
    "FileObj",
    "FileUpload",
    "Group",
    "GroupAgent",
    "Invite",
    "Mention",
    "Message",
    "Notification",
    "NotificationSource",
    "OAuthAccount",
    "Pocket",
    "Reaction",
    "Session",
    "User",
    "Widget",
    "WidgetPosition",
    "Workspace",
    "WorkspaceMembership",
    "WorkspaceSettings",
]

_ALL_DOCUMENTS_CACHE = None


def get_all_documents():
    """Lazy load ALL_DOCUMENTS to avoid circular imports."""
    global _ALL_DOCUMENTS_CACHE
    if _ALL_DOCUMENTS_CACHE is not None:
        return _ALL_DOCUMENTS_CACHE

    from ee.cloud.uploads.models import FileUpload

    _ALL_DOCUMENTS_CACHE = [
        User,
        Agent,
        Pocket,
        Session,
        Comment,
        Notification,
        FileObj,
        FileUpload,
        Workspace,
        Invite,
        Group,
        Message,
    ]
    return _ALL_DOCUMENTS_CACHE


# For backward compatibility, expose as property that auto-calls get_all_documents()
class _AllDocumentsProxy(list):
    """Proxy that lazily loads ALL_DOCUMENTS."""

    def __init__(self):
        super().__init__()
        self._loaded = False

    def _ensure_loaded(self):
        if not self._loaded:
            docs = get_all_documents()
            self.clear()
            self.extend(docs)
            self._loaded = True

    def __getitem__(self, index):
        self._ensure_loaded()
        return super().__getitem__(index)

    def __iter__(self):
        self._ensure_loaded()
        return super().__iter__()

    def __len__(self):
        self._ensure_loaded()
        return super().__len__()

    def __contains__(self, item):
        self._ensure_loaded()
        return super().__contains__(item)


ALL_DOCUMENTS = _AllDocumentsProxy()
