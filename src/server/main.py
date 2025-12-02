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
            try: send_json(sock, msg)
            except: pass

def check_round_completion():
    active_writers = game_state.count_active_writers()
    current_props = len(game_state.active_proposals)
    
    print(f"[CHECK ROUND] Proposte ricevute: {current_props} su {active_writers} attivi.")
    if current_props >= active_writers and active_writers > 0:
        print("[INFO] Turno completato.")
        decision_msg = {"type": EVT_NARRATOR_DECISION_NEEDED, "proposals": game_state.active_proposals}
        with lock:
            if game_state.narrator in active_connections:
                send_json(active_connections[game_state.narrator], decision_msg)

def process_vote_check():
    total_connected = len(game_state.players)
    total_voted = len(game_state.player_votes)
    send_to_all({"type": EVT_VOTE_UPDATE, "count": total_voted, "needed": total_connected})

    if total_voted >= total_connected and total_connected > 0:
        print("[VOTO CONCLUSO] Elaborazione...")
        game_state.is_running = False
        users_leaving = []
        with lock:
            for user_id, vote_is_yes in game_state.player_votes.items():
                sock = active_connections.get(user_id)
                if not sock: continue
                if vote_is_yes: send_json(sock, {"type": EVT_RETURN_TO_LOBBY})
                else:
                    send_json(sock, {"type": EVT_GOODBYE, "msg": "Arrivederci!"})
                    users_leaving.append(user_id)
        
        for uid in users_leaving:
            with lock:
                if uid in active_connections:
                    try: active_connections[uid].close()
                    except: pass
                    del active_connections[uid]
            game_state.remove_player(uid)
        game_state.player_votes.clear()

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
                raw_username = msg.get('username', 'Anonimo')
                username = game_state.add_player(user_id, raw_username)
                
                is_leader = (game_state.leader == user_id)
                send_json(conn, {"type": EVT_WELCOME, "msg": f"Benvenuto {username}!", "is_leader": is_leader})

                if game_state.is_running:
                    if username in game_state.story_usernames:
                        print(f"[INFO] SCRITTORE RITROVATO: {username}")
                        narrator_name = game_state.players.get(game_state.narrator, "???")
                        am_i_narrator = (game_state.narrator == user_id)
                        send_json(conn, {
                            "type": EVT_GAME_STARTED,
                            "narrator": narrator_name,
                            "theme": game_state.current_theme,
                            "am_i_narrator": am_i_narrator,
                            "is_spectator": False 
                        })
                        send_json(conn, {"type": EVT_STORY_UPDATE, "story": game_state.story})
                        if not am_i_narrator and not game_state.has_user_submitted(username):
                            send_json(conn, {"type": EVT_NEW_SEGMENT, "segment_id": game_state.current_segment_id})
                    else:
                        print(f"[INFO] NUOVO SPETTATORE: {username}")
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
                     send_json(conn, {"type": "ERROR", "msg": "Partita in corso."})
                     continue
                if game_state.leader != user_id:
                    send_json(conn, {"type": "ERROR", "msg": "Solo leader."})
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
                    check_round_completion()
                else:
                    send_json(conn, {"type": "ERROR", "msg": result})

            elif msg_type == CMD_SELECT_PROPOSAL:
                if user_id != game_state.narrator: continue
                proposal_id = int(msg.get('proposal_id'))
                success, new_story = game_state.select_proposal(proposal_id)
                if success:
                    send_to_all({"type": EVT_STORY_UPDATE, "story": new_story})
                    send_json(conn, {"type": EVT_ASK_CONTINUE})

            elif msg_type == CMD_DECIDE_CONTINUE:
                if user_id != game_state.narrator: continue
                action = msg.get('action')
                if action == "CONTINUE":
                    new_seg_id = game_state.start_new_segment()
                    send_to_all({"type": EVT_NEW_SEGMENT, "segment_id": new_seg_id})
                elif action == "STOP":
                    print("Stop dal narratore.")
                    send_to_all({"type": EVT_GAME_ENDED, "final_story": game_state.story})
                    game_state.is_running = False 

            elif msg_type == CMD_VOTE_RESTART:
                game_state.register_vote(user_id, True)
                process_vote_check()
            elif msg_type == CMD_VOTE_NO:
                game_state.register_vote(user_id, False)
                process_vote_check()
            elif msg_type == CMD_HEARTBEAT:
                pass

    except ConnectionResetError:
        print(f"Connessione persa con {addr}")
    finally:
        with lock:
            if addr in active_connections: del active_connections[addr]
        
        # --- LOGICA DISCONNESSIONE CRITICA ---
        # 1. Controlliamo se chi esce è il Narratore
        if game_state.is_running and user_id == game_state.narrator:
            print("[ALERT] Il Narratore si è disconnesso! Abort game.")
            
            # Avvisa tutti e manda in Lobby
            send_to_all({
                "type": EVT_RETURN_TO_LOBBY, 
                "msg": "Il Narratore si è disconnesso. La partita è terminata."
            })
            
            # Resetta il gioco
            game_state.abort_game()
        
        # 2. Rimuoviamo il giocatore (Gestisce elezione nuovo Leader se serve)
        new_leader_id = game_state.remove_player(user_id)
        
        # 3. Notifica cambio Leader
        if new_leader_id:
            with lock:
                if new_leader_id in active_connections:
                    send_json(active_connections[new_leader_id], {
                        "type": EVT_LEADER_UPDATE, 
                        "msg": "Il Leader precedente è uscito. Ora sei tu il Leader!"
                    })

        # 4. Se il gioco continua (era uno scrittore), controlla se il turno è finito
        if game_state.is_running: 
            check_round_completion()
        
        # 5. Se eravamo in fase di voto
        elif not game_state.is_running and game_state.player_votes: 
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