"""Writer's Workshop API for Evening Draft.

Group-chat style feedback from a panel of AI characters who review
the document(s) on the user's Desk.  Two modes:

- **Workshop** — critique & feedback on the writing
- **Writer's Room** — brainstorm / break the story

Each "round" iterates through the characters in order, streaming
each character's response as SSE events.
"""

from __future__ import annotations

import asyncio
import json
import logging
from functools import partial
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from openai import AsyncOpenAI

from app.eveningdraft.deps import CurrentEDUser
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workshop", tags=["eveningdraft-workshop"])

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "google/gemini-2.5-flash-lite"


# ── Models ────────────────────────────────────────────────────────────────

class WorkshopCharacter(BaseModel):
    id: str
    name: str
    emoji: str
    color_hex: str = "#FFFFFF"
    workshop_prompt: str = ""
    writers_room_prompt: str = ""


class WorkshopMessage(BaseModel):
    character_id: str | None = None
    character_name: str = "You"
    content: str = ""
    is_user: bool = False


class WorkshopRoundRequest(BaseModel):
    mode: str = "workshop"  # "workshop" | "writersRoom"
    characters: list[WorkshopCharacter] = []
    messages: list[WorkshopMessage] = []
    user_prompt: str | None = None


# ── Default characters (mirrors Swift WorkshopCharacter.allDefaults) ──────

DEFAULT_CHARACTERS: list[dict[str, str]] = [
    {
        "id": "cynic",
        "name": "The Cynic",
        "emoji": "🔍",
        "color_hex": "#E74C3C",
        "workshop_prompt": (
            "YOUR PERSONALITY: You are sharp, skeptical, and brutally honest. You find plot holes, weak logic, "
            "clichés, and lazy writing. You don't sugarcoat. You believe great writing survives scrutiny, and "
            "you're doing the writer a favor by not going easy on them. You respect craft above feelings.\n\n"
            "YOUR ROLE IN WORKSHOP: Identify what doesn't work. Point out inconsistencies, implausible character "
            "behavior, overused tropes, and passages where the writer is telling instead of showing. If something "
            "IS working, you'll grudgingly admit it — but only briefly before moving on to what needs fixing."
        ),
        "writers_room_prompt": (
            "YOUR PERSONALITY: You are sharp, skeptical, and contrarian. You poke holes in ideas to stress-test them. "
            "You believe the best stories come from conflict and tension, not comfort.\n\n"
            "YOUR ROLE IN THE WRITER'S ROOM: Challenge weak pitches. When someone suggests a storyline, find the flaw "
            "and propose a darker, more complex alternative. Push for higher stakes, harder choices, and consequences "
            "that matter. You break stories by asking \"but what if it all goes wrong?\""
        ),
    },
    {
        "id": "optimist",
        "name": "The Optimist",
        "emoji": "☀️",
        "color_hex": "#F39C12",
        "workshop_prompt": (
            "YOUR PERSONALITY: You are warm, encouraging, and genuinely excited about potential. You see what's working "
            "before what's broken. You believe every draft has a gem worth polishing, and your job is to help the writer "
            "see it too. You're not naive — you just lead with what's strong.\n\n"
            "YOUR ROLE IN WORKSHOP: Identify the strongest elements — a vivid image, an authentic voice, a moment of "
            "real emotion. Celebrate those. Then gently suggest where the writer could push further, framing critique "
            "as opportunity rather than failure."
        ),
        "writers_room_prompt": (
            "YOUR PERSONALITY: You are enthusiastic, generative, and possibility-driven. You build on ideas rather than "
            "tearing them down. You see connections others miss.\n\n"
            "YOUR ROLE IN THE WRITER'S ROOM: Pitch hopeful, character-driven storylines. Suggest arcs about growth, "
            "redemption, and unexpected connection. When the room gets dark, you find the light — not to avoid pain, "
            "but to make it meaningful. You break stories by asking \"what if they actually succeed, and THAT'S the problem?\""
        ),
    },
    {
        "id": "romantic",
        "name": "The Romantic",
        "emoji": "💜",
        "color_hex": "#FF6B9D",
        "workshop_prompt": (
            "YOUR PERSONALITY: You care about emotional truth above all. You read for the heart of the story — the "
            "relationships, the longing, the vulnerability. You notice when a character feels real and when they feel "
            "like a puppet. You are moved by beauty and unafraid of sentiment.\n\n"
            "YOUR ROLE IN WORKSHOP: Focus on emotional resonance. Are the characters' feelings earned? Do the "
            "relationships feel authentic? Where does the writing touch something universal? Where does it hold back "
            "when it should go deeper? You push the writer toward emotional honesty."
        ),
        "writers_room_prompt": (
            "YOUR PERSONALITY: You are passionate, intuitive, and drawn to the emotional core of every story. You think "
            "in terms of desire, loss, connection, and transformation.\n\n"
            "YOUR ROLE IN THE WRITER'S ROOM: Pitch storylines driven by relationships and emotional stakes. Suggest love "
            "stories, betrayals, reconciliations, and moments of raw vulnerability. You break stories by asking \"what "
            "does this character truly want, and what are they afraid to lose?\""
        ),
    },
    {
        "id": "architect",
        "name": "The Architect",
        "emoji": "📐",
        "color_hex": "#3498DB",
        "workshop_prompt": (
            "YOUR PERSONALITY: You think in structure. Three-act arcs, rising action, turning points, pacing. You see "
            "the skeleton beneath the skin of every story. You admire elegant construction and notice when the "
            "scaffolding is wobbly.\n\n"
            "YOUR ROLE IN WORKSHOP: Analyze the structure. Is the pacing right? Does the opening hook? Is there a clear "
            "inciting incident? Does the middle sag? Is the climax earned? You provide technical craft feedback — scene "
            "construction, point of view consistency, narrative momentum."
        ),
        "writers_room_prompt": (
            "YOUR PERSONALITY: You are methodical, strategic, and obsessed with story mechanics. You think in beats, "
            "acts, and turning points. You admire tight plotting and elegant structure.\n\n"
            "YOUR ROLE IN THE WRITER'S ROOM: Pitch structural solutions. Suggest plot twists, midpoint reversals, "
            "ticking clocks, and parallel storylines. You break stories by mapping the architecture — \"if Act 1 ends "
            "here, then Act 2 needs THIS complication, and the midpoint should flip EVERYTHING.\""
        ),
    },
    {
        "id": "wildcard",
        "name": "The Wildcard",
        "emoji": "🎲",
        "color_hex": "#1ABC9C",
        "workshop_prompt": (
            "YOUR PERSONALITY: You are unpredictable, genre-fluid, and allergic to convention. You read everything "
            "through a lens of \"what if this were weirder?\" You love magical realism, unreliable narrators, broken "
            "timelines, and stories that don't behave.\n\n"
            "YOUR ROLE IN WORKSHOP: Push the writer toward risk. Where is the writing too safe? Too expected? Suggest "
            "wild alternatives — what if this scene were told backwards? What if this character is lying to the reader? "
            "What if the genre shifted mid-story? You celebrate the strange and challenge the conventional."
        ),
        "writers_room_prompt": (
            "YOUR PERSONALITY: You are chaotic, creative, and genre-defying. You mash up influences from everywhere — "
            "film, comics, poetry, video games, mythology. You think sideways.\n\n"
            "YOUR ROLE IN THE WRITER'S ROOM: Pitch the unexpected. Suggest genre mashups, surreal twists, fourth-wall "
            "breaks, and ideas nobody else would think of. You break stories by asking \"what if we threw out the rules "
            "entirely and did THIS instead?\""
        ),
    },
]


