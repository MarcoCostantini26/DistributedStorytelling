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

sock = None
intentional_exit = False

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
        if self._thread and self._thread.is_alive():
            self._stop_event.set()
            self._thread.join(timeout=0.1)
            self._thread = None
            
    def _run(self, duration):
        remaining = duration
        self._print_time(remaining)
        
        while remaining > 0:
            if self._stop_event.wait(1.0):
                return

            remaining -= 1
            self._print_time(remaining)
            
        if not self._stop_event.is_set(): 
            print("\n[TIMER] ⏰ TEMPO SCADUTO!", flush=True)

    def _print_time(self, remaining):
        if remaining == 60: 
            print(f"\n[TIMER] ⏳ 60s rimanenti...", flush=True)
        elif remaining == 30: 
            print(f"\n[TIMER] ⏳ 30s rimanenti...", flush=True)
        elif remaining == 10: 
            print(f"\n[TIMER] ⚠️ 10s rimanenti!", flush=True)
        elif remaining <= 5 and remaining > 0:
            print(f"\n[TIMER] {remaining}...", flush=True)

# --- STATO DEL CLIENT ---
class ClientState:
    def __init__(self):
        self.is_leader = False
        self.am_i_narrator = False
        self.is_spectator = False
        self.game_running = False
        self.phase = STATE_VIEWING

state = ClientState()
cli_timer = InputTimer()

def heartbeat_loop(sock_ref):
    """Mantiene viva la connessione."""
    while True:
        time.sleep(3)
        try:
            if sock_ref: send_json(sock_ref, {"type": CMD_HEARTBEAT})
            else: break
        except: break

def listen_from_server(sock_ref):
    """Thread di ascolto messaggi."""
    global sock, intentional_exit
    while True:
        try:
            msg = recv_json(sock_ref)
            if not msg: 
                if intentional_exit: break
                else: raise Exception("Server closed")
            
            if msg.get('type') == EVT_GOODBYE:
                print(f"\n[SERVER] {msg.get('msg')}")
                os._exit(0)

            msg_type = msg.get('type')
            timeout = msg.get('timeout', 0)
            
            if timeout: cli_timer.start(timeout)
            else: cli_timer.stop()

            # --- GESTIONE EVENTI ---
            if msg_type == EVT_GAME_STARTED:
                state.game_running = True
                state.am_i_narrator = msg.get('am_i_narrator', False)
                state.is_spectator = msg.get('is_spectator', False)
                state.phase = STATE_VIEWING
                
                print(f"\n{'='*40}")
                print(f"[INFO] Inizio storia! Tema: {msg.get('theme')}")
                if state.is_spectator: print("[RUOLO] Spettatore (Osserva la partita).")
                elif state.am_i_narrator: print("[RUOLO] NARRATORE (Tu dirigi la storia).")
                else: print("[RUOLO] SCRITTORE (Tu scrivi la storia).")
                print(f"{'='*40}")

            elif msg_type == EVT_NEW_SEGMENT:
                print(f"\n\n--- INIZIO SEGMENTO {msg.get('segment_id')} ---")
                if state.is_spectator:
                    state.phase = STATE_VIEWING
                    print("(Spettatore) In attesa degli scrittori...")
                elif state.am_i_narrator:
                    state.phase = STATE_VIEWING
                    print("(Narratore) In attesa che gli scrittori inviino le proposte...")
                else:
                    state.phase = STATE_EDITING
                    print(f">>> TOCCA A TE! Scrivi la tua frase (Hai {timeout}s): <<<")

            elif msg_type == EVT_NARRATOR_DECISION_NEEDED:
                if state.am_i_narrator:
                    state.phase = STATE_DECIDING
                    proposals = msg.get('proposals')
                    
                    print("\n\n*** TOCCA A TE SCEGLIERE ***")
                    for p in proposals: 
                        print(f" > [{p['id']}] {p['author']}: {p['text']}")
                    print(f"\n>>> Inserisci il NUMERO della proposta migliore (Hai {timeout}s): <<<")

            elif msg_type == EVT_STORY_UPDATE:
                print("\n\n📖 STORIA AGGIORNATA:")
                for line in msg.get('story'): 
                    print(f" > {line}")

            elif msg_type == EVT_ASK_CONTINUE:
                print("\nSTORIA AGGIORNATA. Vuoi continuare?")
                print(">>> Scrivi 'C' (Continua) o 'F' (Finisci) <<<")
                state.phase = STATE_DECIDING_CONTINUE

            elif msg_type == EVT_GAME_ENDED:
                print("\n=== PARTITA FINITA ===")
                state.game_running = False
                state.phase = STATE_VOTING
                state.is_spectator = False 
                print("\n[VOTAZIONE] Vuoi giocare ancora?")
                print(">>> Scrivi 'S' (Sì) o 'N' (No) <<<")

            elif msg_type == EVT_VOTE_UPDATE:
                print(f"[VOTO] Avanzamento: {msg.get('count')}/{msg.get('needed')}")

            elif msg_type == EVT_RETURN_TO_LOBBY:
                cli_timer.stop()
                state.game_running = False
                state.phase = STATE_VIEWING
                state.is_spectator = False
                state.am_i_narrator = False
                print("\n\n--- SEI IN LOBBY ---")
                if msg.get('msg'): print(f"MSG: {msg.get('msg')}")
                if state.is_leader: print("LEADER: Scrivi '/start' per iniziare la partita.")
                else: print("Attendi che il Leader avvii la partita...")
            
            elif msg_type == EVT_LEADER_UPDATE:
                state.is_leader = True
                print(f"\n[INFO] {msg.get('msg')}")

            elif msg_type == EVT_WELCOME:
                state.is_leader = msg.get('is_leader')
                print(f"[SERVER] {msg.get('msg')}")
                if state.is_leader: print("Sei il LEADER. Digita '/start' quando sei pronto.")
                else: print("Attendi l'avvio della partita.")

            elif msg_type == "ERROR":
                print(f"\n[ERRORE] {msg.get('msg')}")

        except Exception:
            if not intentional_exit:
                print("\n[!] Connessione persa. Riconnessione in corso...", flush=True)
                reconnect_loop(username_cache)
            break

