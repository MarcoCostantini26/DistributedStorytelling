import unittest
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from server.gamestate import GameState

class TestGameFlow(unittest.TestCase):
    
    def setUp(self):
        self.game = GameState()
        self.game.save_state = lambda: None 
        
        self.p1 = ('127.0.0.1', 1001) 
        self.p2 = ('127.0.0.1', 1002) 
        self.p3 = ('127.0.0.1', 1003) 
        
        self.game.add_player(self.p1, "Alice")
        self.game.add_player(self.p2, "Bob")
        self.game.add_player(self.p3, "Charlie")
        
        self.game.start_new_story()
        
        self.game.start_new_segment()
        
        self.game.narrator = self.p1
        self.game.narrator_username = "Alice"

    def test_submission_logic(self):
        """Testa che solo gli scrittori autorizzati possano scrivere."""
        success, msg = self.game.add_proposal(self.p1, "Io sono il narratore")
        self.assertFalse(success)
        
        success, msg = self.game.add_proposal(self.p2, "Io sono uno scrittore")
        self.assertTrue(success)
        self.assertEqual(len(self.game.active_proposals), 1)

    def test_story_progression(self):
        """Testa che la scelta del narratore aggiorni la storia."""
        self.game.add_proposal(self.p2, "Proposta 1")
        self.game.add_proposal(self.p3, "Proposta 2")
        
        self.game.set_phase_selecting()
        
        success, story = self.game.select_proposal(1)
        
        self.assertTrue(success)
        self.assertEqual(len(self.game.story), 1)
        self.assertEqual(self.game.story[0], "Proposta 2")
        self.assertEqual(len(self.game.active_proposals), 0)

if __name__ == '__main__':
    unittest.main()