Start the server:

python3 -m src.sixtyfivekmconvoy.server.serve --port 8888 --players 3 &


Start random clients:

# Quiet mode (default) - no output
python3 -m sixtyfivekmconvoy.client.randomclient --port 8888

# Verbose mode - displays game state
python3 -m sixtyfivekmconvoy.client.randomclient --port 8888 --verbose

# With custom host
python3 -m sixtyfivekmconvoy.client.randomclient --host localhost --port 8888 --verbose


python3 -m src.sixtyfivekmconvoy.client.terminalclient --port 8888
python3 -m src.sixtyfivekmconvoy.client.terminalclient --host localhost --port 8888



The test can be run using:

cd dev/srcpython3 -m sixtyfivekmconvoy.tests.test_end_to_end

Or directly:

cd dev/srcpython3 sixtyfivekmconvoy/tests/test_end_to_end.py
