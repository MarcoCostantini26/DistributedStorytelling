import socket
import threading
import sys
import os
import random 

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from common.protocol import *
from gamestate import GameState

HOST = '127.0.0.1'
PORT = 65432

# Timer (Secondi)
TIME_PROPOSAL = 40
TIME_SELECTION = 40
TIME_VOTING = 10

game_state = GameState()
active_connections = {} 

# --- FIX FONDAMENTALE: USARE RLock INVECE DI Lock ---
# RLock permette allo stesso thread di ri-acquisire il lock senza bloccarsi.
lock = threading.RLock() 
# ----------------------------------------------------

game_timer = None 

def send_to_all(msg):
    with lock:
        for sock in active_connections.values():
            try: send_json(sock, msg)
            except: pass

# --- TIMER ---
def start_timer(duration, callback):
    global game_timer
    stop_timer() 
    game_timer = threading.Timer(duration, callback)
    game_timer.start()
    return duration

def stop_timer():
    global game_timer
    if game_timer:
        game_timer.cancel()
        game_timer = None

# --- CALLBACK TIMEOUT ---

def on_proposal_timeout():
    """Tempo scrittura scaduto."""
    with lock:
        if not game_state.is_running: return
        print("[TIMEOUT] Tempo scrittura scaduto.")
        
        if not game_state.active_proposals:
            game_state.active_proposals.append({"id": 0, "author": "System", "text": "..."})
        
        decision_msg = {"type": EVT_NARRATOR_DECISION_NEEDED, "proposals": game_state.active_proposals, "timeout": TIME_SELECTION}
        if game_state.narrator in active_connections:
            send_json(active_connections[game_state.narrator], decision_msg)
        
        start_timer(TIME_SELECTION, on_narrator_timeout)

def on_narrator_timeout():
    """Tempo narratore scaduto."""
    with lock:
        if not game_state.is_running: return
        print("[TIMEOUT] Narratore assente. Scelta automatica.")
        
        # 1. Scelta casuale se ci sono proposte
        if game_state.active_proposals:
            random_prop = random.choice(game_state.active_proposals)
            game_state.select_proposal(random_prop['id'])
            
            # 2. Aggiorna la storia per tutti
            send_to_all({"type": EVT_STORY_UPDATE, "story": game_state.story})
            
            # 3. AUTO-CONTINUE: Non chiediamo, andiamo avanti
            new_seg_id = game_state.start_new_segment()
            
            # Avvisiamo che il server ha scelto
            send_to_all({
                "type": EVT_NEW_SEGMENT, 
                "segment_id": new_seg_id, 
                "timeout": TIME_PROPOSAL
            })
            
            # 4. Riavvia timer scrittura
            start_timer(TIME_PROPOSAL, on_proposal_timeout)

def on_voting_timeout():
    with lock:
        print("[TIMEOUT] Voto scaduto.")
        process_vote_check(force_end=True)

# --- FLUSSO ---

def check_round_completion():
    active_writers = game_state.count_active_writers()
    current_props = len(game_state.active_proposals)
    
    print(f"[CHECK] {current_props}/{active_writers}")
    if current_props >= active_writers and active_writers > 0:
        stop_timer() 
        print("[INFO] Turno completato.")
        decision_msg = {"type": EVT_NARRATOR_DECISION_NEEDED, "proposals": game_state.active_proposals, "timeout": TIME_SELECTION}
        with lock:
            if game_state.narrator in active_connections:
                send_json(active_connections[game_state.narrator], decision_msg)
        start_timer(TIME_SELECTION, on_narrator_timeout)

def process_vote_check(force_end=False):
    total_connected = len(game_state.players)
    total_voted = len(game_state.player_votes)
    send_to_all({"type": EVT_VOTE_UPDATE, "count": total_voted, "needed": total_connected})

    if (total_voted >= total_connected and total_connected > 0) or force_end:
        stop_timer()
        print("[VOTO] Fine.")
        game_state.is_running = False
        users_leaving = []
        
        # Chi non ha votato allo scadere torna in lobby
        all_users = list(game_state.players.keys())
        with lock:
            for user_id in all_users:
                # Se NO -> esce
                if user_id in game_state.player_votes and not game_state.player_votes[user_id]:
                    sock = active_connections.get(user_id)
                    if sock: send_json(sock, {"type": EVT_GOODBYE, "msg": "Arrivederci!"})
                    users_leaving.append(user_id)
                # Altrimenti (SI o NON VOTATO) -> Lobby
                else:
                    sock = active_connections.get(user_id)
                    if sock: send_json(sock, {"type": EVT_RETURN_TO_LOBBY})

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
                            send_json(conn, {"type": EVT_NEW_SEGMENT, "segment_id": game_state.current_segment_id, "timeout": TIME_PROPOSAL})
                    else:
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
                    send_to_all({"type": EVT_NEW_SEGMENT, "segment_id": seg_id, "timeout": TIME_PROPOSAL})
                    start_timer(TIME_PROPOSAL, on_proposal_timeout)
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
                stop_timer()
                proposal_id = int(msg.get('proposal_id'))
                success, new_story = game_state.select_proposal(proposal_id)
                if success:
                    send_to_all({"type": EVT_STORY_UPDATE, "story": new_story})
                    send_json(conn, {"type": EVT_ASK_CONTINUE, "timeout": 15})
                    
                    # Timer Auto-Continue se il narratore si addormenta sulla domanda
                    def auto_continue():
                        with lock:
                            if not game_state.is_running: return
                            print("[TIMEOUT] Narratore non decide su continua. Auto-Continue.")
                            new_id = game_state.start_new_segment()
                            send_to_all({"type": EVT_NEW_SEGMENT, "segment_id": new_id, "timeout": TIME_PROPOSAL})
                            start_timer(TIME_PROPOSAL, on_proposal_timeout)
                            
                    start_timer(15, auto_continue)
                else:
                    send_json(conn, {"type": "ERROR", "msg": "ID non valido"})

            elif msg_type == CMD_DECIDE_CONTINUE:
                if user_id != game_state.narrator: continue
                stop_timer()
                action = msg.get('action')
                if action == "CONTINUE":
                    new_seg_id = game_state.start_new_segment()
                    send_to_all({"type": EVT_NEW_SEGMENT, "segment_id": new_seg_id, "timeout": TIME_PROPOSAL})
                    start_timer(TIME_PROPOSAL, on_proposal_timeout)
                elif action == "STOP":
                    print("Fine partita richiesta.")
                    send_to_all({"type": EVT_GAME_ENDED, "final_story": game_state.story, "timeout": TIME_VOTING})
                    game_state.is_running = False 
                    start_timer(TIME_VOTING, on_voting_timeout)

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
        
        if game_state.is_running and user_id == game_state.narrator:
            print("[ALERT] Narratore disconnesso.")
            stop_timer()
            send_to_all({"type": EVT_RETURN_TO_LOBBY, "msg": "Narratore caduto. Reset."})
            game_state.abort_game()
        
        new_leader = game_state.remove_player(user_id)
        if new_leader:
            with lock:
                if new_leader in active_connections:
                    send_json(active_connections[new_leader], {"type": EVT_LEADER_UPDATE, "msg": "Sei il nuovo Leader!"})

        if game_state.is_running: check_round_completion()
        elif not game_state.is_running and game_state.player_votes: process_vote_check()
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