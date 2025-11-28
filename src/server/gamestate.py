import random
import json
import os

class GameState:
    def __init__(self):
        self.players = {}           
        self.story_usernames = []   
        self.player_votes = {}      
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
        except Exception:
            self.available_themes = ["Tema Default"]

    def add_player(self, addr, username):
        clean_name = username.strip()
        if not self.players:
            self.leader = addr
        self.players[addr] = clean_name
        print(f"Giocatore aggiunto: {clean_name} ({addr}).")
        return clean_name

    def remove_player(self, addr):
        new_leader_addr = None # Variabile per tracciare il cambio leader
        
        if addr in self.players:
            username = self.players[addr]
            del self.players[addr]
            
            # Se esce il leader
            if addr == self.leader:
                if self.players:
                    self.leader = list(self.players.keys())[0]
                    new_leader_addr = self.leader # Segnaliamo chi è il nuovo
                    print(f"[INFO] Nuovo Leader assegnato: {self.players[self.leader]}")
                else:
                    self.leader = None
            
            if addr in self.player_votes:
                del self.player_votes[addr]
            
            print(f"[INFO] {username} si è disconnesso.")
        
        return new_leader_addr # Ritorniamo l'indirizzo del nuovo leader

    def register_vote(self, user_id, is_yes):
        self.player_votes[user_id] = is_yes
        return len(self.player_votes)

    def start_new_story(self):
        self.player_votes.clear()
        if len(self.players) < 2:
            return False, "Servono almeno 2 giocatori."
        
        self.is_running = True
        self.story_usernames = list(self.players.values())
        
        self.narrator = random.choice(list(self.players.keys()))
        
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
        
        username = self.players.get(user_id)
        if username not in self.story_usernames:
             return False, "Gli spettatori non possono scrivere."

        proposal = {
            "id": len(self.active_proposals),
            "author": username,
            "text": text
        }
        self.active_proposals.append(proposal)
        return True, proposal

    def count_active_writers(self):
        count = 0
        for addr, name in self.players.items():
            if name in self.story_usernames and addr != self.narrator:
                count += 1
        return count
    
    def has_user_submitted(self, username):
        for p in self.active_proposals:
            if p['author'] == username:
                return True
        return False

    def select_proposal(self, proposal_id):
        selected = next((p for p in self.active_proposals if p['id'] == proposal_id), None)
        if selected:
            self.story.append(selected['text'])
            self.active_proposals = []
            return True, self.story
        return False, None