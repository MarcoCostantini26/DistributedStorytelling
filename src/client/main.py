import socket
import threading
import sys
import os
import time

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from common.protocol import *

HOST = '127.0.0.1'
PORT = 65432

STATE_VIEWING = "VIEWING"
STATE_EDITING = "EDITING"
STATE_WAITING = "WAITING"
STATE_DECIDING = "DECIDING"
STATE_DECIDING_CONTINUE = "DECIDING_CONTINUE"
STATE_VOTING = "VOTING"

# --- TIMER ---
class InputTimer:
    def __init__(self):
        self._stop_event = threading.Event()
        self._thread = None
    def start(self, duration):
        self.stop()
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, args=(duration,), daemon=True)
        self._thread.start()
    def stop(self):
        if self._thread:
            self._stop_event.set()
            self._thread.join(timeout=0.01)
            self._thread = None
    def _run(self, duration):
        remaining = duration
        while remaining > 0:
            if self._stop_event.is_set(): return
            if remaining == 60: print(f"\n[TIMER] ⏳ 60s...", end="", flush=True)
            elif remaining == 30: print(f"\n[TIMER] ⏳ 30s...", end="", flush=True)
            elif remaining == 10: print(f"\n[TIMER] ⚠️ 10s!", end="", flush=True)
            elif remaining <= 5: print(f"\n[TIMER] {remaining}...", end="", flush=True)
            time.sleep(1)
            remaining -= 1
        if not self._stop_event.is_set(): print("\n[TIMER] ⏰ TEMPO SCADUTO!", flush=True)

class ClientState:
    def __init__(self):
        self.is_leader = False
        self.am_i_narrator = False
        self.is_spectator = False
        self.game_running = False
        self.phase = STATE_VIEWING

state = ClientState()
cli_timer = InputTimer()
sock = None 

# --- HEARTBEAT ---
def heartbeat_loop(sock_ref):
    """Invia heartbeat finché il socket è valido."""
    while True:
        time.sleep(3)
        try:
            if sock_ref: send_json(sock_ref, {"type": CMD_HEARTBEAT})
            else: break
        except: break

def listen_from_server(sock_ref):
    global sock
    while True:
        try:
            msg = recv_json(sock_ref)
            if not msg: raise Exception("Server closed")
            
            # (Codice gestione messaggi identico a prima...)
            # Per brevità copio solo la logica base, il resto è uguale
            msg_type = msg.get('type')
            timeout = msg.get('timeout', 0)
            cli_timer.stop()

            if msg_type == EVT_GAME_STARTED:
                state.game_running = True
                state.am_i_narrator = msg.get('am_i_narrator', False)
                state.is_spectator = msg.get('is_spectator', False)
                state.phase = STATE_VIEWING
                print(f"\n[INFO] Inizio storia! Tema: {msg.get('theme')}")
                if state.is_spectator: print("[RUOLO] Spettatore.")
                elif state.am_i_narrator: print("[RUOLO] NARRATORE.")
                else: print("[RUOLO] SCRITTORE.")

            elif msg_type == EVT_NEW_SEGMENT:
                print(f"\n--- INIZIO SEGMENTO {msg.get('segment_id')} ---")
                if state.is_spectator:
                    state.phase = STATE_VIEWING
                    print("(Spettatore) In attesa...")
                elif state.am_i_narrator:
                    state.phase = STATE_VIEWING
                    print("In attesa scrittori...")
                else:
                    state.phase = STATE_EDITING
                    if timeout: print(f"[TIMER] 🕒 Hai {timeout}s!"); cli_timer.start(timeout)
                    print(">>> TOCCA A TE! Scrivi: <<<")

            elif msg_type == EVT_NARRATOR_DECISION_NEEDED:
                if state.am_i_narrator:
                    state.phase = STATE_DECIDING
                    proposals = msg.get('proposals')
                    print("\n*** SCEGLI PROPOSTA ***")
                    if timeout: print(f"[TIMER] 🕒 Hai {timeout}s!"); cli_timer.start(timeout)
                    for p in proposals: print(f"[{p['id']}] {p['author']}: {p['text']}")
                    print(">>> Numero proposta: <<<")

            elif msg_type == EVT_STORY_UPDATE:
                print("\nSTORIA AGGIORNATA:")
                for line in msg.get('story'): print(f" > {line}")

            elif msg_type == EVT_ASK_CONTINUE:
                print("\nSTORIA AGGIORNATA. Vuoi continuare?")
                if timeout: print(f"[TIMER] 🕒 Auto-continue in {timeout}s."); cli_timer.start(timeout)
                print("Scrivi 'C' (Continua) o 'F' (Finisci).")
                state.phase = STATE_DECIDING_CONTINUE

            elif msg_type == EVT_GAME_ENDED:
                print("\n=== PARTITA FINITA ===")
                state.game_running = False
                state.phase = STATE_VOTING
                state.is_spectator = False 
                print("\n[VOTAZIONE] Rigiocare?")
                if timeout: print(f"[TIMER] 🕒 {timeout}s per votare."); cli_timer.start(timeout)
                print(">>> 'S' (Sì) / 'N' (No) <<<")

            elif msg_type == EVT_VOTE_UPDATE:
                print(f"[VOTO] {msg.get('count')}/{msg.get('needed')}")

            elif msg_type == EVT_RETURN_TO_LOBBY:
                cli_timer.stop()
                state.game_running = False
                state.phase = STATE_VIEWING
                state.is_spectator = False
                state.am_i_narrator = False
                print("\n--- IN LOBBY ---")
                if msg.get('msg'): print(f"MSG: {msg.get('msg')}")
                if state.is_leader: print("LEADER: Scrivi '/start'")
                else: print("Attendi avvio...")
            
            elif msg_type == EVT_LEADER_UPDATE:
                state.is_leader = True
                print(f"\n[INFO] {msg.get('msg')}")

            elif msg_type == EVT_GOODBYE:
                cli_timer.stop()
                print(f"\n[SERVER] {msg.get('msg')}")
                os._exit(0)

            elif msg_type == EVT_WELCOME:
                state.is_leader = msg.get('is_leader')
                print(f"[SERVER] {msg.get('msg')}")
                if state.is_leader: print("Digita '/start'.")

        except:
            print("\n[!] Connessione persa. Riconnessione in corso...", flush=True)
            reconnect_loop(username_cache)
            break

