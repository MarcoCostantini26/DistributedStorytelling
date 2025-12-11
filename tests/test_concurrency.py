import unittest
import sys
import os
import threading

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from server.gamestate import GameState

class TestConcurrency(unittest.TestCase):
    
    def setUp(self):
        self.game = GameState()
        self.game.save_state = lambda: None 
        
        self.narrator = ('127.0.0.1', 9999)
        self.game.add_player(self.narrator, "Narrator")
        
        self.writers = []
        for i in range(100):
            addr = ('127.0.0.1', 10000 + i)
            name = f"Writer_{i}"
            self.game.add_player(addr, name)
            self.writers.append(addr)
            
        self.game.start_new_story()
        
        self.game.start_new_segment()
        
        self.game.narrator = self.narrator
        self.game.narrator_username = "Narrator"

    def test_concurrent_proposals(self):
        """Simula 100 client che inviano una proposta nello stesso istante."""
        
        def send_proposal(addr, idx):
            self.game.add_proposal(addr, f"Proposta dal thread {idx}")

        threads = []
        for i, addr in enumerate(self.writers):
            t = threading.Thread(target=send_proposal, args=(addr, i))
            threads.append(t)
            t.start()
            
        for t in threads:
            t.join()
            
        self.assertEqual(len(self.game.active_proposals), 100, 
                         "Il server ha perso delle proposte durante l'invio concorrente!")

if __name__ == '__main__':
    unittest.main()