import unittest
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from server.gamestate import GameState

class TestRobustness(unittest.TestCase):
    
    def setUp(self):
        self.game = GameState()
        self.game.save_state = lambda: None

        self.p1 = ('IP1', 1)
        self.p2 = ('IP2', 2)
        self.game.add_player(self.p1, "Alice")
        self.game.add_player(self.p2, "Bob")
        self.game.start_new_story()
        
        self.game.narrator = self.p1
        self.game.narrator_username = "Alice"

    def test_empty_proposal(self):
        """Cosa succede se invio una stringa vuota?"""
        success, res = self.game.add_proposal(self.p2, "") 
        self.assertTrue(success) 
        self.assertEqual(self.game.active_proposals[0]['text'], "")

    def test_massive_proposal(self):
        """Stress test: invio di un testo enorme (Buffer Overflow check)."""
        huge_text = "A" * 1000000 
        success, res = self.game.add_proposal(self.p2, huge_text)
        
        self.assertTrue(success)
        self.assertEqual(len(self.game.active_proposals), 1)

    def test_invalid_selection_id(self):
        """Il narratore sceglie un ID che non esiste."""
        self.game.add_proposal(self.p2, "Proposta valida") 
        
        success, story = self.game.select_proposal(999)
        self.assertFalse(success)
        self.assertIsNone(story)
        
        success, story = self.game.select_proposal(-1)
        self.assertFalse(success)

    def test_duplicate_username_handling(self):
        """Verifica gestione omonimia (semplificata)."""
        p3 = ('IP3', 3)
        clean_name = self.game.add_player(p3, "Bob")
        
        self.assertEqual(self.game.players[p3], "Bob")
        self.assertIn(p3, self.game.players)
        self.assertIn(self.p2, self.game.players)

if __name__ == '__main__':
    unittest.main()