username_cache = ""

def reconnect_loop(username):
    global sock
    while True:
        time.sleep(3)
        try:
            new_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            new_sock.settimeout(2)
            new_sock.connect((HOST, PORT))
            new_sock.settimeout(None)
            
            sock = new_sock
            print("[INFO] Riconnesso al server!", flush=True)
            
            # Rilancia i thread
            threading.Thread(target=listen_from_server, args=(sock,), daemon=True).start()
            threading.Thread(target=heartbeat_loop, args=(sock,), daemon=True).start()
            
            send_json(sock, {"type": CMD_JOIN, "username": username})
            return
        except:
            pass

def start_client():
    global sock, username_cache
    print("--- CLIENT (CLI) ---")
    username_cache = input("Username: ")
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect((HOST, PORT))
        threading.Thread(target=listen_from_server, args=(sock,), daemon=True).start()
        threading.Thread(target=heartbeat_loop, args=(sock,), daemon=True).start()
        send_json(sock, {"type": CMD_JOIN, "username": username_cache})
    except:
        print("[ERRORE] Server non trovato. Riprovo...", flush=True)
        reconnect_loop(username_cache)

    while True:
        try:
            if not sock: 
                time.sleep(1)
                continue
                
            user_input = input()
            cli_timer.stop()
            if not user_input: continue

            if user_input.lower() == "/quit": break
            
            try:
                if user_input.lower() == "/start":
                    if state.is_leader and not state.game_running: send_json(sock, {"type": CMD_START_GAME})
                    else: print("[INFO] Non puoi avviare.")
                    continue

                if state.phase == STATE_VOTING:
                    if user_input.upper() == "S": send_json(sock, {"type": CMD_VOTE_RESTART}); print("Voto SI.")
                    elif user_input.upper() == "N": send_json(sock, {"type": CMD_VOTE_NO}); print("Voto NO.")
                    else: print("Scrivi 'S' o 'N'.")
                
                elif state.phase == STATE_DECIDING_CONTINUE:
                    if user_input.upper() == "C": send_json(sock, {"type": CMD_DECIDE_CONTINUE, "action": "CONTINUE"}); state.phase = STATE_VIEWING
                    elif user_input.upper() == "F": send_json(sock, {"type": CMD_DECIDE_CONTINUE, "action": "STOP"}); state.phase = STATE_VIEWING
                    else: print("Scrivi 'C' o 'F'.")

                elif state.phase == STATE_DECIDING and state.am_i_narrator:
                    try:
                        send_json(sock, {"type": CMD_SELECT_PROPOSAL, "proposal_id": int(user_input)})
                        state.phase = STATE_VIEWING
                        print("Scelta inviata...")
                    except: print("Inserisci numero.")

                elif state.phase == STATE_EDITING:
                     send_json(sock, {"type": CMD_SUBMIT, "text": user_input})
                     state.phase = STATE_WAITING
                     print("Inviato!")

            except (BrokenPipeError, ConnectionResetError):
                print("[!] Errore invio. Riconnessione...", flush=True)
                # Il listener gestirà il reconnect
                time.sleep(1)

        except: break
    if sock: sock.close()

if __name__ == "__main__":
    start_client()