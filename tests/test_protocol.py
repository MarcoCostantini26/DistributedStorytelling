import unittest
import sys
import os
import json
import struct

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from common.protocol import send_json, recv_json

class MockSocket:
    def __init__(self, data_to_receive=b""):
        self.sent_data = b""        
        self.incoming_data = data_to_receive 

    def sendall(self, data):
        """Simula l'invio: accumula i byte."""
        self.sent_data += data

    def recv(self, bufsize):
        """Simula la ricezione: restituisce i byte dal buffer."""
        if not self.incoming_data:
            return b""
        chunk = self.incoming_data[:bufsize]
        self.incoming_data = self.incoming_data[bufsize:]
        return chunk

class TestProtocol(unittest.TestCase):

    def test_send_json_format(self):
        """Verifica che send_json aggiunga correttamente l'header di lunghezza."""
        mock_sock = MockSocket()
        message = {"type": "TEST", "content": "Ciao"}
        
        send_json(mock_sock, message)
        
        expected_json = json.dumps(message).encode('utf-8')
        expected_len = struct.pack('!I', len(expected_json))
        
        self.assertEqual(mock_sock.sent_data, expected_len + expected_json)

    def test_recv_json_decoding(self):
        """Verifica che recv_json legga e decodifichi correttamente."""
        msg_dict = {"type": "LOGIN", "user": "Mario"}
        msg_bytes = json.dumps(msg_dict).encode('utf-8')
        msg_len = struct.pack('!I', len(msg_bytes))
        
        mock_sock = MockSocket(data_to_receive=(msg_len + msg_bytes))
        
        received_obj = recv_json(mock_sock)
        
        self.assertEqual(received_obj, msg_dict)
        self.assertEqual(received_obj['user'], "Mario")

    def test_recv_empty(self):
        """Verifica che se il socket è chiuso restituisca None."""
        mock_sock = MockSocket(data_to_receive=b"") 
        result = recv_json(mock_sock)
        self.assertIsNone(result)

if __name__ == '__main__':
    unittest.main()