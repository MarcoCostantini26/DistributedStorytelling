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

# --- CONFIGURAZIONE ---
TIME_PROPOSAL = 60
TIME_SELECTION = 30
TIME_VOTING = 30
HEARTBEAT_TIMEOUT = 8  # Secondi dopo i quali il client è considerato morto

game_state = GameState()
active_connections = {} 
last_active = {} # Map[addr, timestamp] - Ultima volta che abbiamo sentito il client
lock = threading.RLock()

game_timer = None 

def send_to_all(msg):
    with lock:
        for sock in active_connections.values():
            try: send_json(sock, msg)
            except: pass

# --- TIMER GIOCO ---
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

# --- MONITOR HEARTBEAT (Nuovo) ---
def monitor_connections():
    """Controlla periodicamente se i client sono vivi."""
    while True:
        time.sleep(2) # Controlla ogni 2 secondi
        now = time.time()
        to_kick = []

        with lock:
            for addr, last_time in last_active.items():
                if now - last_time > HEARTBEAT_TIMEOUT:
                    print(f"[HEARTBEAT] Client {addr} andato in timeout (>{HEARTBEAT_TIMEOUT}s). Disconnessione.")
                    to_kick.append(addr)
            
            # Disconnettiamo i morti (chiudendo il socket, il thread handle_client gestirà il resto)
            for addr in to_kick:
                sock = active_connections.get(addr)
                if sock:
                    try: sock.close() # Questo farà crashare handle_client, attivando la logica di uscita
                    except: pass

# --- CALLBACK TIMEOUT GIOCO ---

def on_proposal_timeout():
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
    with lock:
        if not game_state.is_running: return
        print("[TIMEOUT] Narratore assente. Auto-scelta.")
        if game_state.active_proposals:
            random_prop = random.choice(game_state.active_proposals)
            game_state.select_proposal(random_prop['id'])
            send_to_all({"type": EVT_STORY_UPDATE, "story": game_state.story})
            new_seg_id = game_state.start_new_segment()
            send_to_all({"type": EVT_NEW_SEGMENT, "segment_id": new_seg_id, "timeout": TIME_PROPOSAL})
            start_timer(TIME_PROPOSAL, on_proposal_timeout)

def on_voting_timeout():
    with lock:
        print("[TIMEOUT] Voto scaduto.")
        process_vote_check(force_end=True)

# --- FLUSSO ---

