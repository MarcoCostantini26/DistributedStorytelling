import random
import json
import os

class GameState:
    def __init__(self):
        self.players = {}           # Map[addr_tuple, username]
        self.active_story_players = [] 
        
        # --- GESTIONE VOTI (DIZIONARIO) ---
        self.player_votes = {}      # Map[user_id, True/False] (True=SI, False=NO)
        # ----------------------------------

        self.leader = None
        self.narrator = None  
        self.story = []       
        self.current_theme = "" 
        self.active_proposals = [] 
        self.is_running = False
        self.current_segment_id = 0
        
        self.available_themes = []
        self._load_themes()

    def _load_themes(self):
        try:
            base_dir = os.path.dirname(os.path.abspath(__file__)) 
            theme_path = os.path.join(base_dir, '..', '..', 'data', 'themes.json')
            with open(theme_path, 'r', encoding='utf-8') as f:
                self.available_themes = json.load(f)
            print(f"[SERVER] Caricati {len(self.available_themes)} temi.")
        except Exception as e:
            print(f"[ATTENZIONE] Errore temi ({e}). Uso default.")
            self.available_themes = ["Tema Default: Avventura Improvvisata"]

    def add_player(self, addr, username):
        if not self.players:
            self.leader = addr
        self.players[addr] = username
        print(f"Giocatore aggiunto: {username} ({addr}).")

    def remove_player(self, addr):
        if addr in self.players:
            del self.players[addr]
            # Se il leader esce, passiamo il ruolo al prossimo
            if addr == self.leader:
                if self.players:
                    self.leader = list(self.players.keys())[0]
                    print(f"[INFO] Nuovo Leader assegnato: {self.players[self.leader]}")
                else:
                    self.leader = None
            
            # Rimuoviamo anche dai voti
            if addr in self.player_votes:
                del self.player_votes[addr]

    def register_vote(self, user_id, is_yes):
        """Registra la scelta specifica dell'utente."""
        self.player_votes[user_id] = is_yes
        return len(self.player_votes)

    def start_new_story(self):
        # Reset voti
        self.player_votes.clear()

        if len(self.players) < 2:
            return False, "Servono almeno 2 giocatori per iniziare."
        
        self.is_running = True
        self.active_story_players = list(self.players.keys())
        self.narrator = random.choice(self.active_story_players)
        
        if self.available_themes:
            self.current_theme = random.choice(self.available_themes)
        else:
            self.current_theme = "Tema misterioso"
            
        self.story = []
        self.current_segment_id = 0
        
        return True, {
            "narrator_id": self.narrator, 
            "narrator_name": self.players[self.narrator],
            "theme": self.current_theme
        }

    def start_new_segment(self):
        self.current_segment_id += 1
        self.active_proposals = []
        return self.current_segment_id

    def add_proposal(self, user_id, text):
        if user_id == self.narrator:
            return False, "Il narratore non può inviare proposte."
        
        if user_id not in self.active_story_players:
             return False, "Gli spettatori non possono scrivere."

        proposal = {
            "id": len(self.active_proposals),
            "author": self.players.get(user_id, "Sconosciuto"),
            "text": text
        }
        self.active_proposals.append(proposal)
        return True, proposal

    def select_proposal(self, proposal_id):
        selected = next((p for p in self.active_proposals if p['id'] == proposal_id), None)
        
        if selected:
            full_segment_text = selected['text']
            self.story.append(full_segment_text)
            self.active_proposals = []
            return True, self.story
        return False, None