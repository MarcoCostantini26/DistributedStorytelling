class GameState:
    def __init__(self):
        self.players = {}     # Map[address, username]
        self.narrator = None  # UserID del narratore corrente [cite: 206]
        self.story = []       # Lista dei segmenti approvati
        self.current_theme = "" 
        self.active_proposals = [] # Proposte per il segmento corrente
        self.is_running = False

    def add_player(self, addr, username):
        self.players[addr] = username
        print(f"Giocatore aggiunto: {username} ({addr})")

    def remove_player(self, addr):
        if addr in self.players:
            print(f"Giocatore rimosso: {self.players[addr]}")
            del self.players[addr]
            # Qui andrà gestita la logica se il narratore si disconnette [cite: 329]

    def set_narrator(self, addr):
        self.narrator = addr
        # Logica per notificare i client (implementata nel core)