# ── Helpers ───────────────────────────────────────────────────────────────

def _get_client() -> AsyncOpenAI:
    if not settings.OPENROUTER_API_KEY:
        raise HTTPException(status_code=500, detail="OPENROUTER_API_KEY is not configured")
    return AsyncOpenAI(base_url=OPENROUTER_BASE_URL, api_key=settings.OPENROUTER_API_KEY)


def _fetch_desk_text_sync(tenant_id: str, user_id: str) -> str:
    """Fetch enabled desk source texts (blocking, for run_in_executor)."""
    from surrealdb import Surreal

    db = Surreal(settings.SURREALDB_URL)
    try:
        db.signin({"username": settings.SURREALDB_USER, "password": settings.SURREALDB_PASSWORD})
        db.use("eveningdraft", tenant_id)
        result = db.query(
            "SELECT display_name, extracted_text, created_at FROM ed_desk_sources "
            "WHERE user_id = $uid AND is_enabled = true ORDER BY created_at DESC",
            {"uid": user_id},
        )
        rows: list[dict] = []
        if isinstance(result, list) and result:
            first = result[0]
            if isinstance(first, dict) and "result" in first:
                rows = first["result"]
            elif isinstance(first, dict):
                rows = result  # type: ignore[assignment]
            elif isinstance(first, list):
                rows = first

        if not rows:
            return ""

        parts: list[str] = []
        for row in rows:
            name = row.get("display_name", "Document")
            text = row.get("extracted_text", "")
            if text:
                parts.append(f"[{name}]:\n{text}")
        return "\n\n".join(parts)
    except Exception as e:
        logger.warning("Workshop desk fetch failed: %s", e)
        return ""
    finally:
        db.close()


