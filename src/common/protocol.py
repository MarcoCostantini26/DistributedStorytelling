import json
import struct

# --- COMMANDS (Client -> Server) ---
CMD_START_GAME = "START_GAME"
CMD_JOIN = "JOIN_STORY"
CMD_SUBMIT = "SUBMIT_PROPOSAL"
CMD_HEARTBEAT = "HEARTBEAT"
CMD_DISCONNECT = "DISCONNECT"
CMD_SELECT_PROPOSAL = "SELECT_PROPOSAL"
CMD_DECIDE_CONTINUE = "DECIDE_CONTINUE" 
CMD_VOTE_RESTART = "VOTE_RESTART"
CMD_VOTE_NO = "VOTE_NO"

# --- EVENTS (Server -> Client) ---
EVT_GAME_STARTED = "GAME_STARTED"
EVT_WELCOME = "WELCOME"
EVT_NEW_ROUND = "START_STORY"
EVT_NEW_SEGMENT = "START_SEGMENT"
EVT_UPDATE_PROPOSALS = "PROPOSALS_RECEIVED"
EVT_NARRATOR_ASSIGNED = "NARRATOR_ASSIGNED"
EVT_NARRATOR_DECISION_NEEDED = "NARRATOR_DECISION_NEEDED"
EVT_PROPOSAL_ACK = "PROPOSAL_ACK"
EVT_STORY_UPDATE = "STORY_UPDATE"
EVT_ASK_CONTINUE = "ASK_CONTINUE"
EVT_GAME_ENDED = "GAME_ENDED"
EVT_VOTE_UPDATE = "VOTE_UPDATE"
EVT_RETURN_TO_LOBBY = "RETURN_TO_LOBBY"
EVT_GOODBYE = "GOODBYE"
EVT_LEADER_UPDATE = "LEADER_UPDATE"  

def send_json(sock, data):
    """
    Serializes data to JSON and sends it with a 4-byte length header.
    Format: [Length (4 bytes)] + [JSON Body]
    """
    msg_body = json.dumps(data).encode('utf-8')
    # !I = Network byte order, unsigned int
    msg_len = struct.pack('!I', len(msg_body))
    sock.sendall(msg_len + msg_body)

def recv_json(sock):
    """
    Receives a length-prefixed JSON message handling TCP fragmentation.
    Returns the deserialized dictionary or None on error.
    """
    try:
        # Read header (4 bytes)
        raw_msglen = recvall(sock, 4)
        if not raw_msglen: return None
        msglen = struct.unpack('!I', raw_msglen)[0]
        
        # Read body
        raw_msg = recvall(sock, msglen)
        return json.loads(raw_msg.decode('utf-8'))
    except Exception: return None

def recvall(sock, n):
    """Helper to ensure exactly n bytes are read from the socket."""
    data = bytearray()
    while len(data) < n:
        packet = sock.recv(n - len(data))
        if not packet: return None
        data.extend(packet)
    return data