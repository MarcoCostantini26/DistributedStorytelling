import random
import json  # <--- NUOVO IMPORT
import os    # <--- NUOVO IMPORT

class GameState:
    def __init__(self):
        self.players = {}
        self.leader = None
        self.narrator = None  
        self.story = []       
        self.current_theme = "" 
        self.active_proposals = [] 
        self.is_running = False
        self.current_segment_id = 0
        
        # --- NUOVO: Lista temi e Caricamento ---
        self.available_themes = []
        self._load_themes()

    def _load_themes(self):
        """Carica i temi dal file JSON nella cartella data."""
        try:
            # Calcoliamo il percorso assoluto per evitare errori
            # Partiamo dalla posizione di questo file (gamestate.py)
            base_dir = os.path.dirname(os.path.abspath(__file__)) 
            # Risaliamo a project_root/data/themes.json
            # src/server/ -> src/ -> project_root/ -> data/
            theme_path = os.path.join(base_dir, '..', '..', 'data', 'themes.json')
            
            with open(theme_path, 'r', encoding='utf-8') as f:
                self.available_themes = json.load(f)
            
            print(f"[SERVER] Caricati {len(self.available_themes)} temi da {theme_path}")
            
        except FileNotFoundError:
            print("[ATTENZIONE] File themes.json non trovato. Uso temi di default.")
            self.available_themes = ["Tema Default: Avventura Generica"]
        except Exception as e:
            print(f"[ERRORE] Errore caricamento temi: {e}")
            self.available_themes = ["Tema Default: Emergenza"]

    def add_player(self, addr, username):
        if not self.players:
            self.leader = addr
        self.players[addr] = username
        print(f"Giocatore aggiunto: {username}. Leader: {self.players[self.leader]}")

    def remove_player(self, addr):
        if addr in self.players:
            del self.players[addr]
            if addr == self.leader and self.players:
                self.leader = list(self.players.keys())[0]

    def start_new_story(self):
        if len(self.players) < 2:
            return False, "Servono almeno 2 giocatori per iniziare."
        
        self.is_running = True
        self.narrator = random.choice(list(self.players.keys()))
        
        # --- NUOVO: Scelta Random dal file caricato ---
        if self.available_themes:
            self.current_theme = random.choice(self.available_themes)
        else:
            self.current_theme = "Tema Sconosciuto"
        # ----------------------------------------------
        
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
            # Modifica precedente: Solo testo
            full_segment_text = selected['text']
            self.story.append(full_segment_text)
            self.active_proposals = []
            return True, self.story
        return False, None