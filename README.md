# Distributed Storytelling

This project is a **distributed collaborative storytelling** engine that allows multiple users to write a story together in real-time.
The system uses a **Client-Server** architecture built with Python and TCP Sockets. Players propose concurrent sentences, and a rotating **Narrator** selects the best one to continue the story.

## How to Run

### 1. Start the Server
The server must be started first to handle connections.
```bash
python src/server/main.py
```

### 2. Start the clients
Open a new terminal for each player who wants to join.
```bash
python src/client/main.py
```
