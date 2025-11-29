import tkinter as tk
from tkinter import scrolledtext, messagebox, simpledialog
import socket
import threading
import json
import sys
import os

# Importiamo il protocollo e le costanti
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from common.protocol import *

HOST = '127.0.0.1'
PORT = 65432

# Definizione stati (copiati dal tuo client CLI)
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
        master.geometry("700x550")

        # --- STATO DEL CLIENT ---
        self.sock = None
        self.username = ""
        self.is_leader = False
        self.am_i_narrator = False
        self.is_spectator = False
        self.game_running = False
        self.phase = STATE_VIEWING
        self.running = True

        # --- UI LAYOUT ---
        
        # 1. Area Testo (Chat/Storia)
        self.text_area = scrolledtext.ScrolledText(master, state='disabled', wrap=tk.WORD, font=("Consolas", 10))
        self.text_area.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
        
        # Configurazione colori (Tag)
        self.text_area.tag_config("server", foreground="blue")
        self.text_area.tag_config("error", foreground="red")
        self.text_area.tag_config("narrator", foreground="purple", font=("Consolas", 10, "bold"))
        self.text_area.tag_config("story", foreground="black", font=("Georgia", 11))
        self.text_area.tag_config("info", foreground="gray")
        self.text_area.tag_config("highlight", background="yellow", foreground="black")

        # 2. Area Input
        self.input_frame = tk.Frame(master)
        self.input_frame.pack(padx=10, pady=5, fill=tk.X)

        self.entry_field = tk.Entry(self.input_frame, font=("Arial", 11))
        self.entry_field.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.entry_field.bind("<Return>", self.send_message) # Invio per spedire

        self.send_btn = tk.Button(self.input_frame, text="INVIA", command=self.send_message_btn, bg="#dddddd")
        self.send_btn.pack(side=tk.RIGHT)

        # 3. Status Bar
        self.status_lbl = tk.Label(master, text="Disconnesso", bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.status_lbl.pack(side=tk.BOTTOM, fill=tk.X)

        # Avvio connessione
        self.connect_to_server()

    # --- LOGICA DI RETE ---

    def connect_to_server(self):
        self.username = simpledialog.askstring("Login", "Inserisci il tuo Username:")
        if not self.username:
            self.master.destroy()
            return

        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((HOST, PORT))
            
            # Thread Listener
            threading.Thread(target=self.listen_thread, daemon=True).start()
            
            # Invio Join
            send_json(self.sock, {"type": CMD_JOIN, "username": self.username})
            self.update_status(f"Connesso come: {self.username}")
            
        except Exception as e:
            messagebox.showerror("Errore", f"Impossibile connettersi: {e}")
            self.master.destroy()

    def listen_thread(self):
        """Thread separato che ascolta il server"""
        while self.running:
            try:
                msg = recv_json(self.sock)
                if not msg: break
                
                # Schedula l'aggiornamento UI nel thread principale
                self.master.after(0, self.process_incoming_message, msg)
            except Exception as e:
                print(f"Errore socket: {e}")
                break
        
        self.master.after(0, self.on_disconnect)

    def on_disconnect(self):
        self.log("--- DISCONNESSO DAL SERVER ---", "error")
        self.disable_input()

    # --- GESTIONE MESSAGGI (Dal Server) ---

    def process_incoming_message(self, msg):
        msg_type = msg.get('type')

        if msg_type == EVT_WELCOME:
            self.is_leader = msg.get('is_leader')
            self.log(f"[SERVER] {msg.get('msg')}", "server")
            if self.is_leader:
                self.log(">>> SEI IL LEADER! Scrivi '/start' per iniziare.", "highlight")
            self.update_status()

        elif msg_type == EVT_GAME_STARTED:
            self.game_running = True
            self.am_i_narrator = msg.get('am_i_narrator', False)
            self.is_spectator = msg.get('is_spectator', False)
            self.phase = STATE_VIEWING
            
            self.clear_screen()
            self.log(f"=== NUOVA STORIA INIZIATA ===", "server")
            self.log(f"TEMA: {msg.get('theme')}", "narrator")
            
            if self.is_spectator:
                self.log("[RUOLO] Spettatore.", "info")
            elif self.am_i_narrator:
                self.log("[RUOLO] SEI IL NARRATORE. Attendi le proposte.", "narrator")
            else:
                self.log("[RUOLO] SEI UNO SCRITTORE.", "info")
            
            self.update_status()
            self.disable_input()

        elif msg_type == EVT_NEW_SEGMENT:
            self.log(f"\n--- INIZIO SEGMENTO {msg.get('segment_id')} ---", "info")
            
            if self.is_spectator:
                self.phase = STATE_VIEWING
                self.log("(Spettatore) In attesa...", "info")
                self.disable_input()
            elif self.am_i_narrator:
                self.phase = STATE_VIEWING
                self.log("In attesa delle proposte degli scrittori...", "info")
                self.disable_input()
            else:
                self.phase = STATE_EDITING
                self.log(">>> TOCCA A TE! Scrivi la continuazione:", "highlight")
                self.enable_input()
                self.entry_field.focus()

        elif msg_type == EVT_NARRATOR_DECISION_NEEDED:
            if self.am_i_narrator:
                self.phase = STATE_DECIDING
                proposals = msg.get('proposals')
                self.log("\n*** SCEGLI LA PROPOSTA MIGLIORE (Scrivi il numero) ***", "narrator")
                for p in proposals:
                    self.log(f"[{p['id']}] {p['author']}: {p['text']}")
                self.enable_input()
                self.entry_field.focus()

        elif msg_type == EVT_STORY_UPDATE:
            self.log("\nSTORIA AGGIORNATA:", "info")
            for line in msg.get('story'):
                self.log(f"> {line}", "story")
            self.disable_input()

        elif msg_type == EVT_ASK_CONTINUE:
            if self.am_i_narrator: # Solitamente decide il narratore, ma dipende dalla tua logica server
                 # Nel tuo codice CLI non c'è check sul ruolo per questo evento, ma assumiamo sia per il narratore
                 pass
            
            # Se la logica server manda questo a tutti o solo al narratore, il client si adatta
            self.phase = STATE_DECIDING_CONTINUE
            self.log("\nVuoi continuare? (C = Continua, F = Finisci)", "highlight")
            self.enable_input()

        elif msg_type == EVT_GAME_ENDED:
            self.game_running = False
            self.phase = STATE_VOTING
            self.is_spectator = False 
            self.log("\n=== PARTITA FINITA ===", "server")
            self.log("Votazione: Vuoi giocare ancora? (S = Sì, N = No)", "highlight")
            self.enable_input()

        elif msg_type == EVT_VOTE_UPDATE:
            self.log(f"[VOTO] Hanno votato {msg.get('count')} / {msg.get('needed')}", "info")

        elif msg_type == EVT_RETURN_TO_LOBBY:
            self.game_running = False
            self.phase = STATE_VIEWING
            self.is_spectator = False
            self.am_i_narrator = False
            self.log("\n--- RITORNO IN LOBBY ---", "server")
            if self.is_leader:
                self.log("Sei il Leader. Scrivi '/start' per iniziare.", "highlight")
                self.enable_input()
            else:
                self.log("In attesa del Leader...", "info")
                self.disable_input()
            self.update_status()

        elif msg_type == EVT_LEADER_UPDATE:
            self.is_leader = True
            self.log(f"[INFO] {msg.get('msg')}", "server")
            self.log("Ora puoi usare '/start'.", "highlight")
            self.enable_input()

        elif msg_type == "ERROR":
            self.log(f"ERRORE: {msg.get('msg')}", "error")

    # --- GESTIONE INPUT UTENTE ---

    def send_message_btn(self):
        self.send_message(None)

    def send_message(self, event):
        text = self.entry_field.get().strip()
        if not text: return

        # 1. Comandi Globali
        if text.lower() == "/quit":
            self.master.destroy()
            return

        if text.lower() == "/start":
            if self.is_leader and not self.game_running:
                send_json(self.sock, {"type": CMD_START_GAME})
                self.entry_field.delete(0, tk.END)
            else:
                self.log("Non puoi avviare ora (Non sei leader o partita in corso).", "error")
            return

        # 2. Gestione Fasi di Gioco (Switch Case su self.phase)
        
        if self.phase == STATE_EDITING:
            send_json(self.sock, {"type": CMD_SUBMIT, "text": text})
            self.phase = STATE_WAITING
            self.log(f"Tu: {text}", "info")
            self.log("Proposta inviata! Attendi...", "info")
            self.disable_input()

        elif self.phase == STATE_DECIDING and self.am_i_narrator:
            try:
                pid = int(text)
                send_json(self.sock, {"type": CMD_SELECT_PROPOSAL, "proposal_id": pid})
                self.phase = STATE_VIEWING
                self.log(f"Hai scelto la proposta {pid}.", "info")
                self.disable_input()
            except ValueError:
                self.log("Inserisci un numero valido.", "error")
                return

        elif self.phase == STATE_DECIDING_CONTINUE:
            t = text.upper()
            if t == "C":
                send_json(self.sock, {"type": CMD_DECIDE_CONTINUE, "action": "CONTINUE"})
                self.log("Hai votato per Continuare.", "info")
                self.phase = STATE_VIEWING
                self.disable_input()
            elif t == "F":
                send_json(self.sock, {"type": CMD_DECIDE_CONTINUE, "action": "STOP"})
                self.log("Hai votato per Finire.", "info")
                self.phase = STATE_VIEWING
                self.disable_input()
            else:
                self.log("Inserisci 'C' o 'F'.", "error")
                return

        elif self.phase == STATE_VOTING:
            t = text.upper()
            if t == "S":
                send_json(self.sock, {"type": CMD_VOTE_RESTART})
                self.log("Voto SI inviato.", "info")
                self.entry_field.delete(0, tk.END)
            elif t == "N":
                send_json(self.sock, {"type": CMD_VOTE_NO})
                self.log("Voto NO inviato.", "info")
                self.entry_field.delete(0, tk.END)
            else:
                self.log("Inserisci 'S' o 'N'.", "error")
                return # Non pulire il campo se errore

        elif self.phase == STATE_VIEWING:
             if self.is_leader and not self.game_running:
                 pass # Lascia scrivere /start
             else:
                 self.log("Non puoi scrivere ora.", "error")

        self.entry_field.delete(0, tk.END)

    # --- HELPER UI ---

    def log(self, text, tag=None):
        self.text_area.config(state='normal')
        self.text_area.insert(tk.END, text + "\n", tag)
        self.text_area.see(tk.END)
        self.text_area.config(state='disabled')

    def update_status(self, text=None):
        if text:
            self.status_lbl.config(text=text)
            return
        
        # Auto-generate status text
        role = "Utente"
        if self.is_spectator: role = "Spettatore"
        elif self.am_i_narrator: role = "NARRATORE"
        elif self.game_running: role = "Scrittore"
        
        extra = " (LEADER)" if self.is_leader else ""
        self.status_lbl.config(text=f"{self.username} | {role}{extra} | Fase: {self.phase}")

    def clear_screen(self):
        self.text_area.config(state='normal')
        self.text_area.delete(1.0, tk.END)
        self.text_area.config(state='disabled')

    def disable_input(self):
        # Disabilita l'input ma lascia abilitato se sei leader in lobby per scrivere /start
        if self.phase == STATE_VIEWING and self.is_leader and not self.game_running:
            self.enable_input()
            return
            
        self.entry_field.config(state='disabled')
        self.send_btn.config(state='disabled')

    def enable_input(self):
        self.entry_field.config(state='normal')
        self.send_btn.config(state='normal')

if __name__ == "__main__":
    root = tk.Tk()
    app = StoryClientGUI(root)
    root.mainloop()