username_cache = ""

def reconnect_loop(username):
    global sock
    while True:
        if intentional_exit: return
        time.sleep(3)
        try:
            new_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            new_sock.settimeout(2)
            new_sock.connect((HOST, PORT))
            new_sock.settimeout(None)
            sock = new_sock
            print("[INFO] Riconnesso al server!", flush=True)
            threading.Thread(target=listen_from_server, args=(sock,), daemon=True).start()
            threading.Thread(target=heartbeat_loop, args=(sock,), daemon=True).start()
            send_json(sock, {"type": CMD_JOIN, "username": username})
            return
        except: pass

def start_client():
    global sock, username_cache, intentional_exit
    print("--- DISTRIBUTED STORYTELLING CLIENT (CLI) ---")
    username_cache = input("Inserisci Username: ")
    
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
            if not user_input: continue

            if user_input.lower() == "/quit": 
                intentional_exit = True
                os._exit(0)
            
            try:
                if user_input.lower() == "/start":
                    if state.is_leader and not state.game_running: 
                        send_json(sock, {"type": CMD_START_GAME})
                    else: print("[INFO] Non puoi avviare la partita ora.")
                    continue

                if state.phase == STATE_VOTING:
                    if user_input.upper() == "S": 
                        send_json(sock, {"type": CMD_VOTE_RESTART})
                        print("-> Hai votato SÌ.")
                    elif user_input.upper() == "N": 
                        send_json(sock, {"type": CMD_VOTE_NO})
                        print("-> Hai votato NO. Uscita in corso...")
                        intentional_exit = True
                    else: print("Scrivi 'S' per Sì o 'N' per No.")
                
                elif state.phase == STATE_DECIDING_CONTINUE:
                    if user_input.upper() == "C": 
                        send_json(sock, {"type": CMD_DECIDE_CONTINUE, "action": "CONTINUE"})
                        state.phase = STATE_VIEWING
                    elif user_input.upper() == "F": 
                        send_json(sock, {"type": CMD_DECIDE_CONTINUE, "action": "STOP"})
                        state.phase = STATE_VIEWING
                    else: print("Scrivi 'C' o 'F'.")

                elif state.phase == STATE_DECIDING and state.am_i_narrator:
                    try:
                        pid = int(user_input)
                        send_json(sock, {"type": CMD_SELECT_PROPOSAL, "proposal_id": pid})
                        state.phase = STATE_VIEWING
                        print(f"-> Hai scelto la proposta #{pid}.")
                    except ValueError: print("Inserisci un numero valido.")

                elif state.phase == STATE_EDITING:
                     send_json(sock, {"type": CMD_SUBMIT, "text": user_input})
                     state.phase = STATE_WAITING
                     print(f"-> Inviato: {user_input}")

                else:
                    if not state.is_leader:
                        print("[INFO] Non puoi scrivere in questo momento.")

            except (BrokenPipeError, ConnectionResetError):
                if not intentional_exit:
                    print("[!] Errore di invio. Connessione instabile.", flush=True)

        except KeyboardInterrupt:
            print("\nUscita forzata.")
            intentional_exit = True
            os._exit(0)
            break
        except Exception: break
            
    if sock: sock.close()

if __name__ == "__main__":
    start_client()