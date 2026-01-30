import socket
import threading
import sys
import os
import time
import random 
import json

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from common.protocol import *
from gamestate import GameState

HOST = '127.0.0.1'
GAME_PORT_MASTER = 65432
REPLICATION_PORT = 7000  
REPLICATION_HOST = '127.0.0.1'

TIME_PROPOSAL = 60
TIME_SELECTION = 30
TIME_VOTING = 30
HEARTBEAT_TIMEOUT = 8

game_state = GameState()
active_connections = {} 
last_active = {} 
lock = threading.RLock()
game_timer = None 

AM_I_MASTER = False
SLAVE_SOCKETS = [] 

# =========================================================
#  LOGICA DI ELEZIONE E REPLICAZIONE
# =========================================================

def replication_listener_loop(server_sock):
    """(Solo Master) Accetta connessioni dagli Slave usando il socket GIÀ APERTO."""
    try:
        server_sock.listen(5) 
        print(f"[REPLICA-MASTER] Hub di replica ATTIVO su porta {REPLICATION_PORT}.")
        
        while True:
            conn, addr = server_sock.accept()
            with lock:
                SLAVE_SOCKETS.append(conn)
            send_state_to_single_socket(conn)
    except Exception as e:
        print(f"[REPLICA-ERROR] Listener terminato: {e}")

def send_state_to_single_socket(sock):
    try:
        state_data = game_state.get_state_dict()
        msg_body = json.dumps(state_data).encode('utf-8')
        sock.sendall(msg_body + b'\n__END__\n')
    except Exception:
        with lock:
            if sock in SLAVE_SOCKETS: SLAVE_SOCKETS.remove(sock)

def sync_state_to_all_slaves():
    if not SLAVE_SOCKETS: return
    state_data = game_state.get_state_dict()
    msg_body = json.dumps(state_data).encode('utf-8')
    payload = msg_body + b'\n__END__\n'
    to_remove = []
    with lock:
        for sock in SLAVE_SOCKETS:
            try: sock.sendall(payload)
            except: to_remove.append(sock)
        for dead_sock in to_remove:
            SLAVE_SOCKETS.remove(dead_sock)

