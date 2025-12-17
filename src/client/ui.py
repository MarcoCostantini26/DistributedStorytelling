import tkinter as tk
from tkinter import scrolledtext, messagebox, simpledialog
import socket
import threading
import json
import sys
import os
import time

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from common.protocol import *

# ==========================================
# CONFIGURAZIONE CLIENT
# ==========================================
HOST = '127.0.0.1'
PORT = 65432

BG_COLOR = "#2E3440"
TEXT_BG = "#3B4252"
FG_COLOR = "#D8DEE9"
INPUT_BG = "#4C566A"
BTN_BG = "#5E81AC"
BTN_FG = "#ECEFF4"
NARRATOR_COLOR = "#EBCB8B"
SERVER_COLOR = "#88C0D0"
ERROR_COLOR = "#BF616A"
STORY_COLOR = "#ECEFF4"
TIMER_COLOR = "#D08770"

# Font
FONT_UI = ("Segoe UI", 10)
FONT_STORY = ("Georgia", 12)
FONT_MONO = ("Consolas", 10)
FONT_TIMER = ("Segoe UI", 11, "bold")

# Stati Locali della UI
STATE_VIEWING = "VIEWING"             
STATE_EDITING = "EDITING"             
STATE_WAITING = "WAITING"             
STATE_DECIDING = "DECIDING"           
STATE_DECIDING_CONTINUE = "DECIDING_CONTINUE" 
STATE_VOTING = "VOTING"              

