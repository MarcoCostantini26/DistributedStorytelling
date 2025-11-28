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
active_connections = {} 
lock = threading.Lock()

def send_to_all(msg):
    with lock:
        for sock in active_connections.values():
            try:
                send_json(sock, msg)
            except: pass

def process_vote_check():
    """Controlla se tutti hanno votato e smista i giocatori."""
    total_connected = len(game_state.players)
    total_voted = len(game_state.player_votes)

    # Info Broadcast
    send_to_all({
        "type": EVT_VOTE_UPDATE, 
        "count": total_voted, 
        "needed": total_connected
    })

    # SE TUTTI HANNO VOTATO
    if total_voted >= total_connected and total_connected > 0:
        print("[VOTO CONCLUSO] Elaborazione esiti...")
        
        # 1. Reset stato gioco
        game_state.is_running = False
        
        # 2. Lista di chi deve uscire
        users_leaving = []

        # 3. Iteriamo sui voti e mandiamo messaggi diversi
        with lock:
            for user_id, vote_is_yes in game_state.player_votes.items():
                sock = active_connections.get(user_id)
                if not sock: continue

                if vote_is_yes:
                    # HA VOTATO SÌ -> LOBBY
                    send_json(sock, {"type": EVT_RETURN_TO_LOBBY})
                else:
                    # HA VOTATO NO -> GOODBYE
                    send_json(sock, {"type": EVT_GOODBYE, "msg": "Grazie per aver giocato! Alla prossima."})
                    users_leaving.append(user_id)

        # 4. Rimuoviamo effettivamente chi ha votato NO
        for user_id in users_leaving:
            print(f"[SERVER] Rimuovo {user_id} che ha votato NO.")
            # Chiudiamo il socket lato server per pulizia
            with lock:
                if user_id in active_connections:
                    try:
                        active_connections[user_id].close()
                    except: pass
                    del active_connections[user_id]
            
            # Rimuoviamo dal GameState
            game_state.remove_player(user_id)

        # 5. Pulizia voti per il prossimo round
        game_state.player_votes.clear()
        
        print(f"[SERVER] Rimasti in Lobby: {len(game_state.players)} giocatori.")

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
            
            if msg_type == CMD_JOIN:
                username = msg.get('username', 'Anonimo')
                game_state.add_player(user_id, username)
                
                is_leader = (game_state.leader == user_id)
                send_json(conn, {"type": EVT_WELCOME, "msg": f"Benvenuto {username}!", "is_leader": is_leader})

                if game_state.is_running:
                    print(f"[INFO] {username} è entrato come SPETTATORE.")
                    send_json(conn, {
                        "type": EVT_GAME_STARTED,
                        "narrator": game_state.players.get(game_state.narrator, "???"),
                        "theme": game_state.current_theme,
                        "am_i_narrator": False,
                        "is_spectator": True
                    })
                    send_json(conn, {"type": EVT_STORY_UPDATE, "story": game_state.story})

            elif msg_type == CMD_START_GAME:
                if game_state.is_running:
                     send_json(conn, {"type": "ERROR", "msg": "Partita già in corso."})
                     continue
                if game_state.leader != user_id:
                    send_json(conn, {"type": "ERROR", "msg": "Solo il leader può iniziare."})
                    continue

                success, info = game_state.start_new_story()
                if success:
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
                    
                    seg_id = game_state.start_new_segment()
                    send_to_all({"type": EVT_NEW_SEGMENT, "segment_id": seg_id})
                else:
                    send_json(conn, {"type": "ERROR", "msg": info})

            elif msg_type == CMD_SUBMIT:
                text = msg.get('text')
                success, result = game_state.add_proposal(user_id, text)
                if success:
                    total_writers = len(game_state.active_story_players) - 1
                    current_proposals = len(game_state.active_proposals)
                    if current_proposals >= total_writers:
                        decision_msg = {"type": EVT_NARRATOR_DECISION_NEEDED, "proposals": game_state.active_proposals}
                        with lock:
                            if game_state.narrator in active_connections:
                                send_json(active_connections[game_state.narrator], decision_msg)
                else:
                    send_json(conn, {"type": "ERROR", "msg": result})

            elif msg_type == CMD_SELECT_PROPOSAL:
                if user_id != game_state.narrator: continue
                proposal_id = int(msg.get('proposal_id'))
                success, new_story = game_state.select_proposal(proposal_id)
                if success:
                    send_to_all({"type": EVT_STORY_UPDATE, "story": new_story})
                    send_json(conn, {"type": EVT_ASK_CONTINUE})
                else:
                    send_json(conn, {"type": "ERROR", "msg": "ID non valido"})

            elif msg_type == CMD_DECIDE_CONTINUE:
                if user_id != game_state.narrator: continue
                action = msg.get('action')

                if action == "CONTINUE":
                    new_seg_id = game_state.start_new_segment()
                    send_to_all({"type": EVT_NEW_SEGMENT, "segment_id": new_seg_id})

                elif action == "STOP":
                    print("Narratore ha chiuso la partita. Attesa voti...")
                    send_to_all({"type": EVT_GAME_ENDED, "final_story": game_state.story})
                    game_state.is_running = False 

            # --- GESTIONE VOTO RESTART (SI) ---
            elif msg_type == CMD_VOTE_RESTART:
                game_state.register_vote(user_id, is_yes=True)
                print(f"[VOTO] {user_id} ha votato SI.")
                process_vote_check()

            # --- GESTIONE VOTO NO (NO) ---
            elif msg_type == CMD_VOTE_NO:
                game_state.register_vote(user_id, is_yes=False)
                print(f"[VOTO] {user_id} ha votato NO.")
                process_vote_check()
            # -----------------------------

            elif msg_type == CMD_HEARTBEAT:
                pass

    except ConnectionResetError:
        print(f"Connessione persa con {addr}")
    finally:
        # Se l'utente era già stato rimosso (perchè ha votato NO), questo blocco non fa danni
        with lock:
            if addr in active_connections: del active_connections[addr]
        game_state.remove_player(user_id)
        # Se qualcuno esce (crash) durante il voto, ricalcoliamo
        if not game_state.is_running and game_state.player_votes: 
             process_vote_check()
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