def check_round_completion():
    active_writers = game_state.count_active_writers()
    current_props = len(game_state.active_proposals)
    if current_props >= active_writers and active_writers > 0:
        stop_timer() 
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
        game_state.is_running = False
        users_leaving = []
        all_users = list(game_state.players.keys())
        with lock:
            for user_id in all_users:
                if user_id in game_state.player_votes and not game_state.player_votes[user_id]:
                    sock = active_connections.get(user_id)
                    if sock: send_json(sock, {"type": EVT_GOODBYE, "msg": "Arrivederci!"})
                    users_leaving.append(user_id)
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
        last_active[addr] = time.time() # Inizializza timer heartbeat
    
    user_id = addr
    
    try:
        while True:
            msg = recv_json(conn)
            if not msg: break
            
            # --- AGGIORNA HEARTBEAT ---
            with lock: last_active[addr] = time.time()
            # --------------------------

            msg_type = msg.get('type')
            
            # Se è solo un heartbeat, ignoriamo il resto della logica
            if msg_type == CMD_HEARTBEAT:
                continue

            if msg_type == CMD_JOIN:
                raw_username = msg.get('username', 'Anonimo')
                username = game_state.add_player(user_id, raw_username)
                is_leader = (game_state.leader == user_id)
                send_json(conn, {"type": EVT_WELCOME, "msg": f"Benvenuto {username}!", "is_leader": is_leader})

                if game_state.is_running:
                    if username in game_state.story_usernames:
                        narrator_name = game_state.players.get(game_state.narrator, "???")
                        am_i_narrator = (game_state.narrator == user_id)
                        send_json(conn, {"type": EVT_GAME_STARTED, "narrator": narrator_name, "theme": game_state.current_theme, "am_i_narrator": am_i_narrator, "is_spectator": False})
                        send_json(conn, {"type": EVT_STORY_UPDATE, "story": game_state.story})
                        if not am_i_narrator and not game_state.has_user_submitted(username):
                            send_json(conn, {"type": EVT_NEW_SEGMENT, "segment_id": game_state.current_segment_id, "timeout": TIME_PROPOSAL})
                    else:
                        send_json(conn, {"type": EVT_GAME_STARTED, "narrator": game_state.players.get(game_state.narrator, "???"), "theme": game_state.current_theme, "am_i_narrator": False, "is_spectator": True})
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
                    evt = {"type": EVT_GAME_STARTED, "narrator": info['narrator_name'], "theme": info['theme'], "is_spectator": False}
                    with lock:
                        for p_addr, p_sock in active_connections.items():
                            evt_personal = evt.copy()
                            evt_personal["am_i_narrator"] = (p_addr == info['narrator_id'])
                            send_json(p_sock, evt_personal)
                    seg_id = game_state.start_new_segment()
                    send_to_all({"type": EVT_NEW_SEGMENT, "segment_id": seg_id, "timeout": TIME_PROPOSAL})
                    start_timer(TIME_PROPOSAL, on_proposal_timeout)
                else: send_json(conn, {"type": "ERROR", "msg": info})

            elif msg_type == CMD_SUBMIT:
                text = msg.get('text')

                # --- AGGIUNGI QUESTO BLOCCO DI TEST ---
                if text == "CRASH_NOW":
                    print("!!! SIMULAZIONE CRASH FATALE !!!")
                    os._exit(1) # Uccide il processo Python istantaneamente
                # --------------------------------------

                success, result = game_state.add_proposal(user_id, text)
                if success: check_round_completion()
                else: send_json(conn, {"type": "ERROR", "msg": result})

            elif msg_type == CMD_SELECT_PROPOSAL:
                if user_id != game_state.narrator: continue
                stop_timer()
                proposal_id = int(msg.get('proposal_id'))
                success, new_story = game_state.select_proposal(proposal_id)
                if success:
                    send_to_all({"type": EVT_STORY_UPDATE, "story": new_story})
                    send_json(conn, {"type": EVT_ASK_CONTINUE, "timeout": 15})
                    
                    def auto_continue():
                        with lock:
                            if not game_state.is_running: return
                            new_id = game_state.start_new_segment()
                            send_to_all({"type": EVT_NEW_SEGMENT, "segment_id": new_id, "timeout": TIME_PROPOSAL})
                            start_timer(TIME_PROPOSAL, on_proposal_timeout)
                    start_timer(15, auto_continue)
                else: send_json(conn, {"type": "ERROR", "msg": "ID non valido"})

            elif msg_type == CMD_DECIDE_CONTINUE:
                if user_id != game_state.narrator: continue
                stop_timer()
                action = msg.get('action')
                if action == "CONTINUE":
                    new_seg_id = game_state.start_new_segment()
                    send_to_all({"type": EVT_NEW_SEGMENT, "segment_id": new_seg_id, "timeout": TIME_PROPOSAL})
                    start_timer(TIME_PROPOSAL, on_proposal_timeout)
                elif action == "STOP":
                    send_to_all({"type": EVT_GAME_ENDED, "final_story": game_state.story, "timeout": TIME_VOTING})
                    game_state.is_running = False 
                    start_timer(TIME_VOTING, on_voting_timeout)

            elif msg_type == CMD_VOTE_RESTART:
                game_state.register_vote(user_id, True)
                process_vote_check()
            elif msg_type == CMD_VOTE_NO:
                game_state.register_vote(user_id, False)
                process_vote_check()

    except Exception:
        pass # Disconnessione gestita nel finally
    finally:
        with lock:
            if addr in active_connections: del active_connections[addr]
            if addr in last_active: del last_active[addr] # Pulizia heartbeat
        
        if game_state.is_running and user_id == game_state.narrator:
            print("[ALERT] Narratore disconnesso.")
            stop_timer()
            send_to_all({"type": EVT_RETURN_TO_LOBBY, "msg": "Narratore caduto."})
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
    
    # AVVIO THREAD MONITORAGGIO HEARTBEAT
    threading.Thread(target=monitor_connections, daemon=True).start()
    
    while True:
        conn, addr = server.accept()
        threading.Thread(target=handle_client, args=(conn, addr)).start()

if __name__ == "__main__":
    start_server()