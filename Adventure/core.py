"""Core engine objects for the text adventure runtime.

This module defines the world model (`Location`, `Interactable`, `Item`),
player state (`Player`), and command-processing game loop (`Game`).
"""


class Location:
    """
    Locations are places the player can occupy.
    They link to other locations and contain interactables.
    """

    def __init__(self, name, description):
        self.name = name
        self.description = description
        self.exits = {}
        self.interactables = []

    def __str__(self):
        return self.name

    def connect(self, direction, other_location, back_direction=None):
        """Connect this location to another via a direction.
        If `back_direction` is provided, also creates the reverse connection.
        """
        self.exits[direction] = other_location
        if back_direction:
            other_location.exits[back_direction] = self

    def add_interactable(self, interactable):
        """Place an interactable object in this location."""
        self.interactables.append(interactable)
        interactable.location = self

    def remove_interactable(self, interactable):
        """Remove an interactable object from this location."""
        self.interactables.remove(interactable)
        interactable.location = None

    def get_interactable(self, name):
        """Return the first interactable matching `name`, or None."""
        lowered = name.lower()
        for interactable in self.interactables:
            if interactable.matches(lowered):
                return interactable
        return None

    def look(self):
        """Render a human-readable description of this location."""
        lines = [self.description]
        if self.exits:
            exits = ", ".join(sorted(self.exits.keys()))
            lines.append(f"Exits: {exits}")
        if self.interactables:
            names = ", ".join(obj.name for obj in self.interactables)
            lines.append(f"You notice: {names}")
        return "\n".join(lines)


class Interactable:
    """Base type for objects the player can examine and act on."""

    def __init__(self, name, description, aliases=None):
        self.name = name
        self.description = description
        self.aliases = set(a.lower() for a in (aliases or []))
        self.location = None

    def matches(self, text):
        """Return True when text matches the primary name or an alias."""
        lowered = text.lower()
        return lowered == self.name.lower() or lowered in self.aliases

    def actions(self, game, player):
        """List action verbs currently available for this object."""
        return []

    def look(self, game, player):
        """Describe this object and include context-aware actions."""
        available = self.actions(game, player)
        if available:
            return f"{self.description}\nPossible actions: {', '.join(available)}"
        return self.description

    def act(self, verb, game, player, target=None):
        """Handle an action verb directed at this object."""
        return f"You can't {verb} the {self.name}."


class Item(Interactable):
    """Simple takeable interactable that moves into player inventory."""

    def __init__(self, name, description, aliases=None):
        super().__init__(name, description, aliases=aliases)
        self.taken = False

    def actions(self, game, player):
        if self.taken:
            return []
        return ["take", "look"]

    def act(self, verb, game, player, target=None):
        if verb == "take":
            if self.taken:
                return f"You already took the {self.name}."
            self.taken = True
            player.inventory.add(self.name.lower())
            self.location.remove_interactable(self)
            return f"You take the {self.name}."
        return super().act(verb, game, player, target=target)


class Player:
    """Player state: current location and inventory."""

    def __init__(self, starting_location):
        self.current_location = starting_location
        self.inventory = set()

    def move(self, direction):
        next_location = self.current_location.exits.get(direction)
        if not next_location:
            return "You can't go that way."
        self.current_location = next_location
        return f"You move {direction}.\n{self.current_location.look()}"

    def inventory_text(self):
        if not self.inventory:
            return "Your inventory is empty."
        return "You carry: " + ", ".join(sorted(self.inventory))


