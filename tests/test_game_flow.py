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
        
        self.game.narrator = self.p1
        self.game.narrator_username = "Alice"

    def test_reconnection_whitelist(self):
        """Test CRUCIALE: Verifica che il server ricordi chi era in gioco."""
        self.assertIn("Bob", self.game.story_usernames)
        
        self.game.remove_player(self.p2)
        
        self.assertNotIn(self.p2, self.game.players)

        self.assertIn("Bob", self.game.story_usernames)

    def test_submission_logic(self):
        """Testa che solo gli scrittori autorizzati possano scrivere."""
        success, res = self.game.add_proposal(self.p2, "C'era una volta...")
        self.assertTrue(success)
        self.assertEqual(len(self.game.active_proposals), 1)
        
        success, res = self.game.add_proposal(self.p1, "Io sono il narratore")
        self.assertFalse(success, "Il narratore non dovrebbe poter proporre")
        
        p_outsider = ('127.0.0.1', 9999)
        self.game.add_player(p_outsider, "Hacker")
        success, res = self.game.add_proposal(p_outsider, "Spam")
        self.assertFalse(success, "Gli spettatori non dovrebbero poter scrivere")

    def test_story_progression(self):
        """Testa che la scelta del narratore aggiorni la storia."""
        self.game.add_proposal(self.p2, "Bob dice A") 
        self.game.add_proposal(self.p3, "Charlie dice B") 
        
        success, new_story = self.game.select_proposal(1)
        
        self.assertTrue(success)
        self.assertEqual(len(self.game.story), 1)
        self.assertEqual(self.game.story[0], "Charlie dice B")
        
        self.assertEqual(len(self.game.active_proposals), 0)

if __name__ == '__main__':
    unittest.main()