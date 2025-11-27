import socket
import threading
import sys
import os

# Aggiungi src al path per importare i moduli common
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from common.protocol import send_json, recv_json, CMD_JOIN, EVT_WELCOME
from gamestate import GameState

HOST = '127.0.0.1' # Localhost per test
PORT = 65432

game_state = GameState()

def handle_client(conn, addr):
    """Gestisce la comunicazione con un singolo client."""
    print(f"Nuova connessione da {addr}")
    user_id = None
    
    try:
        while True:
            msg = recv_json(conn)
            if not msg:
                break
            
            msg_type = msg.get('type')
            
            if msg_type == CMD_JOIN:
                username = msg.get('username', 'Anonimo')
                user_id = addr
                game_state.add_player(user_id, username)
                
                # Invia conferma al client
                response = {"type": EVT_WELCOME, "msg": f"Benvenuto {username}!"}
                send_json(conn, response)
                
            # Qui aggiungeremo gli altri case: SUBMIT, HEARTBEAT, etc.
            
    except ConnectionResetError:
        print(f"Connessione persa con {addr}")
    finally:
        if user_id:
            game_state.remove_player(user_id)
        conn.close()

def start_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((HOST, PORT))
    server.listen()
    print(f"[SERVER] In ascolto su {HOST}:{PORT}")

    while True:
        conn, addr = server.accept()
        thread = threading.Thread(target=handle_client, args=(conn, addr))
        thread.start()
        print(f"[ATTIVI] Connessioni attive: {threading.active_count() - 1}")

if __name__ == "__main__":
    start_server()