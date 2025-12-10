import unittest
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from server.gamestate import GameState

class TestBoundaries(unittest.TestCase):
    
    def setUp(self):
        self.game = GameState()
        self.game.save_state = lambda: None
        
        self.narrator = ('N', 0)
        self.writer = ('W', 1)
        self.game.add_player(self.narrator, "Narrator")
        self.game.add_player(self.writer, "Writer")
        self.game.start_new_story()
        
        self.game.narrator = self.narrator
        self.game.narrator_username = "Narrator"

    def test_long_story_stability(self):
        """Simula una storia infinita (1000 turni)."""
        for i in range(1000):
            self.game.add_proposal(self.writer, f"Frase numero {i}")
            self.game.select_proposal(0)
            self.game.start_new_segment()
            
        self.assertEqual(len(self.game.story), 1000)
        self.assertEqual(self.game.current_segment_id, 1000)
        self.assertEqual(self.game.story[-1], "Frase numero 999")
        
        self.game.add_proposal(self.writer, "Frase 1001")
        self.assertEqual(len(self.game.active_proposals), 1)

if __name__ == '__main__':
    unittest.main()