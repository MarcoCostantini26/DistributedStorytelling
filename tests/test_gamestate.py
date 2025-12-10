import unittest
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from server.gamestate import GameState

class TestGameState(unittest.TestCase):
    
    def setUp(self):
        self.game = GameState()
        self.game.save_state = lambda: None

    def test_add_player_and_leader_election(self):
        """Testa l'aggiunta giocatori e l'elezione automatica del Leader."""
        self.game.add_player(('127.0.0.1', 1001), "Alice")
        self.assertEqual(self.game.leader, ('127.0.0.1', 1001), "Il primo giocatore deve essere Leader")
        
        self.game.add_player(('127.0.0.1', 1002), "Bob")
        self.assertEqual(len(self.game.players), 2)
        self.assertEqual(self.game.leader, ('127.0.0.1', 1001), "Il Leader non deve cambiare se entra un altro")

    def test_start_game_constraints(self):
        """Testa che il gioco non parta con un solo giocatore (Corner Case)."""
        self.game.add_player(('127.0.0.1', 1001), "Alice")
        success, msg = self.game.start_new_story()
        self.assertFalse(success, "Il gioco non dovrebbe partire con 1 giocatore")
        
        self.game.add_player(('127.0.0.1', 1002), "Bob")
        success, msg = self.game.start_new_story()
        self.assertTrue(success, "Il gioco deve partire con 2 giocatori")
        self.assertTrue(self.game.is_running)

    def test_voting_logic(self):
        """Testa la logica di votazione per il riavvio."""
        self.game.add_player(('127.0.0.1', 1001), "Alice")
        self.game.add_player(('127.0.0.1', 1002), "Bob")
        
        count = self.game.register_vote(('127.0.0.1', 1001), True)
        self.assertEqual(count, 1)
        self.assertEqual(self.game.player_votes[('127.0.0.1', 1001)], True)

if __name__ == '__main__':
    unittest.main()