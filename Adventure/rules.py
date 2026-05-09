from core import Game
from world import build_world


if __name__ == "__main__":
    Game(build_world).repl()
