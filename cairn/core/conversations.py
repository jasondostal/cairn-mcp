"""Conversation persistence for the chat UI."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from cairn.storage.database import Database

if TYPE_CHECKING:
    from cairn.llm.interface import LLMInterface

logger = logging.getLogger(__name__)


class ConversationManager:
    """CRUD for chat conversations and their messages."""

    def __init__(self, db: Database, llm: LLMInterface | None = None):
        self.db = db
        self.llm = llm

    def create(
        self,
        project: str | None = None,
        title: str | None = None,
        model: str | None = None,
        metadata: dict | None = None,
    ) -> dict:
        row = self.db.execute_one(
            """INSERT INTO conversations (title, project, model, metadata)
               VALUES (%s, %s, %s, %s)
               RETURNING id, title, project, model, message_count,
                         metadata, created_at, updated_at""",
            (title, project, model, metadata or {}),
        )
        self.db.commit()
        return row

    def list(
        self,
        project: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        conditions = []
        params: list = []

        if project:
            conditions.append("project = %s")
            params.append(project)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        total = self.db.execute_one(
            f"SELECT COUNT(*) AS count FROM conversations {where}", params,
        )["count"]

        items = self.db.execute(
            f"""SELECT id, title, project, model, message_count,
                       metadata, created_at, updated_at
                FROM conversations {where}
                ORDER BY updated_at DESC
                LIMIT %s OFFSET %s""",
            params + [limit, offset],
        )

        return {"total": total, "limit": limit, "offset": offset, "items": items}

    def get(self, conversation_id: int) -> dict | None:
        return self.db.execute_one(
            """SELECT id, title, project, model, message_count,
                      metadata, created_at, updated_at
               FROM conversations WHERE id = %s""",
            (conversation_id,),
        )

    def update_title(self, conversation_id: int, title: str) -> dict | None:
        row = self.db.execute_one(
            """UPDATE conversations SET title = %s, updated_at = NOW()
               WHERE id = %s
               RETURNING id, title, project, model, message_count,
                         metadata, created_at, updated_at""",
            (title, conversation_id),
        )
        self.db.commit()
        return row

    def delete(self, conversation_id: int) -> bool:
        result = self.db.execute(
            "DELETE FROM conversations WHERE id = %s RETURNING id",
            (conversation_id,),
        )
        self.db.commit()
        return len(result) > 0

    # --- Messages ---

    def add_message(
        self,
        conversation_id: int,
        role: str,
        content: str | None = None,
        tool_calls: list[dict] | None = None,
        model: str | None = None,
        token_count: int | None = None,
    ) -> dict:
        row = self.db.execute_one(
            """INSERT INTO chat_messages
                   (conversation_id, role, content, tool_calls, model, token_count)
               VALUES (%s, %s, %s, %s, %s, %s)
               RETURNING id, conversation_id, role, content, tool_calls,
                         model, token_count, created_at""",
            (conversation_id, role, content, tool_calls, model, token_count),
        )
        # Update conversation metadata
        self.db.execute(
            """UPDATE conversations
               SET message_count = message_count + 1,
                   updated_at = NOW(),
                   model = COALESCE(%s, model)
               WHERE id = %s""",
            (model, conversation_id),
        )
        self.db.commit()
        return row

    def get_messages(
        self,
        conversation_id: int,
        limit: int = 200,
        offset: int = 0,
    ) -> list[dict]:
        return self.db.execute(
            """SELECT id, conversation_id, role, content, tool_calls,
                      model, token_count, created_at
               FROM chat_messages
               WHERE conversation_id = %s
               ORDER BY created_at ASC
               LIMIT %s OFFSET %s""",
            (conversation_id, limit, offset),
        )

    # --- Auto-title ---

    def auto_title(self, conversation_id: int) -> str | None:
        """Generate a title from the first user message using the LLM."""
        conv = self.get(conversation_id)
        if not conv or conv.get("title"):
            return conv.get("title") if conv else None

        messages = self.get_messages(conversation_id, limit=2)
        first_user = next((m for m in messages if m["role"] == "user"), None)
        if not first_user or not first_user.get("content"):
            return None

        user_text = first_user["content"][:500]

        # If no LLM, use first 60 chars of user message
        if not self.llm:
            title = user_text[:60].strip()
            if len(user_text) > 60:
                title += "..."
            self.update_title(conversation_id, title)
            return title

        try:
            title = self.llm.generate(
                [
                    {"role": "system", "content": "Generate a short title (max 8 words) for this conversation. Return only the title, no quotes."},
                    {"role": "user", "content": user_text},
                ],
                max_tokens=30,
            ).strip().strip('"').strip("'")
            if title:
                self.update_title(conversation_id, title[:200])
                return title[:200]
        except Exception:
            logger.warning("Auto-title generation failed", exc_info=True)

        # Fallback
        title = user_text[:60].strip()
        if len(user_text) > 60:
            title += "..."
        self.update_title(conversation_id, title)
        return title
