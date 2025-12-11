import socket
import threading
import sys
import os
import time
import random 

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from common.protocol import *
from gamestate import GameState

HOST = '127.0.0.1'
PORT = 65432

# Timeout (secondi)
TIME_PROPOSAL = 60
TIME_SELECTION = 30
TIME_VOTING = 30
HEARTBEAT_TIMEOUT = 8

game_state = GameState()
active_connections = {} 
last_active = {} 
lock = threading.RLock() # Thread-safety per GameState
game_timer = None 

def send_to_all(msg):
    with lock:
        for sock in active_connections.values():
            try: send_json(sock, msg)
            except: pass

def start_timer(duration, callback):
    """Avvia timer asincrono, cancellando i precedenti."""
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

def monitor_connections():
    """Watchdog per disconnettere client inattivi (heartbeat)."""
    while True:
        time.sleep(2)
        now = time.time()
        to_kick = []
        with lock:
            for addr, last_time in last_active.items():
                if now - last_time > HEARTBEAT_TIMEOUT:
                    print(f"[HEARTBEAT] Timeout {addr}")
                    to_kick.append(addr)
            for addr in to_kick:
                if addr in active_connections:
                    try: active_connections[addr].close()
                    except: pass

def on_proposal_timeout():
    """Timeout scrittura: forza passaggio a selezione."""
    with lock:
        if not game_state.is_running: return
        print("[TIMEOUT] Scrittura scaduta.")
        
        # STOP CRITICO: Chiude fase scrittura
        game_state.phase = "SELECTING"
        game_state.save_state()

        if not game_state.active_proposals:
            game_state.active_proposals.append({"id": 0, "author": "System", "text": "..."})
            
        decision_msg = {
            "type": EVT_NARRATOR_DECISION_NEEDED, 
            "proposals": game_state.active_proposals, 
            "timeout": TIME_SELECTION
        }
        
        if game_state.narrator in active_connections:
            send_json(active_connections[game_state.narrator], decision_msg)
            
        start_timer(TIME_SELECTION, on_narrator_timeout)

def on_narrator_timeout():
    """Timeout narratore: scelta casuale automatica."""
    with lock:
        if not game_state.is_running: return
        print("[TIMEOUT] Narratore assente. Auto-scelta.")
        
        if game_state.active_proposals:
            random_prop = random.choice(game_state.active_proposals)
            game_state.select_proposal(random_prop['id'])
            
            send_to_all({"type": EVT_STORY_UPDATE, "story": game_state.story})
            
            # Reset a fase scrittura
            new_seg_id = game_state.start_new_segment()
            send_to_all({"type": EVT_NEW_SEGMENT, "segment_id": new_seg_id, "timeout": TIME_PROPOSAL})
            start_timer(TIME_PROPOSAL, on_proposal_timeout)

def on_voting_timeout():
    with lock:
        print("[TIMEOUT] Voto scaduto.")
        process_vote_check(force_end=True)

def check_round_completion():
    """Se tutti hanno scritto, avanza subito."""
    active_writers = game_state.count_active_writers()
    current_props = len(game_state.active_proposals)
    
    if current_props >= active_writers and active_writers > 0:
        stop_timer() 
        game_state.phase = "SELECTING" # Blocca invii tardivi
        game_state.save_state()
        
        decision_msg = {
            "type": EVT_NARRATOR_DECISION_NEEDED, 
            "proposals": game_state.active_proposals, 
            "timeout": TIME_SELECTION
        }
        
        with lock:
            if game_state.narrator in active_connections:
                send_json(active_connections[game_state.narrator], decision_msg)
        
        start_timer(TIME_SELECTION, on_narrator_timeout)

def process_vote_check(force_end=False):
    """Gestisce votazione riavvio."""
    total = len(game_state.players)
    voted = len(game_state.player_votes)
    send_to_all({"type": EVT_VOTE_UPDATE, "count": voted, "needed": total})

    if (voted >= total and total > 0) or force_end:
        stop_timer()
        game_state.is_running = False
        
        users_leaving = []
        all_users = list(game_state.players.keys())
        
        with lock:
            for uid in all_users:
                sock = active_connections.get(uid)
                # Chi vota NO viene disconnesso
                if uid in game_state.player_votes and not game_state.player_votes[uid]:
                    if sock: send_json(sock, {"type": EVT_GOODBYE, "msg": "Grazie!"})
                    users_leaving.append(uid)
                else:
                    if sock: send_json(sock, {"type": EVT_RETURN_TO_LOBBY})

        time.sleep(0.2) 

        for uid in users_leaving:
            with lock:
                if uid in active_connections:
                    try: active_connections[uid].close()
                    except: pass
                    del active_connections[uid]
            
            # Gestione cambio leader
            new_leader = game_state.remove_player(uid) 
            if new_leader:
                with lock:
                    if new_leader in active_connections:
                        send_json(active_connections[new_leader], {"type": EVT_LEADER_UPDATE, "msg": "Sei Leader!"})
        
        game_state.player_votes.clear()
        game_state.phase = "LOBBY"
        game_state.save_state()

