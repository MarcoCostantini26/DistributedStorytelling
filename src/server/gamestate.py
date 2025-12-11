import random
import json
import os
from datetime import datetime

# ==========================================
# CONFIGURAZIONE PATH & COSTANTI
# ==========================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, '..', '..', 'data')
SAVE_FILE = os.path.join(DATA_DIR, 'recovery.json')
HISTORY_FILE = os.path.join(DATA_DIR, 'history.json')
THEMES_FILE = os.path.join(DATA_DIR, 'themes.json')

# Fasi del Gioco
PHASE_LOBBY = "LOBBY"
PHASE_WRITING = "WRITING"      
PHASE_SELECTING = "SELECTING"  
PHASE_VOTING = "VOTING"         

class GameState:
    """
    Gestisce la logica centrale, lo stato della partita e la persistenza dei dati.
    Agisce come 'Single Source of Truth' per il server.
    """
    def __init__(self, persistence=True):
        self.persistence = persistence
        
        self.players = {}           
        self.player_votes = {}      
        self.active_proposals = []  
        
        self.leader = None          
        self.narrator = None        
        self.narrator_username = None 
        self.story = []             
        self.story_usernames = []   
        self.current_theme = "" 
        self.is_running = False
        self.current_segment_id = 0
        self.phase = PHASE_LOBBY    
        
        self.available_themes = []
        self._load_themes()
        
        if self.persistence:
            self.load_state()

    def _load_themes(self):
        """Carica i temi dal file JSON o usa un default."""
        try:
            if os.path.exists(THEMES_FILE):
                with open(THEMES_FILE, 'r', encoding='utf-8') as f:
                    self.available_themes = json.load(f)
            else:
                self.available_themes = ["Tema Default"]
        except Exception:
            self.available_themes = ["Tema di Emergenza"]

    # ==========================================
    # PERSISTENZA & RECOVERY
    # ==========================================
    def save_state(self):
        """Salva lo stato corrente su disco per crash recovery."""
        if not self.persistence: return

        if not self.is_running:
            if os.path.exists(SAVE_FILE):
                try: os.remove(SAVE_FILE)
                except: pass
            return

        data = {
            "story": self.story,
            "story_usernames": self.story_usernames,
            "narrator_username": self.narrator_username,
            "current_theme": self.current_theme,
            "active_proposals": self.active_proposals,
            "current_segment_id": self.current_segment_id,
            "is_running": self.is_running,
            "phase": self.phase 
        }
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(SAVE_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"[ERRORE] Salvataggio fallito: {e}")

    def load_state(self):
        """Ripristina lo stato precedente in caso di riavvio del server."""
        if not os.path.exists(SAVE_FILE): return

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
            self.phase = data.get("phase", PHASE_LOBBY)
            
            print(f"[RECOVERY] Ripristinato. Fase: {self.phase}, Narratore: {self.narrator_username}")
        except Exception as e:
            print(f"[ERRORE] Recovery fallito: {e}")
            if os.path.exists(SAVE_FILE):
                try: os.remove(SAVE_FILE)
                except: pass

    # ==========================================
    # GESTIONE GIOCATORI
    # ==========================================
    def add_player(self, addr, username):
        clean_name = username.strip()
        if not self.players:
            self.leader = addr 
        self.players[addr] = clean_name
        
        if self.is_running and clean_name == self.narrator_username:
            self.narrator = addr
            print(f"[RECOVERY] Il Narratore {clean_name} è tornato!")
            
        return clean_name

    def remove_player(self, addr):
        """
        Rimuove un giocatore. Se era Leader, ne elegge uno nuovo.
        Ritorna l'indirizzo del nuovo leader (se cambiato).
        """
        new_leader_addr = None 
        if addr in self.players:
            if self.persistence: print(f"[INFO] Rimozione giocatore: {self.players[addr]}")
            del self.players[addr]
            
            if addr == self.leader:
                self.leader = list(self.players.keys())[0] if self.players else None
                new_leader_addr = self.leader
            
            if addr in self.player_votes:
                del self.player_votes[addr]
            
            if addr == self.narrator:
                self.narrator = None 
        
        return new_leader_addr

    # ==========================================
    # LOGICA DI GIOCO (GAME LOOP)
    # ==========================================
    def start_new_story(self):
        """Inizializza una nuova partita (Reset variabili, scelta Narratore/Tema)."""
        self.player_votes.clear()
        if len(self.players) < 2: return False, "Servono 2 giocatori."
        
        self.is_running = True
        self.story_usernames = list(self.players.values())
        
        self.narrator = random.choice(list(self.players.keys()))
        self.narrator_username = self.players[self.narrator]
        
        if self.available_themes: self.current_theme = random.choice(self.available_themes)
        else: self.current_theme = "Tema misterioso"
            
        self.story = []
        self.current_segment_id = 0
        self.phase = PHASE_LOBBY 
        
        self.save_state()
        return True, {
            "narrator_id": self.narrator, 
            "narrator_name": self.narrator_username,
            "theme": self.current_theme
        }

    def start_new_segment(self):
        """Avvia un nuovo round di scrittura."""
        self.current_segment_id += 1
        self.active_proposals = []
        self.phase = PHASE_WRITING 
        self.save_state()
        return self.current_segment_id

    def add_proposal(self, user_id, text):
        """
        Registra una proposta da un giocatore.
        CRITICO: Rifiuta la proposta se la fase non è WRITING (Timer scaduto).
        """
        if self.phase != PHASE_WRITING:
            return False, "Tempo scaduto! Fase chiusa."

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
        self.save_state()
        return True, proposal

    def set_phase_selecting(self):
        """Helper per chiudere la fase di scrittura manualmente (usato dai test e dai timeout)."""
        self.phase = PHASE_SELECTING
        self.save_state()

    def select_proposal(self, proposal_id):
        """Il narratore sceglie la proposta vincente."""
        selected = next((p for p in self.active_proposals if p['id'] == proposal_id), None)
        if selected:
            self.story.append(selected['text'])
            self.active_proposals = []
            self.phase = PHASE_LOBBY 
            self.save_state()
            return True, self.story
        return False, None

    def abort_game(self):
        """Reset forzato della partita."""
        self.is_running = False
        self.phase = PHASE_LOBBY
        self.active_proposals = []
        self.player_votes.clear()
        self.story_usernames = []
        self.save_state() 

    def register_vote(self, user_id, is_yes):
        self.player_votes[user_id] = is_yes
        return len(self.player_votes)

    # ==========================================
    # UTILITIES
    # ==========================================
    def count_active_writers(self):
        """Conta quanti giocatori attivi (escluso narratore) devono ancora scrivere."""
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
        """Archivia la storia completa in JSON a fine partita."""
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
            except Exception: pass

        history_data.append(story_entry)

        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
                json.dump(history_data, f, indent=4)
            print(f"[ARCHIVIO] Storia salvata in {HISTORY_FILE}")
        except Exception as e:
            print(f"[ERRORE] Impossibile salvare storico: {e}")