class Game:
    """Command parser and runtime loop for a world built by `world_builder`.

    `world_builder` must return a dict with:
    - "start": starting `Location`
    - "is_win": callable accepting `Player` and returning bool
    - optional "win_message": custom message shown on victory
    """

    DIRECTION_ALIASES = {
        "n": "north",
        "s": "south",
        "e": "east",
        "w": "west",
        "north": "north",
        "south": "south",
        "east": "east",
        "west": "west",
    }

    def __init__(self, world_builder, title="Questing Board Adventure"):
        self.running = True
        self.won = False
        self.title = title
        world = world_builder()
        self.player = Player(world["start"])
        self.win_condition = world["is_win"]
        self.win_message = world.get("win_message", "You win!")

    def _find_local_interactable(self, name):
        """Find an interactable in the player's current location."""
        return self.player.current_location.get_interactable(name)

    def _find_local_or_inventory(self, name):
        """Resolve a name to a local object or an inventory item string."""
        local = self._find_local_interactable(name)
        if local:
            return local
        lowered = name.lower()
        if lowered in self.player.inventory:
            return lowered
        for item_name in self.player.inventory:
            parts = item_name.split()
            if lowered in parts or lowered == item_name.replace(" ", ""):
                return item_name
        return None

    def _check_win(self):
        """Evaluate and apply win state. Returns True when won."""
        if self.win_condition(self.player):
            self.won = True
            self.running = False
            return True
        return False

    def handle_command(self, raw_command):
        """Parse and execute one user command, returning response text."""
        command = raw_command.strip()
        if not command:
            return "Enter a command."

        words = command.lower().split()
        verb = words[0]

        if verb in {"quit", "exit"}:
            self.running = False
            return "Goodbye."

        if verb in {"look", "l"}:
            if len(words) == 1:
                return self.player.current_location.look()
            name = " ".join(words[1:])
            obj = self._find_local_interactable(name)
            if not obj:
                return f"There is no '{name}' here."
            return obj.look(self, self.player)

        if verb in {"move", "go", "walk"}:
            if len(words) < 2:
                return "Move where? Try: go north"
            direction = self.DIRECTION_ALIASES.get(words[1], words[1])
            result = self.player.move(direction)
            if self._check_win():
                return result + f"\n\n{self.win_message}"
            return result

        if verb in {"inventory", "inv", "i"}:
            return self.player.inventory_text()

        if verb in {"take", "get", "grab"}:
            if len(words) < 2:
                return "Take what?"
            name = " ".join(words[1:])
            obj = self._find_local_interactable(name)
            if not obj:
                return f"There is no '{name}' here."
            return obj.act("take", self, self.player)

        if verb == "actions":
            if len(words) < 2:
                return "Actions for what?"
            name = " ".join(words[1:])
            obj = self._find_local_interactable(name)
            if not obj:
                return f"There is no '{name}' here."
            available = obj.actions(self, self.player)
            if not available:
                return f"There are no obvious actions for the {obj.name}."
            return f"{obj.name}: " + ", ".join(available)

        if verb in {"use", "unlock", "open"}:
            if len(words) < 2:
                return f"{verb.capitalize()} what?"

            if verb == "use" and "on" in words:
                on_index = words.index("on")
                item_name = " ".join(words[1:on_index])
                target_name = " ".join(words[on_index + 1 :])
                if not item_name or not target_name:
                    return "Use syntax: use <item> on <target>"
                item = self._find_local_or_inventory(item_name)
                if not item:
                    return f"You don't have '{item_name}'."
                target_obj = self._find_local_interactable(target_name)
                if not target_obj:
                    return f"There is no '{target_name}' here."
                if isinstance(item, str):
                    return target_obj.act("use", self, self.player, target=item)
                return target_obj.act("use", self, self.player, target=item.name)

            target_name = " ".join(words[1:])
            target_obj = self._find_local_interactable(target_name)
            if not target_obj:
                return f"There is no '{target_name}' here."
            return target_obj.act(verb, self, self.player)

        if verb == "help":
            return (
                "Commands: look, look <thing>, go <direction>, take <thing>, "
                "actions <thing>, use <item> on <thing>, inventory, quit"
            )

        return "I don't understand that command. Type 'help' for options."

    def repl(self):
        """Run the interactive read-eval-print game loop."""
        print(self.title)
        print("Type 'help' for commands.\n")
        print(self.player.current_location.look())
        while self.running:
            command = input("\n> ")
            response = self.handle_command(command)
            print(response)
