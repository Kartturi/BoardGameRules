"""Unit tests for rule validator."""

import pytest

from boardgamerules.domain.exceptions import RuleViolationError
from boardgamerules.domain.models import Action, GameState
from boardgamerules.engine.validator import validate_player_turn


def test_should_pass_validation_when_active_player_takes_action(
    two_player_game: GameState,
) -> None:
    # Arrange
    action = Action(player_id="p1", action_type="ROLL_DICE")

    # Act & Assert (should not raise)
    validate_player_turn(two_player_game, action)


def test_should_raise_rule_violation_when_non_active_player_takes_action(
    two_player_game: GameState,
) -> None:
    # Arrange
    action = Action(player_id="p2", action_type="ROLL_DICE")

    # Act & Assert
    with pytest.raises(RuleViolationError) as exc_info:
        validate_player_turn(two_player_game, action)

    assert exc_info.value.rule_name == "TurnOrder"
    assert "Alice" in exc_info.value.reason
    assert "p2" in exc_info.value.reason


def test_should_raise_rule_violation_when_game_is_already_completed(
    two_player_game: GameState,
) -> None:
    # Arrange
    completed_game = GameState(
        game_id=two_player_game.game_id,
        players=two_player_game.players,
        is_completed=True,
    )
    action = Action(player_id="p1", action_type="ROLL_DICE")

    # Act & Assert
    with pytest.raises(RuleViolationError) as exc_info:
        validate_player_turn(completed_game, action)

    assert exc_info.value.rule_name == "GameActive"
