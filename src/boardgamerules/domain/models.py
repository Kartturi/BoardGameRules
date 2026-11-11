"""Core domain models representing games, players, and rules.

Follows Clean Code principles:
- Intention-revealing names
- Immutability with frozen dataclasses
- Pure data structures separated from behavior
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Player:
    """Represents a participant in a board game."""

    id: str
    name: str

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("Player id cannot be empty.")
        if not self.name.strip():
            raise ValueError("Player name cannot be empty.")


@dataclass(frozen=True)
class Action:
    """Represents a move or action initiated by a player."""

    player_id: str
    action_type: str
    payload: dict[str, str | int | float | bool] = field(default_factory=dict)


@dataclass(frozen=True)
class GameState:
    """Represents the complete snapshot of a game's state at a point in time."""

    game_id: str
    players: tuple[Player, ...]
    active_player_index: int = 0
    turn_number: int = 1
    is_completed: bool = False

    @property
    def active_player(self) -> Player:
        """Returns the player whose turn it currently is."""
        if not self.players:
            raise ValueError("Cannot determine active player in a game with no players.")
        return self.players[self.active_player_index]

    def advance_to_next_player(self) -> GameState:
        """Returns a new GameState with the turn advanced to the next player.

        Demonstrates immutability and command-query separation by returning a new
        state object rather than mutating in place.
        """
        if not self.players:
            raise ValueError("Cannot advance turn in a game with no players.")

        next_index = (self.active_player_index + 1) % len(self.players)
        next_turn = self.turn_number + (1 if next_index == 0 else 0)

        return GameState(
            game_id=self.game_id,
            players=self.players,
            active_player_index=next_index,
            turn_number=next_turn,
            is_completed=self.is_completed,
        )