class StoryClientGUI:
    """
    Gestisce l'interfaccia grafica (Tkinter) e la logica client.
    Separa il Thread della UI (MainLoop) dai Thread di rete (Listen/Heartbeat).
    """
    def __init__(self, master):
        self.master = master
        master.title("Distributed Storytelling Client")
        master.geometry("850x700")
        master.configure(bg=BG_COLOR)

        # Stato della connessione e del gioco
        self.sock = None
        self.username = ""
        self.is_leader = False
        self.am_i_narrator = False
        self.is_spectator = False
        self.game_running = False
        self.phase = STATE_VIEWING
        
        self.running = True
        self.reconnecting = False 
        self.intentional_exit = False 
        
        # Gestione Timer UI
        self.timer_left = 0
        self.timer_job = None

        self._setup_ui()

        self.master.after(100, self.initial_connect)

    def _setup_ui(self):
        """Inizializza i widget della GUI."""
        self.header_lbl = tk.Label(self.master, text="DISTRIBUTED STORYTELLING", bg=BG_COLOR, fg=SERVER_COLOR, font=("Segoe UI", 14, "bold"))
        self.header_lbl.pack(pady=(15, 5))

        self.text_frame = tk.Frame(self.master, bg=BG_COLOR)
        self.text_frame.pack(padx=20, pady=5, fill=tk.BOTH, expand=True)

        self.text_area = scrolledtext.ScrolledText(self.text_frame, state='disabled', wrap=tk.WORD, bg=TEXT_BG, fg=FG_COLOR, insertbackground="white", font=FONT_STORY, bd=0, highlightthickness=1, highlightbackground=INPUT_BG)
        self.text_area.pack(fill=tk.BOTH, expand=True)
        
        self.text_area.tag_config("server", foreground=SERVER_COLOR, font=FONT_MONO)
        self.text_area.tag_config("error", foreground=ERROR_COLOR, font=FONT_MONO)
        self.text_area.tag_config("narrator", foreground=NARRATOR_COLOR, font=("Georgia", 12, "bold"))
        self.text_area.tag_config("story", foreground=STORY_COLOR, font=("Georgia", 13, "italic"))
        self.text_area.tag_config("info", foreground="gray", font=FONT_MONO)
        self.text_area.tag_config("highlight", background=NARRATOR_COLOR, foreground=BG_COLOR)

        self.timer_lbl = tk.Label(self.master, text="", bg=BG_COLOR, fg=TIMER_COLOR, font=FONT_TIMER)
        self.timer_lbl.pack(pady=(5, 0))

        self.input_frame = tk.Frame(self.master, bg=BG_COLOR)
        self.input_frame.pack(padx=20, pady=(5, 20), fill=tk.X)

        self.entry_field = tk.Entry(self.input_frame, font=("Segoe UI", 12), bg=INPUT_BG, fg=FG_COLOR, insertbackground="white", bd=0, relief=tk.FLAT)
        self.entry_field.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=8, padx=(0, 10))
        self.entry_field.bind("<Return>", self.send_message)

        self.send_btn = tk.Button(self.input_frame, text="INVIA", command=self.send_message_btn, bg=BTN_BG, fg=BTN_FG, font=("Segoe UI", 10, "bold"), activebackground=SERVER_COLOR, bd=0, cursor="hand2")
        self.send_btn.pack(side=tk.RIGHT, ipadx=15, ipady=5)

        self.status_lbl = tk.Label(self.master, text="Non Connesso", bg="#252A34", fg="gray", font=("Consolas", 9), anchor=tk.W, padx=10, pady=5)
        self.status_lbl.pack(side=tk.BOTTOM, fill=tk.X)

    # ==========================================
    # GESTIONE CONNESSIONE
    # ==========================================
    def initial_connect(self):
        self.username = simpledialog.askstring("Login", "Inserisci Username:", parent=self.master)
        if not self.username:
            self.master.destroy()
            return
        self.connect_to_server()

    def connect_to_server(self):
        """Stabilisce la connessione TCP e avvia i thread di background."""
        try:
            if self.sock: self.sock.close()
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(5)
            self.sock.connect((HOST, PORT))
            self.sock.settimeout(None)
            
            self.running = True
            self.reconnecting = False
            self.intentional_exit = False
            
            threading.Thread(target=self.listen_thread, daemon=True).start()
            threading.Thread(target=self.heartbeat_loop, daemon=True).start()
            
            send_json(self.sock, {"type": CMD_JOIN, "username": self.username})
            self.update_status(f"Connesso come: {self.username}")
            self.log("[SISTEMA] Connessione stabilita.", "server")
            self.enable_input()
            
        except Exception as e:
            if not self.reconnecting:
                self.handle_connection_loss()

    def handle_connection_loss(self):
        """Gestisce la disconnessione e avvia il tentativo di riconnessione."""
        if self.intentional_exit or self.reconnecting: return
        
        self.reconnecting = True
        self.running = False
        
        self.log("\n[!] Connessione persa. Riconnessione tra 3s...", "error")
        self.status_lbl.config(fg=ERROR_COLOR, text="RICONNESSIONE IN CORSO...")
        self.disable_input()
        self.stop_timer()
        
        threading.Thread(target=self.reconnect_loop, daemon=True).start()

    def reconnect_loop(self):
        while self.reconnecting:
            time.sleep(3)
            try:
                temp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                temp_sock.settimeout(2)
                temp_sock.connect((HOST, PORT))
                temp_sock.close()
                self.master.after(0, self.connect_to_server)
                return
            except: pass 

    def listen_thread(self):
        """Loop di ascolto messaggi dal server."""
        while self.running:
            try:
                msg = recv_json(self.sock)
                if not msg: raise Exception("Disconnesso")
                self.master.after(0, self.process_incoming_message, msg)
            except:
                if self.intentional_exit: break
                if self.running: self.master.after(0, self.handle_connection_loss)
                break

    def heartbeat_loop(self):
        """Invia heartbeat periodico per mantenere la connessione."""
        while self.running:
            try:
                time.sleep(3)
                send_json(self.sock, {"type": CMD_HEARTBEAT})
            except: break

    # ==========================================
    # GESTIONE TIMER E UI UTILS
    # ==========================================
    def start_timer(self, seconds):
        self.stop_timer()
        if seconds and seconds > 0:
            self.timer_left = seconds
            self.tick_timer()
        else: self.timer_lbl.config(text="")

    def stop_timer(self):
        if self.timer_job:
            self.master.after_cancel(self.timer_job)
            self.timer_job = None
        self.timer_lbl.config(text="")

    def tick_timer(self):
        """Aggiorna il timer. Se scade, blocca l'input localmente."""
        if self.timer_left > 0:
            self.timer_lbl.config(text=f"Tempo rimanente: {self.timer_left}s")
            self.timer_left -= 1
            self.timer_job = self.master.after(1000, self.tick_timer)
        else:
            self.timer_lbl.config(text="Tempo scaduto!")
            self.timer_job = None
            
            if self.phase == STATE_EDITING:
                self.log("[INFO] Tempo scaduto! Invio bloccato.", "info")
                self.disable_input()
                self.phase = STATE_WAITING

    # ==========================================
    # LOGICA DI GIOCO (Gestione Messaggi)
    # ==========================================
    def process_incoming_message(self, msg):
        msg_type = msg.get('type')
        timeout = msg.get('timeout', 0)
        
        if timeout: self.start_timer(timeout)
        else: self.stop_timer()

        # --- SETUP PARTITA ---
        if msg_type == EVT_WELCOME:
            self.is_leader = msg.get('is_leader')
            self.log(f"Benvenuto, {self.username}.", "server")
            if self.is_leader: self.log(">>> SEI IL LEADER. Scrivi '/start'.", "highlight")
            self.update_status()

        elif msg_type == EVT_GAME_STARTED:
            self.game_running = True
            self.am_i_narrator = msg.get('am_i_narrator', False)
            self.is_spectator = msg.get('is_spectator', False)
            self.phase = STATE_VIEWING
            self.clear_screen()
            self.log(f"TEMA: {msg.get('theme')}", "narrator")
            
            if self.is_spectator: self.log("[INFO] Spettatore.", "info")
            elif self.am_i_narrator: self.log("[RUOLO] NARRATORE.", "narrator")
            else: self.log("[RUOLO] SCRITTORE.", "info")
            
            self.update_status()
            self.disable_input()

        # --- FASE DI SCRITTURA ---
        elif msg_type == EVT_NEW_SEGMENT:
            self.log(f"\n--- Segmento {msg.get('segment_id')} ---", "info")
            if self.is_spectator or self.am_i_narrator:
                self.phase = STATE_VIEWING
                self.log("Gli scrittori stanno scrivendo...", "info")
                self.disable_input()
            else:
                self.phase = STATE_EDITING
                self.log(">>> SCRIVI LA TUA PROPOSTA:", "highlight")
                self.enable_input()
                self.entry_field.focus()
            self.update_status()

        # --- FASE DI SCELTA (NARRATORE) ---
        elif msg_type == EVT_NARRATOR_DECISION_NEEDED:
            if self.am_i_narrator:
                self.phase = STATE_DECIDING
                proposals = msg.get('proposals')
                self.log("\n*** TOCCA A TE SCEGLIERE ***", "narrator")
                for p in proposals:
                    self.log(f"[{p['id']}] {p['author']}: {p['text']}", "story")
                self.enable_input()
                self.entry_field.focus()
                self.update_status()

        elif msg_type == EVT_STORY_UPDATE:
            self.log("\nAGGIORNAMENTO STORIA:", "server")
            for line in msg.get('story'): self.log(f"{line}", "story")
            self.disable_input()

        # --- DECISIONI & VOTAZIONI ---
        elif msg_type == EVT_ASK_CONTINUE:
            self.phase = STATE_DECIDING_CONTINUE
            self.log("\nVuoi continuare la storia? (C/F)", "highlight")
            self.enable_input()
            self.entry_field.focus()
            self.update_status()

        elif msg_type == EVT_GAME_ENDED:
            self.game_running = False
            self.phase = STATE_VOTING
            self.is_spectator = False 
            self.log("\n=== FINE DELLA STORIA ===", "server")
            self.log("Votazione Riavvio: (S = Sì, N = No).", "highlight")
            self.enable_input()
            self.entry_field.focus()
            self.update_status()

        elif msg_type == EVT_VOTE_UPDATE:
            self.log(f"[SISTEMA] Voti ricevuti: {msg.get('count')} / {msg.get('needed')}", "info")

        # --- STATI DI SISTEMA / ERRORI ---
        elif msg_type == EVT_RETURN_TO_LOBBY:
            self.game_running = False
            self.phase = STATE_VIEWING
            self.is_spectator = False
            self.am_i_narrator = False
            self.log("\n--- SEI IN LOBBY ---", "server")
            if msg.get('msg'): self.log(f"ALERT: {msg.get('msg')}", "error")
            
            if self.is_leader:
                self.log("Leader: Scrivi '/start'.", "highlight")
                self.enable_input()
            else:
                self.log("Attendi che il Leader avvii...", "info")
                self.disable_input()
            self.update_status()

        elif msg_type == EVT_LEADER_UPDATE:
            self.is_leader = True
            self.log(f"\n[INFO] {msg.get('msg')}", "server")
            self.enable_input()
            self.update_status()

        elif msg_type == EVT_GOODBYE:
             self.log(f"\n{msg.get('msg')}", "server")
             self.disable_input()
             self.intentional_exit = True
             self.running = False
             if self.sock: 
                 try: self.sock.close()
                 except: pass
             self.master.after(2000, self.master.destroy)

        elif msg_type == "ERROR":
            self.log(f"[ERRORE] {msg.get('msg')}", "error")

    # ==========================================
    # GESTIONE INPUT UTENTE
    # ==========================================
    def send_message_btn(self): self.send_message(None)
    
    def send_message(self, event):
        text = self.entry_field.get().strip()
        if not text: return
        self.entry_field.delete(0, tk.END)

        # Comandi Sistema
        if text.lower() == "/quit": 
            self.intentional_exit = True
            self.master.destroy()
            return

        if text.lower() == "/start":
            if self.is_leader and not self.game_running: 
                send_json(self.sock, {"type": CMD_START_GAME})
            else: 
                self.log("Non puoi avviare.", "error")
            return

        if self.phase == STATE_EDITING:
            send_json(self.sock, {"type": CMD_SUBMIT, "text": text})
            self.phase = STATE_WAITING
            self.log(f"Tu: {text}", "info")
            self.disable_input()
            self.stop_timer() 
            self.update_status()
            
        elif self.phase == STATE_DECIDING and self.am_i_narrator:
            try:
                pid = int(text)
                send_json(self.sock, {"type": CMD_SELECT_PROPOSAL, "proposal_id": pid})
                self.phase = STATE_VIEWING
                self.log(f"Scelta #{pid}.", "info")
                self.disable_input()
                self.stop_timer()
                self.update_status()
            except: self.log("Numero non valido.", "error")
            
        elif self.phase == STATE_DECIDING_CONTINUE:
            t = text.upper()
            if t == "C": 
                send_json(self.sock, {"type": CMD_DECIDE_CONTINUE, "action": "CONTINUE"})
                self.phase = STATE_VIEWING; self.disable_input(); self.stop_timer()
            elif t == "F": 
                send_json(self.sock, {"type": CMD_DECIDE_CONTINUE, "action": "STOP"})
                self.phase = STATE_VIEWING; self.disable_input(); self.stop_timer()
            else: self.log("Usa 'C' o 'F'.", "error")
            self.update_status()
            
        elif self.phase == STATE_VOTING:
            t = text.upper()
            if t == "S": 
                send_json(self.sock, {"type": CMD_VOTE_RESTART})
                self.log("Voto SÌ.", "info"); self.stop_timer()
            elif t == "N": 
                send_json(self.sock, {"type": CMD_VOTE_NO})
                self.log("Voto NO.", "info"); self.stop_timer()
            else: self.log("Usa 'S' o 'N'.", "error")

        elif self.phase == STATE_VIEWING:
             if not (self.is_leader and not self.game_running):
                 self.log("Non puoi scrivere adesso.", "error")

    # ==========================================
    # UTILITIES GRAFICHE
    # ==========================================
    def log(self, text, tag=None):
        """Scrive nel box testuale principale."""
        self.text_area.config(state='normal')
        self.text_area.insert(tk.END, text + "\n", tag)
        self.text_area.see(tk.END)
        self.text_area.config(state='disabled')
        
    def update_status(self, text=None):
        if text: 
            self.status_lbl.config(text=text)
            return
        role = "Spettatore" if self.is_spectator else "NARRATORE" if self.am_i_narrator else "Scrittore" if self.game_running else "Utente"
        extra = " [LEADER]" if self.is_leader else ""
        self.status_lbl.config(text=f"{self.username} | {role}{extra} | {self.phase}")

    def clear_screen(self):
        self.text_area.config(state='normal')
        self.text_area.delete(1.0, tk.END)
        self.text_area.config(state='disabled')

    def disable_input(self):
        if self.phase == STATE_VIEWING and self.is_leader and not self.game_running: 
            self.enable_input()
            return
        self.entry_field.config(state='disabled', bg=BG_COLOR)
        self.send_btn.config(state='disabled', bg=BG_COLOR)

    def enable_input(self):
        self.entry_field.config(state='normal', bg=INPUT_BG)
        self.send_btn.config(state='normal', bg=BTN_BG)

if __name__ == "__main__":
    root = tk.Tk()
    app = StoryClientGUI(root)
    root.mainloop()