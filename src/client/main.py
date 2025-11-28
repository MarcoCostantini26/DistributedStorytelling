import socket
import threading
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from common.protocol import *

HOST = '127.0.0.1'
PORT = 65432

# Stati Client
STATE_VIEWING = "VIEWING"
STATE_EDITING = "EDITING"
STATE_WAITING = "WAITING"
STATE_DECIDING = "DECIDING"          # Narratore sceglie proposta
STATE_DECIDING_CONTINUE = "DECIDING_CONTINUE" # Narratore sceglie se continuare

class ClientState:
    def __init__(self):
        self.is_leader = False
        self.am_i_narrator = False
        self.is_spectator = False
        self.game_running = False
        self.phase = STATE_VIEWING

state = ClientState()

def listen_from_server(sock):
    while True:
        try:
            msg = recv_json(sock)
            if not msg: break
            msg_type = msg.get('type')

            if msg_type == EVT_GAME_STARTED:
                state.game_running = True
                state.am_i_narrator = msg.get('am_i_narrator', False)
                state.is_spectator = msg.get('is_spectator', False)
                state.phase = STATE_VIEWING
                
                print(f"\n[INFO] Nuova storia iniziata! Tema: {msg.get('theme')}")
                if state.is_spectator:
                    print("[RUOLO] Sei entrato a partita in corso. Modalità SPETTATORE.")
                elif state.am_i_narrator:
                    print("[RUOLO] Sei il NARRATORE. Attendi le proposte.")
                else:
                    print("[RUOLO] Sei uno SCRITTORE. Preparati a scrivere.")

            elif msg_type == EVT_NEW_SEGMENT:
                print(f"\n--- INIZIO SEGMENTO {msg.get('segment_id')} ---")
                if state.is_spectator:
                    state.phase = STATE_VIEWING
                    print("(Spettatore) In attesa delle proposte...")
                elif state.am_i_narrator:
                    state.phase = STATE_VIEWING
                    print("In attesa delle proposte degli scrittori...")
                else:
                    state.phase = STATE_EDITING
                    print(">>> TOCCA A TE! Scrivi la tua continuazione e premi Invio: <<<")

            elif msg_type == EVT_NARRATOR_DECISION_NEEDED:
                if state.am_i_narrator:
                    state.phase = STATE_DECIDING
                    proposals = msg.get('proposals')
                    print("\n" + "*"*40)
                    print("SCEGLI LA PROPOSTA MIGLIORE:")
                    for p in proposals:
                        print(f"[{p['id']}] {p['author']}: {p['text']}")
                    print("*"*40)
                    print(">>> Scrivi il NUMERO della proposta vincente: <<<")

            elif msg_type == EVT_STORY_UPDATE:
                print("\n" + "="*40 + "\nSTORIA AGGIORNATA:")
                for line in msg.get('story'):
                    print(f" > {line}")
                print("="*40 + "\n")

            elif msg_type == EVT_ASK_CONTINUE:
                print("\n" + "="*40)
                print("STORIA AGGIORNATA. Vuoi continuare?")
                print("Scrivi 'C' per Continuare, 'F' per Finire.")
                print("="*40)
                state.phase = STATE_DECIDING_CONTINUE

            elif msg_type == EVT_GAME_ENDED:
                print("\n" + "="*40 + "\nLA PARTITA È FINITA!\n" + "="*40)
                state.game_running = False
                state.phase = STATE_VIEWING
                if state.is_leader: print("Digita '/start' per una nuova partita.")

            elif msg_type == EVT_WELCOME:
                state.is_leader = msg.get('is_leader')
                print(f"[SERVER] {msg.get('msg')}")
                if state.is_leader: print("Digita '/start' per iniziare.")
            
            elif msg_type == "ERROR":
                print(f"[ERRORE] {msg.get('msg')}")

        except Exception as e:
            print(f"Errore listener: {e}")
            break
    os._exit(0)

def start_client():
    print("--- CLIENT STORYTELLING ---")
    username = input("Username: ")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((HOST, PORT))
    
    threading.Thread(target=listen_from_server, args=(sock,), daemon=True).start()
    send_json(sock, {"type": CMD_JOIN, "username": username})

    while True:
        try:
            user_input = input()
            if not user_input: continue

            if user_input.lower() == "/quit": break
            if user_input.lower() == "/start":
                if state.is_leader and not state.game_running:
                    send_json(sock, {"type": CMD_START_GAME})
                else:
                    print("[INFO] Non puoi avviare ora.")
                continue

            # LOGICA INPUT BASATA SUGLI STATI
            if state.phase == STATE_DECIDING_CONTINUE:
                if user_input.upper() == "C":
                    send_json(sock, {"type": CMD_DECIDE_CONTINUE, "action": "CONTINUE"})
                    state.phase = STATE_VIEWING
                    print("Hai scelto di continuare...")
                elif user_input.upper() == "F":
                    send_json(sock, {"type": CMD_DECIDE_CONTINUE, "action": "STOP"})
                    state.phase = STATE_VIEWING
                    print("Hai scelto di finire.")
                else: print("Scrivi 'C' o 'F'.")

            elif state.phase == STATE_DECIDING and state.am_i_narrator:
                try:
                    send_json(sock, {"type": CMD_SELECT_PROPOSAL, "proposal_id": int(user_input)})
                    state.phase = STATE_VIEWING
                    print("Scelta inviata...")
                except: print("Inserisci un numero valido.")

            elif state.phase == STATE_EDITING:
                 send_json(sock, {"type": CMD_SUBMIT, "text": user_input})
                 state.phase = STATE_WAITING
                 print("Proposta inviata! Attendi...")

            elif state.phase == STATE_WAITING:
                print("Hai già inviato. Aspetta.")
            
            elif state.phase == STATE_VIEWING and state.game_running and not state.is_spectator:
                print("Non è il momento di scrivere.")
            
            elif state.is_spectator and state.game_running:
                print("Sei uno spettatore, goditi la storia!")

        except: break
    sock.close()

if __name__ == "__main__":
    start_client()