"""BoardGameRules entry point."""

from boardgamerules.domain.models import Action, GameState, Player
from boardgamerules.engine.validator import validate_player_turn


def main() -> None:
    # 1. Initialize players
    alice = Player(id="p1", name="Alice")
    bob = Player(id="p2", name="Bob")

    # 2. Initialize game state
    state = GameState(game_id="game-001", players=(alice, bob))
    print(f"Game '{state.game_id}' started with players: {alice.name}, {bob.name}")
    print(f"Current turn {state.turn_number}: Active player is {state.active_player.name}")

    # 3. Simulate an action by the active player
    action = Action(player_id="p1", action_type="ROLL_DICE")
    validate_player_turn(state, action)
    print(f"Action '{action.action_type}' by {state.active_player.name} validated successfully!")

    # 4. Advance turn
    next_state = state.advance_to_next_player()
    print(f"Advanced turn: Next active player is {next_state.active_player.name}")


if __name__ == "__main__":
    main()
