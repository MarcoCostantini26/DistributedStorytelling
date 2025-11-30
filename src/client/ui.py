import tkinter as tk
from tkinter import scrolledtext, messagebox, simpledialog
import socket
import threading
import json
import sys
import os

# --- SETUP IMPORTAZIONI ---
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from common.protocol import *

HOST = '127.0.0.1'
PORT = 65432

# --- TEMA DARK & STILE ---
BG_COLOR = "#2E3440"        # Sfondo Finestra (Grigio Scuro)
TEXT_BG = "#3B4252"         # Sfondo Area Testo
FG_COLOR = "#D8DEE9"        # Testo Principale (Bianco sporco)
INPUT_BG = "#4C566A"        # Sfondo Input
BTN_BG = "#5E81AC"          # Blu Nordico
BTN_FG = "#ECEFF4"          # Testo Bottone
NARRATOR_COLOR = "#EBCB8B"  # Oro/Giallo
SERVER_COLOR = "#88C0D0"    # Ciano
ERROR_COLOR = "#BF616A"     # Rosso
STORY_COLOR = "#ECEFF4"     # Bianco brillante

FONT_UI = ("Segoe UI", 10)
FONT_STORY = ("Georgia", 12)
FONT_MONO = ("Consolas", 10)

# Stati (uguali al CLI)
STATE_VIEWING = "VIEWING"
STATE_EDITING = "EDITING"
STATE_WAITING = "WAITING"
STATE_DECIDING = "DECIDING"
STATE_DECIDING_CONTINUE = "DECIDING_CONTINUE"
STATE_VOTING = "VOTING"

