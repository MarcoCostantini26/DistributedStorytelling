import random
import json
import os
from datetime import datetime

SAVE_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'recovery.json'))
HISTORY_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'history.json'))

class GameState:
    def __init__(self):
        self.players = {}           # Map[addr, username] (Solo chi è connesso ORA)
        self.story_usernames = []   # Whitelist: Nomi di chi ha iniziato la partita
        self.player_votes = {}      
        self.leader = None          # Indirizzo del leader
        self.narrator = None        # Indirizzo del narratore
        self.narrator_username = None # NUOVO: Serve per riconoscerlo dopo il crash
        self.story = []       
        self.current_theme = "" 
        self.active_proposals = [] 
        self.is_running = False
        self.current_segment_id = 0
        self.available_themes = []
        
        self._load_themes()
        
        # TENTATIVO DI RIPRISTINO STATO
        self.load_state()

    def _load_themes(self):
        try:
            theme_path = os.path.join(os.path.dirname(SAVE_FILE), 'themes.json')
            with open(theme_path, 'r', encoding='utf-8') as f:
                self.available_themes = json.load(f)
        except Exception:
            self.available_themes = ["Tema Default"]

    # --- PERSISTENZA ---
    def save_state(self):
        """Salva lo stato corrente su file JSON."""
        if not self.is_running:
            # Se la partita non corre, cancelliamo il file di recovery
            if os.path.exists(SAVE_FILE):
                os.remove(SAVE_FILE)
            return

        data = {
            "story": self.story,
            "story_usernames": self.story_usernames,
            "narrator_username": self.narrator_username,
            "current_theme": self.current_theme,
            "active_proposals": self.active_proposals,
            "current_segment_id": self.current_segment_id,
            "is_running": self.is_running
        }
        try:
            with open(SAVE_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
            print("[PERSISTENZA] Stato salvato.")
        except Exception as e:
            print(f"[ERRORE] Salvataggio fallito: {e}")

    def load_state(self):
        """Carica lo stato se esiste un file di recovery."""
        if not os.path.exists(SAVE_FILE):
            return

        try:
            with open(SAVE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.story = data.get("story", [])
            self.story_usernames = data.get("story_usernames", [])
            self.narrator_username = data.get("narrator_username")
            self.current_theme = data.get("current_theme", "")
            self.active_proposals = data.get("active_proposals", [])
            self.current_segment_id = data.get("current_segment_id", 0)
            self.is_running = data.get("is_running", False)
            
            print(f"[RECOVERY] Partita ripristinata! Narratore atteso: {self.narrator_username}")
        except Exception as e:
            print(f"[ERRORE] Recovery fallito: {e}")

    def add_player(self, addr, username):
        clean_name = username.strip()
        if not self.players:
            self.leader = addr
        self.players[addr] = clean_name
        
        # SE STIAMO RECUPERANDO DA UN CRASH:
        # Dobbiamo ricollegare l'indirizzo IP al ruolo logico
        if self.is_running and clean_name == self.narrator_username:
            self.narrator = addr
            print(f"[RECOVERY] Il Narratore {clean_name} è tornato!")
            
        print(f"Giocatore aggiunto: {clean_name} ({addr}).")
        return clean_name

    def remove_player(self, addr):
        new_leader_addr = None 
        if addr in self.players:
            username = self.players[addr]
            del self.players[addr]
            
            if addr == self.leader:
                self.leader = list(self.players.keys())[0] if self.players else None
                new_leader_addr = self.leader
            
            if addr in self.player_votes:
                del self.player_votes[addr]
            
            # Nota: Non cancelliamo il narratore da narrator_username, 
            # perché ci serve per riconoscerlo se rientra.
            if addr == self.narrator:
                self.narrator = None # Disconnesso fisicamente
                print(f"[INFO] Narratore {username} disconnesso (Socket perso).")
            else:
                print(f"[INFO] {username} si è disconnesso.")
        
        return new_leader_addr

    def start_new_story(self):
        self.player_votes.clear()
        if len(self.players) < 2: return False, "Servono 2 giocatori."
        
        self.is_running = True
        self.story_usernames = list(self.players.values())
        
        # Scelta Narratore
        self.narrator = random.choice(list(self.players.keys()))
        self.narrator_username = self.players[self.narrator] # Salviamo il nome per il crash
        
        if self.available_themes: self.current_theme = random.choice(self.available_themes)
        else: self.current_theme = "Tema misterioso"
            
        self.story = []
        self.current_segment_id = 0
        
        self.save_state() # SAVE
        return True, {
            "narrator_id": self.narrator, 
            "narrator_name": self.narrator_username,
            "theme": self.current_theme
        }

    def start_new_segment(self):
        self.current_segment_id += 1
        self.active_proposals = []
        self.save_state() # SAVE
        return self.current_segment_id

    def add_proposal(self, user_id, text):
        # Controllo robusto: se il narratore non è connesso fisicamente, usiamo il nome
        current_user_name = self.players.get(user_id)
        
        if current_user_name == self.narrator_username:
            return False, "Il narratore non può inviare proposte."
        
        if current_user_name not in self.story_usernames:
             return False, "Gli spettatori non possono scrivere."

        proposal = {
            "id": len(self.active_proposals),
            "author": current_user_name,
            "text": text
        }
        self.active_proposals.append(proposal)
        self.save_state() # SAVE
        return True, proposal

    def select_proposal(self, proposal_id):
        selected = next((p for p in self.active_proposals if p['id'] == proposal_id), None)
        if selected:
            self.story.append(selected['text'])
            self.active_proposals = []
            self.save_state() # SAVE
            return True, self.story
        return False, None

    def abort_game(self):
        self.is_running = False
        self.active_proposals = []
        self.player_votes.clear()
        self.story_usernames = []
        self.save_state() # Questo cancellerà il file o salverà is_running=False
        print("[GAMESTATE] Partita resettata.")

    def register_vote(self, user_id, is_yes):
        self.player_votes[user_id] = is_yes
        return len(self.player_votes)

    def count_active_writers(self):
        count = 0
        for addr, name in self.players.items():
            if name in self.story_usernames and name != self.narrator_username:
                count += 1
        return count
    
    def has_user_submitted(self, username):
        for p in self.active_proposals:
            if p['author'] == username: return True
        return False

    def save_to_history(self):
        """Salva la storia conclusa nell'archivio storico permanente."""
        if not self.story: return

        story_entry = {
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "theme": self.current_theme,
            "narrator": self.narrator_username,
            "full_text": self.story
        }

        history_data = []
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                    history_data = json.load(f)
            except Exception:
                history_data = []

        history_data.append(story_entry)

        try:
            with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
                json.dump(history_data, f, indent=4)
            print(f"[ARCHIVIO] Storia salvata in {HISTORY_FILE}")
        except Exception as e:
            print(f"[ERRORE] Impossibile salvare storico: {e}")