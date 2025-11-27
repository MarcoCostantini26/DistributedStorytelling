import socket
import threading
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from common.protocol import send_json, recv_json, CMD_JOIN, EVT_WELCOME

HOST = '127.0.0.1'
PORT = 65432

def listen_from_server(sock):
    """Thread che ascolta costantemente messaggi dal server"""
    while True:
        try:
            msg = recv_json(sock)
            if msg:
                print(f"\n[SERVER]: {msg}")
                # Qui gestiremo l'aggiornamento della UI in base al tipo di messaggio
        except Exception:
            print("\nDisconnesso dal server.")
            break

def start_client():
    username = input("Inserisci il tuo username: ")
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect((HOST, PORT))
    except ConnectionRefusedError:
        print("Impossibile connettersi al server.")
        return

    # Avvia thread per ricevere messaggi
    listener = threading.Thread(target=listen_from_server, args=(sock,), daemon=True)
    listener.start()

    # Invia richiesta di Join
    join_req = {"type": CMD_JOIN, "username": username}
    send_json(sock, join_req)

    # Loop principale per input utente
    while True:
        text = input()
        if text.lower() == "/quit":
            break
        # Qui implementeremo l'invio delle proposte (CMD_SUBMIT)
        
    sock.close()

if __name__ == "__main__":
    start_client()