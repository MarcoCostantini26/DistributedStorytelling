import unittest
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from server.gamestate import GameState

class TestFullSimulation(unittest.TestCase):
    
    def setUp(self):
        self.game = GameState()
        # MONKEY PATCH: Disabilita il salvataggio
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
        
        # --- TURNO 1 ---
        # Gli scrittori inviano proposte
        self.game.add_proposal(self.writer1, "Inizio della storia.") # ID 0
        self.game.add_proposal(self.writer2, "C'era una volta.")     # ID 1
        
        # Verifica stato intermedio
        self.assertEqual(len(self.game.active_proposals), 2)
        
        # Narratore sceglie ID 1
        self.game.select_proposal(1)
        self.assertEqual(len(self.game.story), 1)
        self.assertEqual(self.game.story[-1], "C'era una volta.")
        
        # Nuovo segmento
        self.game.start_new_segment()
        self.assertEqual(self.game.current_segment_id, 1)

        # --- TURNO 2 ---
        self.game.add_proposal(self.writer1, "Viveva in un castello.") # ID 0
        self.game.select_proposal(0)
        self.assertEqual(len(self.game.story), 2)
        
        # Nuovo segmento
        self.game.start_new_segment()

        # --- TURNO 3 ---
        self.game.add_proposal(self.writer2, "E mangiava pizza.") # ID 0
        self.game.select_proposal(0)
        self.assertEqual(len(self.game.story), 3)

        # --- FINE PARTITA ---
        # Simuliamo lo stop del narratore
        self.game.is_running = False
        
        # Verifica storia finale
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