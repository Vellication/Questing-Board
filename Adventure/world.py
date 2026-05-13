from core import Game, Interactable, Item, Location


class Gate(Interactable):
    def __init__(
        self,
        name,
        description,
        unlock_item,
        source_location,
        target_location,
        direction,
        aliases=None,
    ):
        super().__init__(name, description, aliases=aliases)
        self.unlock_item = unlock_item.lower()
        self.source_location = source_location
        self.target_location = target_location
        self.direction = direction
        self.unlocked = False

    def actions(self, game, player):
        if self.unlocked:
            return ["open", "use", "look"]
        if self.unlock_item in player.inventory:
            return ["unlock", "use", "look"]
        return ["look"]

    def look(self, game, player):
        if self.unlocked:
            return (
                f"{self.description} The lock hangs open.\n"
                "You can now go north through the gate."
            )
        if self.unlock_item in player.inventory:
            return (
                f"{self.description} It looks like your {self.unlock_item} could "
                "unlock it."
            )
        return f"{self.description} It is locked tight."

    def unlock(self, player):
        if self.unlocked:
            return "The gate is already unlocked."
        if self.unlock_item not in player.inventory:
            return f"You need the {self.unlock_item} to unlock the gate."
        self.unlocked = True
        self.source_location.connect(self.direction, self.target_location, "south")
        return "You unlock the gate with a heavy clunk."

    def act(self, verb, game, player, target=None):
        if verb in {"unlock", "use"}:
            if target and target.lower() != self.unlock_item:
                return f"Using {target} on the gate does nothing."
            return self.unlock(player)
        if verb == "open":
            if not self.unlocked:
                return "The gate is locked."
            return "The gate is open. You can head north."
        return super().act(verb, game, player, target=target)


def build_world():
    foyer = Location(
        "Foyer",
        "You stand in a dusty foyer. A hallway leads east. A locked iron gate "
        "stands to the north.",
    )
    hallway = Location(
        "Hallway",
        "A narrow hallway lit by a flickering bulb. The foyer is west and a "
        "storage room lies east.",
    )
    storage = Location(
        "Storage Room",
        "Broken crates line the walls. Something glints on a shelf.",
    )
    outside = Location(
        "Outside",
        "Cool night air hits your face. You're free.",
    )

    foyer.connect("east", hallway, "west")
    hallway.connect("east", storage, "west")

    brass_key = Item(
        "brass key",
        "A tarnished brass key with a gate symbol stamped into it.",
        aliases=["key"],
    )
    storage.add_interactable(brass_key)

    gate = Gate(
        name="iron gate",
        description="A tall iron gate blocks the way north.",
        unlock_item="brass key",
        source_location=foyer,
        target_location=outside,
        direction="north",
        aliases=["gate"],
    )
    foyer.add_interactable(gate)

    return {
        "start": foyer,
        "is_win": lambda player: player.current_location is outside,
        "win_message": "You escaped. You win!",
    }


if __name__ == "__main__":
    Game(build_world).repl()
