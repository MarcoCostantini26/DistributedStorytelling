import socket
import threading
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from common.protocol import send_json, recv_json, CMD_JOIN, EVT_WELCOME, CMD_START_GAME, EVT_GAME_STARTED

HOST = '127.0.0.1'
PORT = 65432

class ClientState:
    def __init__(self):
        self.is_leader = False
        self.am_i_narrator = False
        self.game_running = False

state = ClientState()

def listen_from_server(sock):
    """Thread che ascolta costantemente messaggi dal server"""
    while True:
        try:
            msg = recv_json(sock)
            if not msg:
                break
            
            msg_type = msg.get('type')

            if msg_type == EVT_WELCOME:
                print(f"\n[SERVER]: {msg.get('msg')}")
                
                # Controlliamo se siamo il leader
                if msg.get('is_leader'):
                    state.is_leader = True
                    print(">>> SEI IL LEADER! Digita '/start' quando vuoi iniziare la partita. <<<")
                else:
                    print(">>> In attesa che il leader inizi la partita... <<<")

            elif msg_type == EVT_GAME_STARTED:
                state.game_running = True
                narrator_name = msg.get('narrator')
                theme = msg.get('theme')
                state.am_i_narrator = msg.get('am_i_narrator', False)

                print("\n" + "="*40)
                print(f"LA PARTITA È INIZIATA!")
                print(f"TEMA: {theme}")
                print(f"NARRATORE: {narrator_name}")
                
                if state.am_i_narrator:
                    print("\n[RUOLO]: SEI IL NARRATORE!")
                    print("Attendi le proposte degli altri giocatori...")
                else:
                    print("\n[RUOLO]: SEI UNO SCRITTORE!")
                    print("Presto potrai inviare la tua proposta per la storia.")
                print("="*40 + "\n")

            elif msg_type == "ERROR":
                print(f"\n[ERRORE]: {msg.get('msg')}")

            else:
                print(f"\n[SERVER MSG]: {msg}")

        except Exception as e:
            print(f"\nErrore nella ricezione: {e}")
            break
    
    print("\nDisconnesso dal server.")
    os._exit(0)

def start_client():
    print("--- DISTRIBUTED STORYTELLING CLIENT ---")
    username = input("Inserisci il tuo username: ")
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect((HOST, PORT))
    except ConnectionRefusedError:
        print("Impossibile connettersi al server. È acceso?")
        return

    # Avvia thread per ricevere messaggi
    listener = threading.Thread(target=listen_from_server, args=(sock,), daemon=True)
    listener.start()

    # 1. Invia richiesta di Join
    join_req = {"type": CMD_JOIN, "username": username}
    send_json(sock, join_req)

    # 2. Loop principale per input utente
    while True:
        try:
            text = input()
            
            if not text: continue

            if text.lower() == "/quit":
                break
            
            # COMANDO START (Solo per il Leader)
            elif text.lower() == "/start":
                if state.is_leader:
                    if not state.game_running:
                        print("[CLIENT] Invio richiesta avvio partita...")
                        send_json(sock, {"type": CMD_START_GAME})
                    else:
                        print("[CLIENT] La partita è già in corso!")
                else:
                    print("[CLIENT] Solo il Leader può avviare la partita.")

            # QUI ANDRA' LA LOGICA PER INVIARE PROPOSTE
            # else:
            #     if state.game_running and not state.am_i_narrator:
            #          send_proposal(...)
            
        except EOFError:
            break
        except KeyboardInterrupt:
            break
        
    sock.close()
    print("Chiusura client.")

if __name__ == "__main__":
    start_client()