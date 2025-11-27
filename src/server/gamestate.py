import random

class GameState:
    def __init__(self):
        self.players = {}     # Map[addr_tuple, username]
        self.leader = None
        self.narrator = None  
        self.story = []       
        self.current_theme = "" 
        self.active_proposals = [] 
        self.is_running = False
        self.current_segment_id = 0

    def add_player(self, addr, username):
        # Se è il primo giocatore, diventa il Leader
        if not self.players:
            self.leader = addr
        
        self.players[addr] = username
        print(f"Giocatore aggiunto: {username} ({addr}). Leader attuale: {self.players[self.leader]}")

    def remove_player(self, addr):
        if addr in self.players:
            del self.players[addr]
            # Se il leader esce, assegnamo il ruolo al prossimo
            if addr == self.leader and self.players:
                self.leader = list(self.players.keys())[0]

    def start_new_story(self):
        
        # Controllo minimo giocatori
        if len(self.players) < 2:
            return False, "Servono almeno 2 giocatori per iniziare."
        
        self.is_running = True
        # Assegna narratore
        self.narrator = random.choice(list(self.players.keys()))
        
        # Genera tema
        self.current_theme = "Un'avventura in una città dimenticata" 
        self.story = []

        self.current_segment_id = 0
        return True, {
            "narrator_id": self.narrator, 
            "narrator_name": self.players[self.narrator],
            "theme": self.current_theme
        }

    def start_new_segment(self):
        """Prepara il server per un nuovo round di scrittura"""
        self.current_segment_id += 1
        self.active_proposals = [] # Pulisce le proposte vecchie
        return self.current_segment_id

    def add_proposal(self, user_id, text):
        if user_id == self.narrator:
            return False, "Il narratore non può inviare proposte."
            
        proposal = {
            "id": len(self.active_proposals),
            "author": self.players.get(user_id, "Sconosciuto"),
            "text": text
        }
        self.active_proposals.append(proposal)
        return True, proposal