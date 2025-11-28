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
from gamestate import GameState

HOST = '127.0.0.1'
PORT = 65432

game_state = GameState()
active_connections = {} # Map[addr_tuple -> socket_connection]
lock = threading.Lock()

def broadcast(msg):
    """Invia un messaggio a TUTTI i client connessi."""
    with lock:
        for addr, sock in active_connections.items():
            try:
                send_json(sock, msg)
            except Exception as e:
                print(f"Errore invio a {addr}: {e}")

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
            
            # --- GESTIONE JOIN ---
            if msg_type == CMD_JOIN:
                username = msg.get('username', 'Anonimo')
                game_state.add_player(user_id, username)
                
                # Risposta solo a chi è entrato
                is_leader = (game_state.leader == user_id)
                response = {
                    "type": EVT_WELCOME, 
                    "msg": f"Benvenuto {username}!",
                    "is_leader": is_leader
                }
                send_json(conn, response)

            # --- GESTIONE START GAME (Solo Leader) ---
            elif msg_type == CMD_START_GAME:
                # 1. Verifica permessi
                if game_state.leader != user_id:
                    send_json(conn, {"type": "ERROR", "msg": "Solo il leader può iniziare la partita."})
                    continue

                # 2. Avvia logica di gioco
                success, info = game_state.start_new_story()
                
                if success:
                    # 3. BROADCAST: Notifica a TUTTI
                    # info contiene: narrator_id, narrator_name, theme
                    evt = {
                        "type": EVT_GAME_STARTED,
                        "narrator": info['narrator_name'],
                        "theme": info['theme'],
                        "is_narrator": False
                    }
                    
                    with lock:
                        for p_addr, p_sock in active_connections.items():
                            evt_personal = evt.copy()
                            evt_personal["am_i_narrator"] = (p_addr == info['narrator_id'])
                            send_json(p_sock, evt_personal)
                    
                    print(f"Partita iniziata. Narratore: {info['narrator_name']}")

                    seg_id = game_state.start_new_segment()
                    segment_msg = {
                        "type": EVT_NEW_SEGMENT,
                        "segment_id": seg_id
                    }

                    with lock:
                        for sock in active_connections.values():
                            send_json(sock, segment_msg)
                            
                    print(f"Avviato segmento {seg_id}")

                else:
                    send_json(conn, {"type": "ERROR", "msg": info})

            # --- GESTIONE PROPOSTE SCRITTORI ---
            elif msg_type == CMD_SUBMIT:
                text = msg.get('text')
                success, result = game_state.add_proposal(user_id, text)
                
                if success:
                    print(f"[PROPOSTA] {addr} ha scritto.")
                    
                    # 1. CONTROLLO: Tutti gli scrittori hanno inviato?
                    # Numero scrittori = Totale giocatori - 1 (il Narratore)
                    total_writers = len(game_state.players) - 1
                    current_proposals = len(game_state.active_proposals)

                    print(f"[DEBUG] Proposte: {current_proposals}/{total_writers}")

                    if current_proposals >= total_writers:
                        print("[INFO] Tutte le proposte ricevute! Invio al Narratore.")
                        
                        # 2. Prepara il pacchetto per il Narratore
                        decision_msg = {
                            "type": EVT_NARRATOR_DECISION_NEEDED,
                            "proposals": game_state.active_proposals
                        }
                        
                        # 3. Invia SOLO al Narratore
                        narrator_id = game_state.narrator
                        with lock:
                            if narrator_id in active_connections:
                                send_json(active_connections[narrator_id], decision_msg)
                else:
                    send_json(conn, {"type": "ERROR", "msg": result})

                # --- GESTIONE SCELTA NARRATORE ---
            elif msg_type == CMD_SELECT_PROPOSAL:
                # Solo il narratore può fare questo
                if user_id != game_state.narrator:
                    continue

                proposal_id = int(msg.get('proposal_id'))
                
                # Applica la scelta nel GameState
                success, new_story = game_state.select_proposal(proposal_id)
                
                if success:
                    # BROADCAST: Aggiorna la storia per tutti
                    update_msg = {
                        "type": EVT_STORY_UPDATE,
                        "story": new_story
                    }
                    with lock:
                        for sock in active_connections.values():
                            send_json(sock, update_msg)

                    print(f"Attendo decisione dal narratore {user_id}...")
                    send_json(conn, {"type": EVT_ASK_CONTINUE}) 
                    # --------------------

                else:
                    send_json(conn, {"type": "ERROR", "msg": "ID non valido"})
                    # --- [AGGIUNTA] START NUOVO SEGMENTO ---
                    
                    # 2. Prepara il GameState per il nuovo round
                    new_seg_id = game_state.start_new_segment()
                    
                    # 3. Avvisa tutti i client di abilitare la scrittura (INPUT ON)
                    new_segment_msg = {
                        "type": EVT_NEW_SEGMENT,
                        "segment_id": new_seg_id
                    }

                    with lock:
                        for sock in active_connections.values():
                            send_json(sock, new_segment_msg)
                            
                    print(f"Storia aggiornata. Avviato segmento {new_seg_id}")
                    # ---------------------------------------
            # --- GESTIONE DECISIONE CONTINUA/STOP ---
            elif msg_type == CMD_DECIDE_CONTINUE:
                # Solo il narratore può decidere
                if user_id != game_state.narrator:
                    continue
                
                action = msg.get('action') # Ci aspettiamo "CONTINUE" o "STOP"

                if action == "CONTINUE":
                    # --- CASO 1: SI CONTINUA ---
                    new_seg_id = game_state.start_new_segment()
                    
                    msg_segment = {
                        "type": EVT_NEW_SEGMENT, 
                        "segment_id": new_seg_id
                    }
                    with lock:
                        for sock in active_connections.values():
                            send_json(sock, msg_segment)
                    print(f"Il narratore ha scelto di continuare. Segmento {new_seg_id}")

                elif action == "STOP":
                    # --- CASO 2: FINE PARTITA ---
                    print("Il narratore ha chiuso la partita.")
                    
                    # Qui in futuro metteremo il salvataggio su file (game_state.save_story...)
                    
                    end_msg = {
                        "type": EVT_GAME_ENDED,
                        "final_story": game_state.story
                    }
                    with lock:
                        for sock in active_connections.values():
                            send_json(sock, end_msg)
                            
                    # Reset dello stato per una eventuale nuova partita futura
                    # (Opzionale, dipende se vuoi chiudere il server o resettare la lobby)
                    game_state.is_running = False
            # --- GESTIONE HEARTBEAT ---
            elif msg_type == CMD_HEARTBEAT:
                pass

    except ConnectionResetError:
        print(f"Connessione persa con {addr}")
    finally:
        with lock:
            if addr in active_connections:
                del active_connections[addr]
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
        thread = threading.Thread(target=handle_client, args=(conn, addr))
        thread.start()

if __name__ == "__main__":
    start_server()