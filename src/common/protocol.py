import json
import struct

# Costanti per i comandi (Client -> Server) [cite: 243]
CMD_JOIN = "JOIN_STORY"
CMD_SUBMIT = "SUBMIT_PROPOSAL"
CMD_HEARTBEAT = "HEARTBEAT"
CMD_DISCONNECT = "DISCONNECT"
CMD_SELECT_PROPOSAL = "SELECT_PROPOSAL" # Comando del narratore

# Costanti per gli eventi (Server -> Client) [cite: 249]
EVT_WELCOME = "WELCOME" # Risposta al Join
EVT_NEW_ROUND = "START_STORY"
EVT_NEW_SEGMENT = "START_SEGMENT"
EVT_UPDATE_PROPOSALS = "PROPOSALS_RECEIVED"
EVT_NARRATOR_ASSIGNED = "NARRATOR_ASSIGNED"
EVT_STORY_UPDATE = "STORY_UPDATE"

def send_json(sock, data):
    """
    Invia un messaggio JSON con un header di lunghezza (4 byte).
    Questo risolve problemi di frammentazione TCP.
    """
    msg_body = json.dumps(data).encode('utf-8')
    msg_len = struct.pack('!I', len(msg_body))
    sock.sendall(msg_len + msg_body)

def recv_json(sock):
    """
    Riceve un messaggio JSON leggendo prima la lunghezza.
    """
    try:
        # Leggi i primi 4 byte per la lunghezza
        raw_msglen = recvall(sock, 4)
        if not raw_msglen:
            return None
        msglen = struct.unpack('!I', raw_msglen)[0]
        
        # Leggi il corpo del messaggio
        raw_msg = recvall(sock, msglen)
        return json.loads(raw_msg.decode('utf-8'))
    except Exception as e:
        print(f"Errore ricezione dati: {e}")
        return None

def recvall(sock, n):
    """Funzione helper per assicurarsi di ricevere n byte."""
    data = bytearray()
    while len(data) < n:
        packet = sock.recv(n - len(data))
        if not packet:
            return None
        data.extend(packet)
    return data