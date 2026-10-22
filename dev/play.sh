#!/bin/bash


num_players=3
if [ "$1" != "" ]; then
  port=$1
else
  port=8888
fi

# Start the server; trap the pid and store it in a variable
python3 -m src.sixtyfivekmconvoy.server.serve --port $port --players $num_players 2>&1 | tee server.log &
server_pid=$!
trap "kill -9 $server_pid 2>/dev/null" EXIT
echo "Server pid: $server_pid"

# Wait for server to be ready by checking the log file
# The server prints: "Waiting for $num_players players on port $port"
echo "Waiting for server to start on port $port..."
max_attempts=50
attempt=0
while [ $attempt -lt $max_attempts ]; do
    if [ -f server.log ] && grep -q "Waiting for $num_players players on port $port" server.log 2>/dev/null; then
        echo "Server is ready!"
        break
    fi
    sleep 0.1
    echo -n "."
    attempt=$((attempt + 1))
done

if [ $attempt -ge $max_attempts ]; then
    echo "Warning: Server startup message not found in log, continuing anyway..."
fi

# Quiet mode (default) - no output
python3 -m src.sixtyfivekmconvoy.client.randomclient --port $port 2>&1 | tee client1.log &
# catch the pid and store it in a variable
client_pid1=$!
echo "Client pid: $client_pid1"
#trap "kill -9 $client_pid1" EXIT

# Quiet mode (default) - no output
python3 -m src.sixtyfivekmconvoy.client.randomclient --port $port 2>&1 | tee client2.log &
# catch the pid and store it in a variable
client_pid2=$!
echo "Client pid: $client_pid2"
#trap "kill -9 $client_pid2" EXIT

## Verbose mode - displays game state
python3 -m src.sixtyfivekmconvoy.client.randomclient --port $port --verbose 2>&1 | tee client3.log &
# catch the pid and store it in a variable
client_pid3=$!
echo "Client pid: $client_pid3"
#trap "kill -9 $client_pid3" EXIT

# With custom host
#python3 -m src.sixtyfivekmconvoy.client.terminalclient --host localhost --port 8888 


trap "kill -9 $server_pid $client_pid1 $client_pid2 $client_pid3" EXIT


wait $server_pid $client_pid1 $client_pid2 $client_pid3