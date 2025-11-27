import socket
import threading
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from common.protocol import send_json, recv_json, CMD_JOIN, EVT_WELCOME, CMD_START_GAME, EVT_GAME_STARTED, EVT_NEW_SEGMENT, CMD_SUBMIT

HOST = '127.0.0.1'
PORT = 65432

# Definizione stati locali del Client 
STATE_VIEWING = "VIEWING"  # Legge la storia / attende start
STATE_EDITING = "EDITING"  # Può scrivere la proposta
STATE_WAITING = "WAITING"  # Ha inviato, aspetta il narratore

class ClientState:
    def __init__(self):
        self.is_leader = False
        self.am_i_narrator = False
        self.game_running = False
        self.phase = STATE_VIEWING # Stato iniziale

state = ClientState()

def listen_from_server(sock):
    while True:
        try:
            msg = recv_json(sock)
            if not msg: break
            
            msg_type = msg.get('type')

            # --- GESTIONE START GAME ---
            if msg_type == EVT_GAME_STARTED:
                state.game_running = True
                state.am_i_narrator = msg.get('am_i_narrator', False)
                state.phase = STATE_VIEWING
                
                print(f"\n[INFO] Nuova storia iniziata! Tema: {msg.get('theme')}")
                if state.am_i_narrator:
                    print("[RUOLO] Sei il NARRATORE. Attendi le proposte.")
                else:
                    print("[RUOLO] Sei uno SCRITTORE. Preparati a scrivere.")

            # --- GESTIONE NUOVO SEGMENTO (Transizione a EDITING) ---
            elif msg_type == EVT_NEW_SEGMENT:
                print(f"\n--- INIZIO SEGMENTO {msg.get('segment_id')} ---")
                
                if state.am_i_narrator:
                    state.phase = STATE_VIEWING
                    print("In attesa delle proposte degli scrittori...")
                else:
                    state.phase = STATE_EDITING
                    print(">>> TOCCA A TE! Scrivi la tua continuazione e premi Invio: <<<")

            # --- ALTRI MESSAGGI ---
            elif msg_type == EVT_WELCOME:
                state.is_leader = msg.get('is_leader')
                print(f"[SERVER] {msg.get('msg')}")
                if state.is_leader: print("Digita '/start' per iniziare.")

            elif msg_type == "ERROR":
                print(f"[ERRORE] {msg.get('msg')}")

        except Exception as e:
            print(f"Errore: {e}")
            break
    os._exit(0)

def start_client():
    print("--- DISTRIBUTED STORYTELLING CLIENT ---")
    username = input("Username: ")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((HOST, PORT))
    
    listener = threading.Thread(target=listen_from_server, args=(sock,), daemon=True)
    listener.start()

    send_json(sock, {"type": CMD_JOIN, "username": username})

    while True:
        try:
            user_input = input() # Input bloccante
            if not user_input: continue

            # Gestione comandi di sistema
            if user_input.lower() == "/quit": break
            
            if user_input.lower() == "/start":
                if state.is_leader and not state.game_running:
                    send_json(sock, {"type": CMD_START_GAME})
                else:
                    print("[INFO] Non puoi avviare ora.")
                continue

            # --- GESTIONE INVIO PROPOSTE (Solo in fase EDITING) ---
            if state.game_running:
                if state.phase == STATE_EDITING:
                    # Invia la proposta al server
                    proposal_msg = {
                        "type": CMD_SUBMIT,
                        "text": user_input
                    }
                    send_json(sock, proposal_msg)
                    
                    # Cambio stato locale: EDITING -> WAITING
                    state.phase = STATE_WAITING
                    print("[INFO] Proposta inviata! In attesa della decisione del narratore...")
                
                elif state.phase == STATE_WAITING:
                    print("[INFO] Hai già inviato una proposta. Aspetta il prossimo turno.")
                
                elif state.phase == STATE_VIEWING:
                    if state.am_i_narrator:
                        print("[INFO] Sei il narratore, non puoi proporre frasi.")
                    else:
                        print("[INFO] Non è ancora il momento di scrivere.")

        except EOFError: break
    
    sock.close()

if __name__ == "__main__":
    start_client()
