"""Validation rules for board game actions and turns.

Demonstrates Clean Code:
- Pure validation functions with no hidden side effects
- Self-explanatory naming and clear contracts
- Explicit domain exception on rule failure
"""

from __future__ import annotations

from boardgamerules.domain.exceptions import RuleViolationError
from boardgamerules.domain.models import Action, GameState


def validate_player_turn(state: GameState, action: Action) -> None:
    """Validates that the action is being performed by the active player.

    Raises:
        RuleViolationError: If a player attempts an action when it is not their turn,
                           or if the game has already completed.
    """
    if state.is_completed:
        raise RuleViolationError(
            rule_name="GameActive",
            reason=(
                f"Action '{action.action_type}' rejected because game "
                f"'{state.game_id}' is already over."
            ),
        )

    active_player = state.active_player
    if action.player_id != active_player.id:
        raise RuleViolationError(
            rule_name="TurnOrder",
            reason=(
                f"It is {active_player.name}'s turn (id: {active_player.id}), "
                f"not {action.player_id}'s."
            ),
        )
