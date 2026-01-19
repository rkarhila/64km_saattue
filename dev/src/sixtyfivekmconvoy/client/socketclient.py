#! /usr/bin/env python3

"""
This module contains the SocketClient class for a socket client.

The client connects to a server and sends and receives messages.
Messages are sent and received as JSON, and choice responses are lists of integers.
"""

import json
import socket


class SocketClient:

  def __init__(self, conf):
    self.conf = conf
    self.socket = None 
    self._receive_buffer = ''  # Buffer for receiving JSON messages

  def connect(self, host, port):
    """Connect to the server."""
    self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    self.socket.connect((host, port))

  def disconnect(self):
    if self.socket:
      self.socket.close()
      self.socket = None
    self._receive_buffer = ''

  def _send_json(self, data):
    """Send JSON-encoded data over the socket."""
    if not self.socket:
      raise ConnectionError("Not connected to server")
    json_str = json.dumps(data) + '\n'
    self.socket.sendall(json_str.encode('utf-8'))

  def _receive_json(self):
    """Receive and parse JSON data from the socket."""
    if not self.socket:
      raise ConnectionError("Not connected to server")
    # Read line-by-line to handle JSON messages, using instance buffer to preserve data
    buffer = self._receive_buffer
    while True:
      try:
        data = self.socket.recv(4096)
      except (ConnectionResetError, BrokenPipeError, OSError) as e:
        raise ConnectionError(f"Socket connection error: {e}")
      if not data:
        raise ConnectionError("Socket connection closed")
      buffer += data.decode('utf-8')
      
      # Process complete lines from the buffer
      while '\n' in buffer:
        line, buffer = buffer.split('\n', 1)
        line = line.strip()
        if not line:
          # Skip empty lines
          continue
        
        # Only try to parse lines that look like JSON (start with { or [)
        if line.startswith('{') or line.startswith('['):
          try:
            json_obj = json.loads(line)
            # Save remaining buffer for next call
            self._receive_buffer = buffer
            return json_obj
          except json.JSONDecodeError:
            # If this looks like JSON but parsing failed, it might be incomplete
            # Put it back in buffer and wait for more data
            buffer = line + '\n' + buffer
            break
        # Otherwise, skip this line (might be debug output or other non-JSON text)
    
    # Save buffer for next call (no complete message yet)
    self._receive_buffer = buffer

  def push_info(self, state=None):
    """Receive game state information as JSON from the server.
    
    If state is None, reads from socket. Otherwise, this is called by local clients
    and the default implementation reads from socket.
    """
    # For socket clients, receive JSON from the server
    return self._receive_json()

  def await_choice(self, candidates=None):
    """Receive candidates as JSON, make a choice, and send back a list of integers.
    
    If candidates is None, reads from socket. Otherwise, this is called by local clients.
    The default implementation reads candidates from socket, makes a choice (should be
    overridden by subclasses), and sends back the choice as a list of integers.
    """
    # Receive candidates as JSON from the server
    if candidates is None:
      candidates = self._receive_json()
    
    # Make a choice (should be overridden by subclasses that know how to choose)
    # For now, default to first option if it's a list
    if isinstance(candidates, list) and len(candidates) > 0:
      choice = [candidates[0]]
    elif isinstance(candidates, dict) and 'options' in candidates:
      # Handle dictionary format with 'options' key
      options = candidates['options']
      if len(options) > 0:
        choice = [options[0]]
      else:
        choice = []
    else:
      choice = []
    
    # Send back the choice as a list of integers
    self._send_json(choice)
    return choice 
  
  def send_choice(self, choice):
    """Send a choice (list of integers) as JSON to the server."""
    # Ensure choice is a list of integers
    if isinstance(choice, int):
      choice = [choice]
    elif not isinstance(choice, list):
      raise ValueError(f"Choice must be a list of integers, got {type(choice)}")
    self._send_json([int(x) for x in choice]) 




