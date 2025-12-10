import unittest
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from server.gamestate import GameState

class TestLeaderMechanics(unittest.TestCase):
    
    def setUp(self):
        self.game = GameState()
        self.game.save_state = lambda: None

    def test_leader_handover(self):
        """Se il leader esce, il prossimo giocatore diventa leader."""
        p1 = ('127.0.0.1', 1001)
        p2 = ('127.0.0.1', 1002)
        p3 = ('127.0.0.1', 1003)

        self.game.add_player(p1, "LeaderOriginale")
        self.game.add_player(p2, "Vice")
        self.game.add_player(p3, "Terzo")

        self.assertEqual(self.game.leader, p1)

        new_leader = self.game.remove_player(p1)

        self.assertIsNotNone(new_leader)
        self.assertEqual(new_leader, p2, "Il Leader dovrebbe passare al secondo giocatore (Vice)")
        
        self.assertEqual(self.game.leader, p2)

    def test_leader_leaves_empty_room(self):
        """Se l'unico giocatore (leader) esce, il leader diventa None."""
        p1 = ('127.0.0.1', 1001)
        self.game.add_player(p1, "Solo")
        
        self.game.remove_player(p1)
        
        self.assertIsNone(self.game.leader)
        self.assertEqual(len(self.game.players), 0)

if __name__ == '__main__':
    unittest.main()