import unittest
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))
from server.gamestate import GameState

class TestFullSimulation(unittest.TestCase):
    
    def setUp(self):
        self.game = GameState()
        self.game.save_state = lambda: None 
        
        self.narrator = ('N', 0)
        self.writer1 = ('W1', 1)
        self.writer2 = ('W2', 2)
        
        self.game.add_player(self.narrator, "Narrator")
        self.game.add_player(self.writer1, "Writer1")
        self.game.add_player(self.writer2, "Writer2")
        
        self.game.start_new_story()
        
        self.game.narrator = self.narrator
        self.game.narrator_username = "Narrator"

    def test_full_game_loop(self):
        """Simula una partita completa di 3 turni."""
        
        self.game.add_proposal(self.writer1, "Inizio della storia.") 
        self.game.add_proposal(self.writer2, "C'era una volta.")     
        
        self.assertEqual(len(self.game.active_proposals), 2)
        
        self.game.select_proposal(1)
        self.assertEqual(len(self.game.story), 1)
        self.assertEqual(self.game.story[-1], "C'era una volta.")
        
        self.game.start_new_segment()
        self.game.narrator = self.narrator
        self.game.narrator_username = "Narrator"

        self.game.add_proposal(self.writer1, "Viveva in un castello.")
        self.game.select_proposal(0)
        self.assertEqual(len(self.game.story), 2)
        
        self.game.start_new_segment()
        self.game.narrator = self.narrator
        self.game.narrator_username = "Narrator"

        self.game.add_proposal(self.writer2, "E mangiava pizza.") 
        self.game.select_proposal(0)
        self.assertEqual(len(self.game.story), 3)

        self.game.is_running = False
        
        expected_story = [
            "C'era una volta.",
            "Viveva in un castello.",
            "E mangiava pizza."
        ]
        self.assertEqual(self.game.story, expected_story)
        
        print("\n[SIMULAZIONE] Storia generata correttamente:")
        for line in self.game.story:
            print(f"> {line}")

if __name__ == '__main__':
    unittest.main()