class StoryClientGUI:
    def __init__(self, master):
        self.master = master
        master.title("Distributed Storytelling Client")
        master.geometry("850x650")
        master.configure(bg=BG_COLOR)

        # --- STATO ---
        self.sock = None
        self.username = ""
        self.is_leader = False
        self.am_i_narrator = False
        self.is_spectator = False
        self.game_running = False
        self.phase = STATE_VIEWING
        self.running = True

        # --- UI LAYOUT ---

        # 1. Header
        self.header_lbl = tk.Label(
            master, text="DISTRIBUTED STORYTELLING", 
            bg=BG_COLOR, fg=SERVER_COLOR, 
            font=("Segoe UI", 14, "bold")
        )
        self.header_lbl.pack(pady=(15, 5))

        # 2. Area Testo (Frame per padding)
        self.text_frame = tk.Frame(master, bg=BG_COLOR)
        self.text_frame.pack(padx=20, pady=10, fill=tk.BOTH, expand=True)

        self.text_area = scrolledtext.ScrolledText(
            self.text_frame, 
            state='disabled', 
            wrap=tk.WORD, 
            bg=TEXT_BG, 
            fg=FG_COLOR,
            insertbackground="white",
            font=FONT_STORY,
            bd=0, 
            highlightthickness=1, 
            highlightbackground=INPUT_BG
        )
        self.text_area.pack(fill=tk.BOTH, expand=True)
        
        # Tag Stili
        self.text_area.tag_config("server", foreground=SERVER_COLOR, font=FONT_MONO)
        self.text_area.tag_config("error", foreground=ERROR_COLOR, font=FONT_MONO)
        self.text_area.tag_config("narrator", foreground=NARRATOR_COLOR, font=("Georgia", 12, "bold"))
        self.text_area.tag_config("story", foreground=STORY_COLOR, font=("Georgia", 13, "italic"))
        self.text_area.tag_config("info", foreground="gray", font=FONT_MONO)
        self.text_area.tag_config("highlight", background=NARRATOR_COLOR, foreground=BG_COLOR)

        # 3. Area Input
        self.input_frame = tk.Frame(master, bg=BG_COLOR)
        self.input_frame.pack(padx=20, pady=(0, 20), fill=tk.X)

        self.entry_field = tk.Entry(
            self.input_frame, 
            font=("Segoe UI", 12), 
            bg=INPUT_BG, 
            fg=FG_COLOR,
            insertbackground="white",
            bd=0, relief=tk.FLAT
        )
        self.entry_field.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=8, padx=(0, 10))
        self.entry_field.bind("<Return>", self.send_message)

        self.send_btn = tk.Button(
            self.input_frame, 
            text="INVIA", 
            command=self.send_message_btn, 
            bg=BTN_BG, fg=BTN_FG,
            font=("Segoe UI", 10, "bold"),
            activebackground=SERVER_COLOR,
            bd=0, cursor="hand2"
        )
        self.send_btn.pack(side=tk.RIGHT, ipadx=15, ipady=5)

        # 4. Status Bar
        self.status_lbl = tk.Label(
            master, 
            text="Non Connesso", 
            bg="#252A34", fg="gray", 
            font=("Consolas", 9),
            anchor=tk.W, padx=10, pady=5
        )
        self.status_lbl.pack(side=tk.BOTTOM, fill=tk.X)

        # Avvio connessione ritardato
        self.master.after(100, self.connect_to_server)

    # --- LOGICA DI RETE ---

    def connect_to_server(self):
        self.username = simpledialog.askstring("Login", "Inserisci Username:", parent=self.master)
        if not self.username:
            self.master.destroy()
            return

        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((HOST, PORT))
            threading.Thread(target=self.listen_thread, daemon=True).start()
            send_json(self.sock, {"type": CMD_JOIN, "username": self.username})
            self.update_status(f"Connesso come: {self.username}")
        except Exception as e:
            messagebox.showerror("Errore", f"Impossibile connettersi al server.\n{e}")
            self.master.destroy()

    def listen_thread(self):
        while self.running:
            try:
                msg = recv_json(self.sock)
                if not msg: break
                self.master.after(0, self.process_incoming_message, msg)
            except Exception:
                break
        self.master.after(0, self.on_disconnect)

    def on_disconnect(self):
        if self.running:
            self.log("\n--- DISCONNESSO DAL SERVER ---", "error")
            self.disable_input()
            self.status_lbl.config(fg=ERROR_COLOR, text="DISCONNESSO")
            self.running = False

    # --- GESTIONE MESSAGGI ---

    def process_incoming_message(self, msg):
        msg_type = msg.get('type')

        if msg_type == EVT_WELCOME:
            self.is_leader = msg.get('is_leader')
            self.log(f"Benvenuto, {self.username}.", "server")
            self.log("-" * 40, "info")
            if self.is_leader:
                self.log(">>> SEI IL LEADER. Scrivi '/start' per iniziare.", "highlight")
            self.update_status()

        elif msg_type == EVT_GAME_STARTED:
            self.game_running = True
            self.am_i_narrator = msg.get('am_i_narrator', False)
            self.is_spectator = msg.get('is_spectator', False)
            self.phase = STATE_VIEWING
            
            self.clear_screen()
            self.log(f"CAPITOLO 1: {msg.get('theme')}", "narrator")
            self.log("-" * 40, "info")
            
            if self.is_spectator:
                self.log("[INFO] Sei entrato come SPETTATORE.", "info")
            elif self.am_i_narrator:
                self.log("[RUOLO] Sei il NARRATORE. Guida la storia.", "narrator")
            else:
                self.log("[RUOLO] Sei uno SCRITTORE.", "info")
            
            self.update_status()
            self.disable_input()

        elif msg_type == EVT_NEW_SEGMENT:
            self.log(f"\n--- Segmento {msg.get('segment_id')} ---", "info")
            if self.is_spectator:
                self.phase = STATE_VIEWING
                self.log("In attesa degli scrittori...", "info")
                self.disable_input()
            elif self.am_i_narrator:
                self.phase = STATE_VIEWING
                self.log("Gli scrittori stanno scrivendo...", "info")
                self.disable_input()
            else:
                self.phase = STATE_EDITING
                self.log(">>> SCRIVI LA TUA PROPOSTA:", "highlight")
                self.enable_input()
                self.entry_field.focus()

        elif msg_type == EVT_NARRATOR_DECISION_NEEDED:
            if self.am_i_narrator:
                self.phase = STATE_DECIDING
                proposals = msg.get('proposals')
                self.log("\n*** TOCCA A TE SCEGLIERE ***", "narrator")
                self.log("Scrivi il numero della proposta migliore:\n", "narrator")
                for p in proposals:
                    self.log(f"[{p['id']}] {p['author']}: {p['text']}", "story")
                self.enable_input()
                self.entry_field.focus()

        elif msg_type == EVT_STORY_UPDATE:
            self.log("\nAGGIORNAMENTO STORIA:", "server")
            for line in msg.get('story'):
                self.log(f"{line}", "story")
            self.disable_input()

        elif msg_type == EVT_ASK_CONTINUE:
            self.phase = STATE_DECIDING_CONTINUE
            self.log("\nVuoi continuare la storia?", "highlight")
            self.log("Scrivi 'C' per Continuare o 'F' per Finire.", "info")
            self.enable_input()
            self.entry_field.focus()

        elif msg_type == EVT_GAME_ENDED:
            self.game_running = False
            self.phase = STATE_VOTING
            self.is_spectator = False 
            self.log("\n=== FINE DELLA STORIA ===", "server")
            self.log("Votazione Riavvio: Scrivi 'S' (Sì) o 'N' (No).", "highlight")
            self.enable_input()
            self.entry_field.focus()

        elif msg_type == EVT_VOTE_UPDATE:
            self.log(f"[SISTEMA] Voti ricevuti: {msg.get('count')} / {msg.get('needed')}", "info")

        elif msg_type == EVT_RETURN_TO_LOBBY:
            self.game_running = False
            self.phase = STATE_VIEWING
            self.is_spectator = False
            self.am_i_narrator = False
            self.log("\n--- SEI IN LOBBY ---", "server")
            if self.is_leader:
                self.log("Leader: Scrivi '/start' per una nuova partita.", "highlight")
                self.enable_input()
            else:
                self.log("Attendi che il Leader avvii...", "info")
                self.disable_input()
            self.update_status()

        elif msg_type == EVT_LEADER_UPDATE:
            self.is_leader = True
            self.log(f"\n[INFO] {msg.get('msg')}", "server")
            self.log("Comando '/start' sbloccato.", "highlight")
            self.enable_input()

        elif msg_type == EVT_GOODBYE:
             self.log("\n" + "*"*30, "info")
             self.log(f"{msg.get('msg')}", "server")
             self.log("*"*30, "info")
             self.disable_input()
             self.running = False
             self.sock.close()

        elif msg_type == "ERROR":
            self.log(f"[ERRORE] {msg.get('msg')}", "error")

    # --- GESTIONE INPUT ---

    def send_message_btn(self):
        self.send_message(None)

    def send_message(self, event):
        text = self.entry_field.get().strip()
        if not text: return

        # --- FIX: CANCELLA SUBITO IL TESTO ---
        self.entry_field.delete(0, tk.END)
        # -------------------------------------

        # Comandi Sistema
        if text.lower() == "/quit":
            self.master.destroy()
            return

        if text.lower() == "/start":
            if self.is_leader and not self.game_running:
                send_json(self.sock, {"type": CMD_START_GAME})
            else:
                self.log("Non puoi avviare ora.", "error")
            return

        # Fasi di Gioco
        if self.phase == STATE_EDITING:
            send_json(self.sock, {"type": CMD_SUBMIT, "text": text})
            self.phase = STATE_WAITING
            self.log(f"Tu: {text}", "info")
            self.disable_input()

        elif self.phase == STATE_DECIDING and self.am_i_narrator:
            try:
                pid = int(text)
                send_json(self.sock, {"type": CMD_SELECT_PROPOSAL, "proposal_id": pid})
                self.phase = STATE_VIEWING
                self.log(f"Hai scelto la proposta #{pid}.", "info")
                self.disable_input()
            except ValueError:
                self.log("Devi inserire un numero.", "error")
                return

        elif self.phase == STATE_DECIDING_CONTINUE:
            t = text.upper()
            if t == "C":
                send_json(self.sock, {"type": CMD_DECIDE_CONTINUE, "action": "CONTINUE"})
                self.phase = STATE_VIEWING
                self.disable_input()
            elif t == "F":
                send_json(self.sock, {"type": CMD_DECIDE_CONTINUE, "action": "STOP"})
                self.phase = STATE_VIEWING
                self.disable_input()
            else:
                self.log("Usa 'C' o 'F'.", "error")
                return

        elif self.phase == STATE_VOTING:
            t = text.upper()
            if t == "S":
                send_json(self.sock, {"type": CMD_VOTE_RESTART})
                self.log("Hai votato SÌ.", "info")
            elif t == "N":
                send_json(self.sock, {"type": CMD_VOTE_NO})
                self.log("Hai votato NO.", "info")
            else:
                self.log("Usa 'S' o 'N'.", "error")
                return 

        elif self.phase == STATE_VIEWING:
             if not (self.is_leader and not self.game_running):
                 self.log("Non puoi scrivere adesso.", "error")

    # --- HELPER ---

    def log(self, text, tag=None):
        self.text_area.config(state='normal')
        self.text_area.insert(tk.END, text + "\n", tag)
        self.text_area.see(tk.END)
        self.text_area.config(state='disabled')

    def update_status(self, text=None):
        if text:
            self.status_lbl.config(text=text)
            return
        
        role = "Utente"
        if self.is_spectator: role = "Spettatore"
        elif self.am_i_narrator: role = "NARRATORE"
        elif self.game_running: role = "Scrittore"
        
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