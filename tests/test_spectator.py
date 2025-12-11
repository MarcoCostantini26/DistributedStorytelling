import unittest
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from server.gamestate import GameState

class TestSpectator(unittest.TestCase):
    
    def setUp(self):
        self.game = GameState()
        self.game.save_state = lambda: None
        
        self.p1 = ('IP1', 1)
        self.p2 = ('IP2', 2)
        self.game.add_player(self.p1, "Alice")
        self.game.add_player(self.p2, "Bob")
        
        self.game.start_new_story()
        
        self.game.start_new_segment()
        
    def test_late_joiner_is_spectator(self):
        """Chi entra dopo lo start è uno spettatore."""
        spectator = ('IP3', 3)
        self.game.add_player(spectator, "Charlie")
        
        self.assertNotIn("Charlie", self.game.story_usernames)
        self.assertIn("Alice", self.game.story_usernames)

    def test_spectator_cannot_write(self):
        """Uno spettatore prova a inviare una proposta."""
        spectator = ('IP3', 3)
        self.game.add_player(spectator, "Charlie")
        
        success, msg = self.game.add_proposal(spectator, "Voglio giocare anche io!")
        
        self.assertFalse(success, "Lo spettatore non dovrebbe poter scrivere!")
        self.assertEqual(len(self.game.active_proposals), 0)
        
        self.assertIn("spettatori", msg.lower())

if __name__ == '__main__':
    unittest.main()