"""Unit tests for domain models."""

import pytest

from boardgamerules.domain.models import GameState, Player


def test_should_create_player_with_valid_id_and_name() -> None:
    # Arrange & Act
    player = Player(id="p1", name="Alice")

    # Assert
    assert player.id == "p1"
    assert player.name == "Alice"


@pytest.mark.parametrize("empty_value", ["", "   "])
def test_should_raise_error_when_player_name_is_blank(empty_value: str) -> None:
    # Arrange, Act & Assert
    with pytest.raises(ValueError, match="Player name cannot be empty"):
        Player(id="p1", name=empty_value)


def test_should_advance_to_next_player_without_mutating_original_state(
    two_player_game: GameState,
) -> None:
    # Arrange
    initial_player = two_player_game.active_player

    # Act
    next_state = two_player_game.advance_to_next_player()

    # Assert
    assert two_player_game.active_player == initial_player
    assert next_state.active_player.id == "p2"
    assert next_state.turn_number == 1


def test_should_increment_turn_number_after_full_round_rotation(
    two_player_game: GameState,
) -> None:
    # Arrange
    first_move = two_player_game.advance_to_next_player()

    # Act
    second_move = first_move.advance_to_next_player()

    # Assert
    assert second_move.active_player.id == "p1"
    assert second_move.turn_number == 2