def attempt_promotion():
    """Tenta di acquisire la porta 7000 in modo ESCLUSIVO."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind((REPLICATION_HOST, REPLICATION_PORT))
        return s
    except OSError:
        return None

def run_as_slave(my_port):
    """
    Tutti iniziano da qui.
    1. Provo a connettermi a chi comanda (porta 7000).
    2. Se riesco -> Sono Slave (sync dati).
    3. Se fallisco -> Provo a diventare Master (bind 7000).
    """
    global AM_I_MASTER, game_state
    print(f"[ROLE] Inizializzazione nodo su porta {my_port}...")
    
    time.sleep(random.random() * 1.5)

    while not AM_I_MASTER:
        connected = False
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2)
            s.connect((REPLICATION_HOST, REPLICATION_PORT))
            s.settimeout(None)
            connected = True
            
            print(f"[SLAVE] Trovato Master! Entro in modalità passiva (Backup per porta {my_port}).")
            
            buffer = ""
            while True:
                data = s.recv(4096)
                if not data: raise Exception("Master closed")
                
                buffer += data.decode('utf-8')
                while '__END__\n' in buffer:
                    parts = buffer.split('__END__\n', 1)
                    json_str = parts[0]
                    buffer = parts[1]
                    try:
                        data = json.loads(json_str)
                        with lock:
                            game_state.apply_state_dict(data)
                            game_state.save_state()
                    except: pass

        except (ConnectionRefusedError, OSError, Exception):
            if connected: print("[SLAVE] Master perso/caduto.")
            
            print("[ELECTION] Nessun Master rilevato. Tento la promozione...")
            
            rep_socket = attempt_promotion()
            
            if rep_socket:
                print(f"[ELECTION] Ho vinto la gara! Divento MASTER.")
                become_master(my_port, rep_socket)
                break
            else:
                print("[ELECTION] Porta 7000 occupata da qualcun altro. Riprovo a connettermi...")
                for i in range(10):
                    time.sleep(0.5)
                    try:
                        test = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        test.connect((REPLICATION_HOST, REPLICATION_PORT))
                        test.close()
                        break
                    except: pass
                continue 

def become_master(port, rep_sock):
    global AM_I_MASTER
    AM_I_MASTER = True
    print("\n" + "!"*50)
    print(f"!!! MASTER ATTIVO SU PORTA {port} !!!")
    print("!"*50 + "\n")
    start_game_server(port, rep_sock)

# =========================================================
#  CORE E TIMERS
# =========================================================

original_save = game_state.save_state
def hooked_save_state():
    original_save() 
    if AM_I_MASTER:
        sync_state_to_all_slaves() 
game_state.save_state = hooked_save_state

def send_to_all(msg):
    with lock:
        for sock in active_connections.values():
            try: send_json(sock, msg)
            except: pass

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

def resume_game_timers():
    if not game_state.is_running: return
    print(f"[RESUME] Ripristino timer fase: {game_state.phase}")
    if game_state.phase == "WRITING":
        start_timer(TIME_PROPOSAL, on_proposal_timeout)
    elif game_state.phase == "SELECTING":
        start_timer(TIME_SELECTION, on_narrator_timeout)
    elif game_state.phase == "VOTING":
        start_timer(TIME_VOTING, on_voting_timeout)

def monitor_connections():
    while True:
        time.sleep(2)
        if not AM_I_MASTER: continue
        now = time.time()
        to_kick = []
        with lock:
            for addr, last_time in last_active.items():
                if now - last_time > HEARTBEAT_TIMEOUT:
                    to_kick.append(addr)
            for addr in to_kick:
                sock = active_connections.get(addr)
                if sock:
                    try: sock.close()
                    except: pass

def on_proposal_timeout():
    with lock:
        if not game_state.is_running: return
        print("[TIMEOUT] Tempo scrittura scaduto.")
        game_state.phase = "SELECTING"
        game_state.save_state()
        if not game_state.active_proposals:
            game_state.active_proposals.append({"id": 0, "author": "System", "text": "..."})
        decision_msg = {"type": EVT_NARRATOR_DECISION_NEEDED, "proposals": game_state.active_proposals, "timeout": TIME_SELECTION}
        if game_state.narrator in active_connections:
            send_json(active_connections[game_state.narrator], decision_msg)
        start_timer(TIME_SELECTION, on_narrator_timeout)

def on_narrator_timeout():
    with lock:
        if not game_state.is_running: return
        print("[TIMEOUT] Narratore assente.")
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

def check_round_completion():
    active_writers = game_state.count_active_writers()
    current_props = len(game_state.active_proposals)
    if current_props >= active_writers and active_writers > 0:
        stop_timer() 
        game_state.phase = "SELECTING"
        game_state.save_state()
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
                    if sock: send_json(sock, {"type": EVT_GOODBYE, "msg": "Grazie!"})
                    users_leaving.append(user_id)
                else:
                    sock = active_connections.get(user_id)
                    if sock: send_json(sock, {"type": EVT_RETURN_TO_LOBBY})
        time.sleep(0.2) 
        for uid in users_leaving:
            with lock:
                if uid in active_connections:
                    try: active_connections[uid].close()
                    except: pass
                    del active_connections[uid]
            new_leader_addr = game_state.remove_player(uid) 
            if new_leader_addr:
                with lock:
                    if new_leader_addr in active_connections:
                        send_json(active_connections[new_leader_addr], {"type": EVT_LEADER_UPDATE, "msg": "Sei il Leader!"})
        game_state.player_votes.clear()
        game_state.phase = "LOBBY" 
        game_state.save_state()

def handle_client(conn, addr):
    print(f"Nuova connessione da {addr}")
    with lock:
        active_connections[addr] = conn
        last_active[addr] = time.time()
    user_id = addr
    try:
        while True:
            msg = recv_json(conn)
            if not msg: break
            with lock: last_active[addr] = time.time()
            msg_type = msg.get('type')
            
            if msg_type == CMD_HEARTBEAT: continue
            if not AM_I_MASTER: break

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
                        if am_i_narrator and game_state.phase == "SELECTING":
                             send_json(conn, {"type": EVT_NARRATOR_DECISION_NEEDED, "proposals": game_state.active_proposals, "timeout": TIME_SELECTION})
                        elif not am_i_narrator and game_state.phase == "WRITING" and not game_state.has_user_submitted(username):
                            send_json(conn, {"type": EVT_NEW_SEGMENT, "segment_id": game_state.current_segment_id, "timeout": TIME_PROPOSAL})
                    else:
                        send_json(conn, {"type": EVT_GAME_STARTED, "narrator": game_state.players.get(game_state.narrator, "???"), "theme": game_state.current_theme, "am_i_narrator": False, "is_spectator": True})
                        send_json(conn, {"type": EVT_STORY_UPDATE, "story": game_state.story})
                game_state.save_state()

            elif msg_type == CMD_START_GAME:
                if game_state.is_running: continue
                if game_state.leader != user_id: continue
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

            elif msg_type == CMD_SUBMIT:
                text = msg.get('text')
                if text == "CRASH_NOW": os._exit(1)
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
                    game_state.save_to_history()
                    game_state.is_running = False 
                    game_state.phase = "VOTING"
                    game_state.save_state()
                    send_to_all({"type": EVT_GAME_ENDED, "final_story": game_state.story, "timeout": TIME_VOTING})
                    start_timer(TIME_VOTING, on_voting_timeout)

            elif msg_type == CMD_VOTE_RESTART:
                game_state.register_vote(user_id, True)
                process_vote_check()
            elif msg_type == CMD_VOTE_NO:
                game_state.register_vote(user_id, False)
                process_vote_check()

    except Exception: pass 
    finally:
        if AM_I_MASTER:
            with lock:
                if addr in active_connections: del active_connections[addr]
                if addr in last_active: del last_active[addr]
            if game_state.is_running and user_id == game_state.narrator:
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

def start_game_server(port, rep_sock):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server.bind((HOST, port))
        server.listen()
        print(f"[SERVER] Master attivo su {HOST}:{port}")
        
        resume_game_timers()

        threading.Thread(target=replication_listener_loop, args=(rep_sock,), daemon=True).start()
        threading.Thread(target=monitor_connections, daemon=True).start()
        
        while True:
            try:
                conn, addr = server.accept()
                threading.Thread(target=handle_client, args=(conn, addr)).start()
            except OSError: break
    except OSError as e:
        print(f"[FATAL] Errore avvio server su porta {port}: {e}")
        rep_sock.close()
    except KeyboardInterrupt:
        print("\n[SERVER] Arresto richiesto. Chiusura...")

if __name__ == "__main__":
    try:
        target_port = GAME_PORT_MASTER
        if len(sys.argv) > 2 and sys.argv[1] == "SLAVE":
            target_port = int(sys.argv[2])
            
        AM_I_MASTER = False
        run_as_slave(target_port)
        
    except KeyboardInterrupt:
        print("\n[MAIN] Uscita.")