import unittest
import sys
import os
import json

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))
import server.gamestate as gs_module 
from server.gamestate import GameState

class TestPersistence(unittest.TestCase):
    
    
    def setUp(self):
        """Prepariamo l'ambiente di test."""
        self.original_save_file = gs_module.SAVE_FILE
        
        self.test_file = "test_recovery.json"
        gs_module.SAVE_FILE = self.test_file
        
        if os.path.exists(self.test_file):
            os.remove(self.test_file)

        self.game = GameState()

    def tearDown(self):
        """Pulizia finale."""
        if os.path.exists(self.test_file):
            os.remove(self.test_file)
            
        gs_module.SAVE_FILE = self.original_save_file

    def test_save_and_load(self):
        """Verifica che i dati salvati vengano ricaricati identici."""
        self.game.add_player(('IP1', 1), "Mario")
        self.game.add_player(('IP2', 2), "Luigi")
        self.game.start_new_story()
        
        self.game.narrator_username = "Mario" 

        success, res = self.game.add_proposal(('IP2', 2), "C'era una volta un fungo.")
        self.assertTrue(success)
        
        self.game.save_state()
        self.assertTrue(os.path.exists(self.test_file))

        new_game = GameState()
        
        self.assertTrue(new_game.is_running)
        self.assertEqual(len(new_game.story_usernames), 2)
        self.assertEqual(len(new_game.active_proposals), 1)
        self.assertEqual(new_game.active_proposals[0]['text'], "C'era una volta un fungo.")

if __name__ == '__main__':
    unittest.main()