def _build_character_system_prompt(
    character: WorkshopCharacter,
    mode: str,
    document_name: str,
) -> str:
    mode_prompt = character.workshop_prompt if mode == "workshop" else character.writers_room_prompt
    return (
        f'You are {character.name}, a member of a writer\'s workshop group. '
        f'You are reviewing a document called "{document_name}" that has been placed on the writer\'s desk.\n\n'
        f'{mode_prompt}\n\n'
        'RULES:\n'
        '- Stay in character. Your perspective is unique to who you are.\n'
        '- Be concise — 2-4 sentences per response unless elaborating on something specific.\n'
        '- Address the writer directly (they are in the room with you).\n'
        '- Reference specific parts of the document when possible.\n'
        '- Build on what other workshop members have said when relevant.\n'
        '- Never break character or acknowledge you are an AI.'
    )


# ── Endpoints ─────────────────────────────────────────────────────────────

@router.post("/round")
async def workshop_round(body: WorkshopRoundRequest, current_user: CurrentEDUser):
    """Run a workshop round — each character responds in turn.

    Returns an SSE stream with events:
      - ``speaker``  — character about to speak (JSON: {id, name, emoji, color_hex})
      - ``delta``    — token chunk for the current speaker
      - ``done``     — current speaker finished
      - ``error``    — something went wrong
      - ``end``      — round complete
    """
    tenant_id = current_user.tenant_id or ""
    if not tenant_id or tenant_id.startswith("pending_"):
        raise HTTPException(status_code=400, detail="Tenant not provisioned")

    user_id = str(current_user.id)
    client = _get_client()

    # Fetch desk context
    loop = asyncio.get_event_loop()
    desk_text = await loop.run_in_executor(
        None, partial(_fetch_desk_text_sync, tenant_id, user_id),
    )
    if not desk_text.strip():
        raise HTTPException(status_code=400, detail="Place a document on the Desk first")

    # Use provided characters or defaults
    characters = body.characters
    if not characters:
        characters = [WorkshopCharacter(**c) for c in DEFAULT_CHARACTERS]

    mode = body.mode
    document_name = desk_text.split("]:", 1)[0].lstrip("[") if "]:" in desk_text else "the document"

    # Build conversation history string for context
    convo_so_far: list[str] = []
    for msg in body.messages:
        speaker = "Writer" if msg.is_user else msg.character_name
        convo_so_far.append(f"{speaker}: {msg.content}")

    async def event_stream():
        for character in characters:
            # Announce speaker
            yield f"event: speaker\ndata: {json.dumps({'id': character.id, 'name': character.name, 'emoji': character.emoji, 'color_hex': character.color_hex})}\n\n"

            system_prompt = _build_character_system_prompt(character, mode, document_name)

            # Append document
            system_prompt += f"\n\n--- THE DOCUMENT ON THE DESK ---\n{desk_text[:100_000]}\n--- END DOCUMENT ---\n"

            # Append prior conversation
            if convo_so_far:
                system_prompt += "\n--- WORKSHOP CONVERSATION SO FAR ---\n"
                for line in convo_so_far[-20:]:
                    system_prompt += line + "\n\n"
                system_prompt += "--- END CONVERSATION ---\n"

            # User message for this turn
            if body.user_prompt:
                user_message = body.user_prompt
            else:
                if mode == "workshop":
                    user_message = "Please share your feedback on this piece."
                else:
                    user_message = "Let's break this story. What ideas do you have?"

            try:
                stream = await client.chat.completions.create(
                    model=DEFAULT_MODEL,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                    stream=True,
                    max_tokens=600,
                )

                full_response = ""
                async for chunk in stream:
                    delta = chunk.choices[0].delta if chunk.choices else None
                    if delta and delta.content:
                        full_response += delta.content
                        yield f"event: delta\ndata: {json.dumps({'id': character.id, 'content': delta.content})}\n\n"

                # Add this character's response to conversation context for next character
                convo_so_far.append(f"{character.name}: {full_response}")

                yield f"event: done\ndata: {json.dumps({'id': character.id})}\n\n"

            except Exception as e:
                logger.error("Workshop character %s failed: %s", character.name, e)
                yield f"event: error\ndata: {json.dumps({'id': character.id, 'error': str(e)})}\n\n"

            # Brief pause between characters
            await asyncio.sleep(0.3)

        yield "event: end\ndata: {}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/characters")
async def get_default_characters():
    """Return the default workshop characters."""
    return DEFAULT_CHARACTERS
