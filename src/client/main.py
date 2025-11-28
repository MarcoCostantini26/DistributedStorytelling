import socket
import threading
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from common.protocol import (
    send_json, recv_json, 
    CMD_JOIN, EVT_WELCOME, 
    CMD_START_GAME, EVT_GAME_STARTED, 
    EVT_NEW_SEGMENT, CMD_SUBMIT, 
    CMD_HEARTBEAT,
    CMD_SELECT_PROPOSAL,
    EVT_NARRATOR_DECISION_NEEDED,
    EVT_STORY_UPDATE,
    EVT_ASK_CONTINUE,
    CMD_DECIDE_CONTINUE,
    EVT_GAME_ENDED
)
HOST = '127.0.0.1'
PORT = 65432

# Definizione stati locali del Client 
STATE_VIEWING = "VIEWING"   # Legge la storia / attende start
STATE_EDITING = "EDITING"   # Può scrivere la proposta
STATE_WAITING = "WAITING"   # Ha inviato, aspetta il narratore
STATE_DECIDING = "DECIDING" # Narratore sta scegliendo la proposta
# ### CORREZIONE 1: Aggiunto nuovo stato ###
STATE_DECIDING_CONTINUE = "DECIDING_CONTINUE" # Narratore decide se continuare o finire

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
            
            elif msg_type == EVT_NARRATOR_DECISION_NEEDED:
                if state.am_i_narrator:
                    state.phase = STATE_DECIDING
                    proposals = msg.get('proposals')
                    
                    print("\n" + "*"*40)
                    print("TUTTE LE PROPOSTE SONO ARRIVATE! SCEGLI LA MIGLIORE:")
                    for p in proposals:
                        print(f"[{p['id']}] {p['author']}: {p['text']}")
                    print("*"*40)
                    print(">>> Scrivi il NUMERO della proposta vincente e premi Invio: <<<")

            elif msg_type == EVT_STORY_UPDATE:
                story_lines = msg.get('story')
                print("\n" + "="*40)
                print("STORIA AGGIORNATA:")
                for line in story_lines:
                    print(f" > {line}")
                print("="*40 + "\n")

            elif msg_type == EVT_ASK_CONTINUE:
                # Il server sta chiedendo al Narratore se vuole continuare
                print("\n" + "="*40)
                print("HAI SCELTO LA PROPOSTA! LA STORIA È AGGIORNATA.")
                print("Vuoi continuare a giocare o finire qui?")
                print("Scrivi 'C' per Continuare, 'F' per Finire.")
                print("="*40)
                
                # ### CORREZIONE 2: Usiamo state.phase invece di client_state.current_mode ###
                state.phase = STATE_DECIDING_CONTINUE

            elif msg_type == EVT_GAME_ENDED:
                print("\n" + "="*40)
                print("LA PARTITA È FINITA!")
                print("Ecco la storia completa:")
                for line in msg.get('final_story', []):
                    print(f"- {line}")
                print("="*40)
                state.game_running = False
                state.phase = STATE_VIEWING
                # Non usciamo, magari vuole fare un'altra partita
                # break 

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
    print("--- DISTRIBUTED STORYTELLING CLIENT ---")
    username = input("Username: ")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((HOST, PORT))
    
    listener = threading.Thread(target=listen_from_server, args=(sock,), daemon=True)
    listener.start()

    send_json(sock, {"type": CMD_JOIN, "username": username})

    while True:
        try:
            user_input = input()
            if not user_input: continue

            # Gestione comandi di sistema
            if user_input.lower() == "/quit": break
            
            if user_input.lower() == "/start":
                if state.is_leader and not state.game_running:
                    send_json(sock, {"type": CMD_START_GAME})
                else:
                    print("[INFO] Non puoi avviare ora.")
                continue

            # ### CORREZIONE 3: Gestione Input basata sugli STATI ###
            
            # 1. Se il narratore deve decidere se CONTINUARE
            if state.phase == STATE_DECIDING_CONTINUE:
                if user_input.upper() == "C":
                    send_json(sock, {"type": CMD_DECIDE_CONTINUE, "action": "CONTINUE"})
                    state.phase = STATE_VIEWING # Resetta temporaneamente
                    print("Hai scelto di continuare. In attesa...")
                    
                elif user_input.upper() == "F":
                    send_json(sock, {"type": CMD_DECIDE_CONTINUE, "action": "STOP"})
                    state.phase = STATE_VIEWING
                    print("Hai scelto di terminare la partita.")
                else:
                    print("Comando non valido. Scrivi 'C' o 'F'.")

            # 2. Se il narratore deve scegliere una PROPOSTA
            elif state.phase == STATE_DECIDING and state.am_i_narrator:
                try:
                    choice_id = int(user_input)
                    select_msg = {"type": CMD_SELECT_PROPOSAL, "proposal_id": choice_id}
                    send_json(sock, select_msg)
                    print("[INFO] Scelta inviata...")
                    state.phase = STATE_VIEWING 
                except ValueError:
                    print("[ERRORE] Inserisci un numero valido.")

            # 3. Se lo scrittore deve inviare una PROPOSTA
            elif state.phase == STATE_EDITING:
                 proposal_msg = {"type": CMD_SUBMIT, "text": user_input}
                 send_json(sock, proposal_msg)
                 state.phase = STATE_WAITING
                 print("[INFO] Proposta inviata! In attesa...")

            # 4. Casi in cui l'utente scrive ma non dovrebbe
            elif state.phase == STATE_WAITING:
                print("[INFO] Hai già inviato. Aspetta.")
            
            elif state.phase == STATE_VIEWING and state.game_running:
                print("[INFO] Non è il momento di scrivere.")

        except EOFError: break
        except Exception as e:
            print(f"Errore input: {e}")
            break
    
    sock.close()

if __name__ == "__main__":
    start_client()