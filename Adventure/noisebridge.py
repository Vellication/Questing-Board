"""Noisebridge-flavored world builder backed by the live NoiseQuest API.

This module translates API resources (locations, guilds, and open quests) into
Adventure engine primitives so they can be explored through the text-adventure
REPL.
"""

import json
from urllib.parse import urlencode
from urllib.request import urlopen

from core import Game, Interactable, Location


API_BASE = "https://nbquest.nthmost.net/api/v1"


def _get_json(path, params=None):
    """Fetch and decode JSON from an API path under ``API_BASE``."""
    query = ""
    if params:
        query = "?" + urlencode(params)
    url = f"{API_BASE}{path}{query}"
    with urlopen(url, timeout=20) as response:
        return json.load(response)


def _shorten(text, limit=68):
    """Trim long text for room/item descriptions while preserving readability."""
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


class InfoTerminal(Interactable):
    """Interactable that summarizes API health and economy state."""

    def __init__(self, stats, version, economy):
        super().__init__(
            name="info terminal",
            description="A terminal showing the current state of the Noisebridge quest economy.",
            aliases=["terminal", "info"],
        )
        self.stats = stats
        self.version = version
        self.economy = economy

    def actions(self, game, player):
        return ["look", "use"]

    def act(self, verb, game, player, target=None):
        if verb != "use":
            return super().act(verb, game, player, target=target)
        warnings = self.stats.get("economy_warnings") or []
        warning_text = ", ".join(warnings) if warnings else "none"
        return (
            f"API version: {self.version.get('version', 'unknown')}\n"
            f"Open quests: {self.stats.get('quests_open', 0)} / "
            f"Done quests: {self.stats.get('quests_done', 0)}\n"
            f"Total quests: {self.stats.get('quest_count', 0)} / "
            f"Users: {self.stats.get('user_count', 0)}\n"
            f"XP minted: {self.stats.get('total_xp_minted', 0)} / "
            f"XP burned: {self.stats.get('total_xp_burned', 0)}\n"
            f"Calibration: {self.stats.get('calibration_status', 'unknown')}\n"
            f"Economy warnings: {warning_text}\n"
            f"Economy config keys: {', '.join(sorted((self.economy.get('config') or {}).keys()))}"
        )


class GuildLedger(Interactable):
    """Interactable that lists known guilds and short descriptions."""

    def __init__(self, guilds):
        super().__init__(
            name="guild ledger",
            description="A worn binder listing Noisebridge guilds.",
            aliases=["guilds", "ledger"],
        )
        self.guilds = guilds

    def actions(self, game, player):
        return ["look", "use"]

    def act(self, verb, game, player, target=None):
        if verb != "use":
            return super().act(verb, game, player, target=target)
        lines = ["Guilds:"]
        for guild in self.guilds:
            summary = guild.get("description") or "No description yet."
            lines.append(f"- {guild['name']} ({guild['slug']}): {_shorten(summary, 72)}")
        return "\n".join(lines)

class QuestLedger(Interactable):
    """Interactable that lists open quests sorted by urgency."""

    def __init__(self, quests, guild_by_id, name="quest ledger", description=None):
        super().__init__(
            name=name,
            description=description or "A board listing open quests by urgency.",
            aliases=["quests", "quest list"],
        )
        self.quests = quests
        self.guild_by_id = guild_by_id

    def actions(self, game, player):
        return ["look", "use"]

    def act(self, verb, game, player, target=None):
        if verb != "use":
            return super().act(verb, game, player, target=target)
        sorted_quests = sorted(self.quests, key=lambda q: q.get("urgency", 0), reverse=True)
        lines = ["Open Quests (by urgency):"]
        if not sorted_quests:
            lines.append("  (none)")
            return "\n".join(lines)
        for q in sorted_quests:
            guild_name = self.guild_by_id.get(q.get("guild_id"), "No guild")
            lines.append(
                f"  [{q['urgency']:>2}] quest {q['id']}: {_shorten(q['title'], 50)}"
                f" ({guild_name})"
            )
        return "\n".join(lines)

