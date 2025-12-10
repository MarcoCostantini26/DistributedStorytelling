import unittest
import sys
import os
import json

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from server.gamestate import GameState

class TestThemes(unittest.TestCase):

    def setUp(self):
        pass
    
    def test_load_themes_success(self):
        """Verifica il caricamento normale dei temi."""
        game = GameState()
        game.save_state = lambda: None
        self.assertTrue(len(game.available_themes) > 0)
        self.assertIsInstance(game.available_themes, list)

    def test_theme_selection(self):
        """Verifica che venga scelto un tema valido all'avvio."""
        game = GameState()
        game.save_state = lambda: None
        game.add_player(('A', 1), "A")
        game.add_player(('B', 2), "B")
        
        success, info = game.start_new_story()
        
        self.assertTrue(success)
        self.assertIsNotNone(game.current_theme)
        self.assertIn(game.current_theme, game.available_themes)
        print(f"Tema selezionato dal test: {game.current_theme}")

    def test_missing_file_fallback(self):
        """Corner Case: Se il file json non esiste, il server deve usare un default."""
        game = GameState()
        game.save_state = lambda: None
        game.available_themes = [] 
        
        game.add_player(('A', 1), "A")
        game.add_player(('B', 2), "B")
        game.start_new_story()
        
        self.assertEqual(game.current_theme, "Tema misterioso")

if __name__ == '__main__':
    unittest.main()