import unittest
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from server.gamestate import GameState

class TestCleanup(unittest.TestCase):
    
    def setUp(self):
        self.game = GameState()
        self.game.save_state = lambda: None 
        
        self.narrator = ('N', 0)
        self.writer = ('W', 1)
        
        self.game.add_player(self.narrator, "Narrator")
        self.game.add_player(self.writer, "Writer")
        
        self.game.start_new_story()
        
        self.game.start_new_segment()
        self.game.narrator = self.narrator
        self.game.narrator_username = "Narrator"

        success, msg = self.game.add_proposal(self.writer, "Testo da cancellare")
        if not success:
            print(f"DEBUG SETUP FAIL: {msg}")
            
        self.game.register_vote(self.writer, True)

    def test_abort_clears_everything(self):
        """Verifica che abort_game() riporti lo stato a zero."""
        self.assertTrue(self.game.is_running)
        self.assertEqual(len(self.game.active_proposals), 1, "Il setup non ha aggiunto la proposta!")
        self.assertEqual(len(self.game.player_votes), 1)
        self.assertGreater(len(self.game.story_usernames), 0)

        self.game.abort_game()

        self.assertFalse(self.game.is_running, "Il gioco dovrebbe essere fermo")
        self.assertEqual(len(self.game.active_proposals), 0, "Le proposte non sono state cancellate")
        self.assertEqual(len(self.game.player_votes), 0, "I voti non sono stati cancellati")
        self.assertEqual(len(self.game.story_usernames), 0, "La whitelist non è stata pulita")
        
        self.assertEqual(len(self.game.players), 2)

if __name__ == '__main__':
    unittest.main()