class QuestInteractable(Interactable):
    """Interactable wrapper for a single open quest claim in the simulation."""

    def __init__(self, quest, guild_name, location_name):
        super().__init__(
            name=f"quest {quest['id']}",
            description=_shorten(quest["title"], 80),
            aliases=[f"q{quest['id']}"],
        )
        self.quest = quest
        self.guild_name = guild_name
        self.location_name = location_name

    def actions(self, game, player):
        token = f"quest-{self.quest['id']}"
        if token in player.inventory:
            return ["look"]
        return ["look", "use"]

    def look(self, game, player):
        q = self.quest
        details = [
            f"{q['title']}",
            f"XP: {q['xp']} | Urgency: {q['urgency']} | Status: {q['status']}",
            f"Guild: {self.guild_name} | Location: {self.location_name}",
            f"Skills: {', '.join(q['skills']) if q['skills'] else 'none'}",
            _shorten(q["description"], 180),
        ]
        token = f"quest-{q['id']}"
        if token in player.inventory:
            details.append("You have already claimed this quest in the simulation.")
        else:
            details.append("Use this quest to claim it in your simulated inventory.")
        return "\n".join(details)

    def act(self, verb, game, player, target=None):
        if verb != "use":
            return super().act(verb, game, player, target=target)
        token = f"quest-{self.quest['id']}"
        if token in player.inventory:
            return f"You already claimed quest {self.quest['id']}."
        player.inventory.add(token)
        return (
            f"You claim quest {self.quest['id']}: {self.quest['title']}\n"
            f"Earned (simulated): {self.quest['xp']} XP."
        )


def _load_open_quests(limit=80):
    """Load up to ``limit`` open quests, following API cursor pagination."""
    items = []
    cursor = None
    while len(items) < limit:
        page_size = min(50, limit - len(items))
        params = {"status": "open", "limit": page_size}
        if cursor:
            params["cursor"] = cursor
        page = _get_json("/quests", params=params)
        page_items = page.get("items") or []
        items.extend(page_items)
        cursor = page.get("next_cursor")
        if not cursor or not page_items:
            break
    return items


def build_noisebridge_world():
    """Build the world graph from live NoiseQuest API data."""
    locations = _get_json("/locations")
    guilds = _get_json("/guilds")
    stats = _get_json("/stats")
    version = _get_json("/version")
    economy = _get_json("/economy")
    quests = _load_open_quests(limit=80)

    guild_by_id = {g["id"]: g["name"] for g in guilds}
    location_data_by_id = {loc["id"]: loc for loc in locations}
    quests_by_guild_id = {}
    for quest in quests:
        guild_id = quest.get("guild_id")
        if guild_id is None:
            continue
        quests_by_guild_id.setdefault(guild_id, []).append(quest)

    quest_board = Location(
        "Quest Board",
        "NoiseQuest v1 hums to life. "
        "Travel using: go <location-slug> or go guild-<guild-slug>. "
        "Type 'help' for commands.",
    )

    location_rooms = {}
    for loc in locations:
        description = loc.get("description") or "No description available."
        room = Location(
            loc["name"],
            f"{description}\nLocation kind: {loc['kind']} | Slug: {loc['slug']}",
        )
        location_rooms[loc["id"]] = room
        quest_board.connect(loc["slug"], room, "board")

    guild_rooms = {}
    for guild in guilds:
        description = guild.get("description") or "No guild description available."
        room = Location(
            f"{guild['name']} Guild Hall",
            f"{description}\nGuild slug: {guild['slug']}",
        )
        guild_quests = quests_by_guild_id.get(guild["id"], [])
        room.add_interactable(
            QuestLedger(
                guild_quests,
                guild_by_id,
                name=f"{guild['name']} quest ledger",
                description=f"A board listing open quests for the {guild['name']} guild.",
            )
        )
        guild_rooms[guild["id"]] = room
        quest_board.connect(f"guild-{guild['slug']}", room, "board")

    quest_board.add_interactable(InfoTerminal(stats, version, economy))
    quest_board.add_interactable(GuildLedger(guilds))
    quest_board.add_interactable(QuestLedger(quests,guild_by_id))

    unassigned = 0
    for quest in quests:
        location_id = quest.get("location_id")
        if location_id in location_rooms:
            room = location_rooms[location_id]
            location_name = location_data_by_id[location_id]["name"]
        elif quest.get("guild_id") in guild_rooms:
            room = guild_rooms[quest["guild_id"]]
            location_name = "Guild Hall"
        else:
            room = quest_board
            location_name = "Unassigned"
            unassigned += 1
        guild_name = guild_by_id.get(quest.get("guild_id"), "No guild")
        room.add_interactable(QuestInteractable(quest, guild_name, location_name))

    quest_board.description += (
        f"\nLoaded {len(locations)} locations, {len(guilds)} guilds, and "
        f"{len(quests)} open quests ({unassigned} without a location assignment)."
    )

    return {
        "start": quest_board,
        "is_win": lambda player: False,
        "win_message": "",
    }


if __name__ == "__main__":
    Game(build_noisebridge_world, title="NoiseQuest v1").repl()