def handle_client(conn, addr):
    print(f"Connessione: {addr}")
    with lock:
        active_connections[addr] = conn
        last_active[addr] = time.time()
    
    user_id = addr
    try:
        while True:
            msg = recv_json(conn)
            if not msg: break
            
            with lock: last_active[addr] = time.time()
            mtype = msg.get('type')
            
            if mtype == CMD_HEARTBEAT: continue

            if mtype == CMD_JOIN:
                username = game_state.add_player(user_id, msg.get('username', 'Anon'))
                is_leader = (game_state.leader == user_id)
                send_json(conn, {"type": EVT_WELCOME, "msg": f"Ciao {username}", "is_leader": is_leader})

                if game_state.is_running:
                    # Recovery
                    narrator_name = game_state.players.get(game_state.narrator, "?")
                    am_i_narrator = (game_state.narrator == user_id)
                    in_game = (username in game_state.story_usernames)
                    
                    evt = {
                        "type": EVT_GAME_STARTED, 
                        "narrator": narrator_name, 
                        "theme": game_state.current_theme, 
                        "am_i_narrator": am_i_narrator, 
                        "is_spectator": not in_game
                    }
                    send_json(conn, evt)
                    send_json(conn, {"type": EVT_STORY_UPDATE, "story": game_state.story})
                    
                    if in_game and not am_i_narrator and not game_state.has_user_submitted(username) and game_state.phase == "WRITING":
                        send_json(conn, {"type": EVT_NEW_SEGMENT, "segment_id": game_state.current_segment_id, "timeout": TIME_PROPOSAL})

            elif mtype == CMD_START_GAME:
                if game_state.is_running or game_state.leader != user_id:
                     send_json(conn, {"type": "ERROR", "msg": "Non permesso."})
                     continue
                
                success, info = game_state.start_new_story()
                if success:
                    base_evt = {"type": EVT_GAME_STARTED, "narrator": info['narrator_name'], "theme": info['theme'], "is_spectator": False}
                    with lock:
                        for p_addr, p_sock in active_connections.items():
                            evt = base_evt.copy()
                            evt["am_i_narrator"] = (p_addr == info['narrator_id'])
                            send_json(p_sock, evt)
                    
                    sid = game_state.start_new_segment()
                    send_to_all({"type": EVT_NEW_SEGMENT, "segment_id": sid, "timeout": TIME_PROPOSAL})
                    start_timer(TIME_PROPOSAL, on_proposal_timeout)

            elif mtype == CMD_SUBMIT:
                # GameState controlla fase (WRITING). Rifiuta se in SELECTING.
                ok, res = game_state.add_proposal(user_id, msg.get('text'))
                if ok: check_round_completion()
                else: send_json(conn, {"type": "ERROR", "msg": res})

            elif mtype == CMD_SELECT_PROPOSAL:
                if user_id != game_state.narrator: continue
                stop_timer()
                
                ok, story = game_state.select_proposal(int(msg.get('proposal_id')))
                if ok:
                    send_to_all({"type": EVT_STORY_UPDATE, "story": story})
                    send_json(conn, {"type": EVT_ASK_CONTINUE, "timeout": 15})
                    
                    def auto_cont():
                        with lock:
                            if not game_state.is_running: return
                            nid = game_state.start_new_segment()
                            send_to_all({"type": EVT_NEW_SEGMENT, "segment_id": nid, "timeout": TIME_PROPOSAL})
                            start_timer(TIME_PROPOSAL, on_proposal_timeout)
                    start_timer(15, auto_cont)
                else: send_json(conn, {"type": "ERROR", "msg": "ID invalido"})

            elif mtype == CMD_DECIDE_CONTINUE:
                if user_id != game_state.narrator: continue
                stop_timer()
                if msg.get('action') == "CONTINUE":
                    nid = game_state.start_new_segment()
                    send_to_all({"type": EVT_NEW_SEGMENT, "segment_id": nid, "timeout": TIME_PROPOSAL})
                    start_timer(TIME_PROPOSAL, on_proposal_timeout)
                elif msg.get('action') == "STOP":
                    game_state.save_to_history()
                    game_state.is_running = False 
                    game_state.phase = "VOTING"
                    game_state.save_state()
                    send_to_all({"type": EVT_GAME_ENDED, "final_story": game_state.story, "timeout": TIME_VOTING})
                    start_timer(TIME_VOTING, on_voting_timeout)

            elif mtype == CMD_VOTE_RESTART:
                game_state.register_vote(user_id, True)
                process_vote_check()
            elif mtype == CMD_VOTE_NO:
                game_state.register_vote(user_id, False)
                process_vote_check()

    except Exception: pass 
    finally:
        with lock:
            if addr in active_connections: del active_connections[addr]
            if addr in last_active: del last_active[addr]
        
        if game_state.is_running and user_id == game_state.narrator:
            stop_timer()
            send_to_all({"type": EVT_RETURN_TO_LOBBY, "msg": "Narratore uscito."})
            game_state.abort_game()
        
        new_lead = game_state.remove_player(user_id)
        if new_lead:
            with lock:
                if new_lead in active_connections:
                    send_json(active_connections[new_lead], {"type": EVT_LEADER_UPDATE, "msg": "Sei Leader!"})

        if game_state.is_running: check_round_completion()
        elif not game_state.is_running and game_state.player_votes: process_vote_check()
        conn.close()

def start_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen()
    print(f"[SERVER] Ready on {HOST}:{PORT}")
    
    threading.Thread(target=monitor_connections, daemon=True).start()
    while True:
        conn, addr = server.accept()
        threading.Thread(target=handle_client, args=(conn, addr)).start()

if __name__ == "__main__":
    start_server()