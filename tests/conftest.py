"""Shared test fixtures for BoardGameRules test suite."""

import pytest

from boardgamerules.domain.models import GameState, Player


@pytest.fixture
def sample_players() -> tuple[Player, Player]:
    """Provides a pair of distinct players for test scenarios."""
    return (
        Player(id="p1", name="Alice"),
        Player(id="p2", name="Bob"),
    )


@pytest.fixture
def two_player_game(sample_players: tuple[Player, Player]) -> GameState:
    """Provides an active two-player game state at turn 1."""
    return GameState(game_id="test-game", players=sample_players)
