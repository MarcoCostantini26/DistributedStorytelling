import socket
import threading
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from common.protocol import *
from gamestate import GameState

HOST = '127.0.0.1'
PORT = 65432

game_state = GameState()
active_connections = {} # Map[addr_tuple -> socket]
lock = threading.Lock()

def send_to_all(msg):
    with lock:
        for sock in active_connections.values():
            try:
                send_json(sock, msg)
            except: pass

def handle_client(conn, addr):
    print(f"Nuova connessione da {addr}")
    with lock:
        active_connections[addr] = conn
    user_id = addr
    
    try:
        while True:
            msg = recv_json(conn)
            if not msg: break
            msg_type = msg.get('type')
            
            # --- JOIN ---
            if msg_type == CMD_JOIN:
                username = msg.get('username', 'Anonimo')
                game_state.add_player(user_id, username)
                
                is_leader = (game_state.leader == user_id)
                send_json(conn, {"type": EVT_WELCOME, "msg": f"Benvenuto {username}!", "is_leader": is_leader})

                # GESTIONE SPETTATORE (LATE JOIN)
                if game_state.is_running:
                    print(f"[INFO] {username} è entrato come SPETTATORE.")
                    # 1. Info Partita
                    send_json(conn, {
                        "type": EVT_GAME_STARTED,
                        "narrator": game_state.players.get(game_state.narrator, "???"),
                        "theme": game_state.current_theme,
                        "am_i_narrator": False,
                        "is_spectator": True
                    })
                    # 2. Storia pregressa
                    send_json(conn, {
                        "type": EVT_STORY_UPDATE,
                        "story": game_state.story
                    })

            # --- START GAME ---
            elif msg_type == CMD_START_GAME:
                if game_state.leader != user_id:
                    send_json(conn, {"type": "ERROR", "msg": "Solo il leader può iniziare."})
                    continue

                success, info = game_state.start_new_story()
                if success:
                    # Notifica inizio a tutti
                    evt = {
                        "type": EVT_GAME_STARTED,
                        "narrator": info['narrator_name'],
                        "theme": info['theme'],
                        "is_spectator": False
                    }
                    with lock:
                        for p_addr, p_sock in active_connections.items():
                            evt_personal = evt.copy()
                            evt_personal["am_i_narrator"] = (p_addr == info['narrator_id'])
                            send_json(p_sock, evt_personal)
                    
                    # Avvio primo segmento
                    seg_id = game_state.start_new_segment()
                    send_to_all({"type": EVT_NEW_SEGMENT, "segment_id": seg_id})
                else:
                    send_json(conn, {"type": "ERROR", "msg": info})

            # --- PROPOSTE ---
            elif msg_type == CMD_SUBMIT:
                text = msg.get('text')
                success, result = game_state.add_proposal(user_id, text)
                
                if success:
                    print(f"[PROPOSTA] {addr} ha scritto.")
                    # Calcolo basato sui GIOCATORI ATTIVI (non tutti i connessi)
                    total_writers = len(game_state.active_story_players) - 1
                    current_proposals = len(game_state.active_proposals)

                    if current_proposals >= total_writers:
                        print("[INFO] Tutte proposte ricevute. Invio al Narratore.")
                        decision_msg = {"type": EVT_NARRATOR_DECISION_NEEDED, "proposals": game_state.active_proposals}
                        with lock:
                            if game_state.narrator in active_connections:
                                send_json(active_connections[game_state.narrator], decision_msg)
                else:
                    send_json(conn, {"type": "ERROR", "msg": result})

            # --- SCELTA PROPOSTA ---
            elif msg_type == CMD_SELECT_PROPOSAL:
                if user_id != game_state.narrator: continue
                
                proposal_id = int(msg.get('proposal_id'))
                success, new_story = game_state.select_proposal(proposal_id)
                
                if success:
                    # Aggiorna storia a tutti
                    send_to_all({"type": EVT_STORY_UPDATE, "story": new_story})
                    
                    # Chiedi al narratore se continuare
                    print(f"Attendo decisione continuo dal narratore {user_id}...")
                    send_json(conn, {"type": EVT_ASK_CONTINUE})
                else:
                    send_json(conn, {"type": "ERROR", "msg": "ID non valido"})

            # --- DECISIONE CONTINUA/STOP ---
            elif msg_type == CMD_DECIDE_CONTINUE:
                if user_id != game_state.narrator: continue
                action = msg.get('action')

                if action == "CONTINUE":
                    new_seg_id = game_state.start_new_segment()
                    send_to_all({"type": EVT_NEW_SEGMENT, "segment_id": new_seg_id})
                    print(f"Narratore continua. Segmento {new_seg_id}")

                elif action == "STOP":
                    print("Narratore ha chiuso la partita.")
                    send_to_all({"type": EVT_GAME_ENDED, "final_story": game_state.story})
                    game_state.is_running = False

            # --- HEARTBEAT ---
            elif msg_type == CMD_HEARTBEAT:
                pass

    except ConnectionResetError:
        print(f"Connessione persa con {addr}")
    finally:
        with lock:
            if addr in active_connections: del active_connections[addr]
        game_state.remove_player(user_id)
        conn.close()

def start_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen()
    print(f"[SERVER] In ascolto su {HOST}:{PORT}")
    while True:
        conn, addr = server.accept()
        threading.Thread(target=handle_client, args=(conn, addr)).start()

if __name__ == "__main__":
    start_server()