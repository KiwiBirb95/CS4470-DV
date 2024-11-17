import json
import socket
import sys
import threading
import time

INFINITY = float('inf')

def get_local_ip():
    """Determine the server's local IP by connecting to Google DNS."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as temp_socket:
            # Connect to Google DNS (no actual data is sent)
            temp_socket.connect(("8.8.8.8", 80))
            local_ip = temp_socket.getsockname()[0]
        return local_ip
    except Exception as e:
        print(f"Error determining local IP: {e}")
        return None

class DistanceVectorRouting:
    def __init__(self, topology_file, update_interval):
        self.topology_file = topology_file
        self.update_interval = update_interval
        self.routing_table = {}
        self.neighbors = {}
        self.server_id = None
        self.port = None
        self.ip = None
        self.server_socket = None
        self.connections = {}  # {connection_id: (socket, address)}
        self.packet_count = 0
        self.routing_table_lock = threading.Lock()

    def parse_topology_file(self):
        """Parse the topology file and initialize neighbors and routing table."""
        print(f"Attempting to load topology file: {self.topology_file}")
        try:
            with open(self.topology_file, 'r') as file:
                lines = file.readlines()
                print(f"Topology file content: {lines}")

                if len(lines) < 2:
                    raise ValueError("Invalid topology file format: less than 2 lines.")

                num_servers = int(lines[0].strip())
                num_neighbors = int(lines[1].strip())

                self.server_details = {}
                for i in range(2, 2 + num_servers):
                    try:
                        server_id, server_ip, server_port = lines[i].strip().split()
                        self.server_details[int(server_id)] = (server_ip, int(server_port))
                    except ValueError:
                        raise ValueError(f"Invalid server details format on line {i + 1}: {lines[i]}")

                print(f"Parsed server details: {self.server_details}")

                # Determine self.server_id based on the local IP
                local_ip = get_local_ip()
                print(f"Detected local IP: {local_ip}")
                for server_id, (server_ip, server_port) in self.server_details.items():
                    if server_ip == local_ip:
                        self.server_id = server_id
                        self.ip = server_ip
                        self.port = server_port
                        break

                if self.server_id is None:
                    raise ValueError(f"Local IP {local_ip} does not match any server in the topology file.")

                self.neighbors = {}
                for i in range(2 + num_servers, len(lines)):
                    try:
                        server1, server2, cost = lines[i].strip().split()
                        server1, server2, cost = int(server1), int(server2), int(cost)

                        if server1 == self.server_id:
                            self.neighbors[server2] = cost
                        elif server2 == self.server_id:
                            self.neighbors[server1] = cost
                    except ValueError:
                        raise ValueError(f"Invalid neighbor format on line {i + 1}: {lines[i]}")

                print(f"Parsed neighbors: {self.neighbors}")

                # Initialize routing table
                for server_id in self.server_details.keys():
                    if server_id in self.neighbors:
                        self.routing_table[server_id] = (server_id, self.neighbors[server_id])
                    elif server_id == self.server_id:
                        self.routing_table[server_id] = (server_id, 0)
                    else:
                        self.routing_table[server_id] = (None, INFINITY)

            print("Topology file parsed successfully.")
        except Exception as e:
            print(f"Error reading topology file: {str(e)}")
            sys.exit(1)

    def setup_server_socket(self):
        """Set up the TCP server socket."""
        try:
            if self.ip is None or self.port is None:
                raise ValueError(f"Server IP ({self.ip}) or port ({self.port}) is not set.")

            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.bind((self.ip, self.port))
            self.server_socket.listen(5)
            print(f"Server started at {self.ip}:{self.port}, listening for connections...")
        except Exception as e:
            print(f"Error setting up server socket: {e}")
            sys.exit(1)

    def accept_connections(self):
        """Accept incoming connections from neighbors."""
        while True:
            client_socket, client_address = self.server_socket.accept()
            print(f"New connection from {client_address}")
            connection_id = len(self.connections) + 1
            self.connections[connection_id] = (client_socket, client_address)
            threading.Thread(target=self.handle_client, args=(client_socket, connection_id), daemon=True).start()

    def connect_to_neighbors(self):
        """Establish connections to all neighbors."""
        for neighbor_id, (neighbor_ip, neighbor_port) in self.server_details.items():
            if neighbor_id != self.server_id:
                try:
                    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    client_socket.connect((neighbor_ip, neighbor_port))
                    connection_id = len(self.connections) + 1
                    self.connections[connection_id] = (client_socket, (neighbor_ip, neighbor_port))
                    print(f"Connected to neighbor {neighbor_id} at {neighbor_ip}:{neighbor_port}")
                    threading.Thread(target=self.handle_client, args=(client_socket, connection_id), daemon=True).start()
                except Exception as e:
                    print(f"Error connecting to neighbor {neighbor_id}: {e}")

    def handle_client(self, client_socket, connection_id):
        """Handle communication with a connected neighbor."""
        try:
            while True:
                message = client_socket.recv(1024).decode()
                if not message:
                    break
                self.handle_incoming_message(message)
        except Exception as e:
            print(f"Connection {connection_id} error: {e}")
        finally:
            client_socket.close()
            del self.connections[connection_id]

    def handle_incoming_message(self, message):
        """Handle incoming routing update messages."""
        try:
            update = json.loads(message)
            print(f"Received routing update: {update}")
            with self.routing_table_lock:
                # Process routing update...
                pass
        except Exception as e:
            print(f"Error handling incoming message: {e}")

    def send_update(self):
        """Send routing updates to all neighbors."""
        update_message = json.dumps({
            'server_id': self.server_id,
            'routing_table': self.routing_table
        })
        with self.routing_table_lock:
            for connection_id, (client_socket, _) in self.connections.items():
                try:
                    client_socket.sendall(update_message.encode())
                except Exception as e:
                    print(f"Error sending update to connection {connection_id}: {e}")

    def periodic_updates(self):
        """Send periodic routing updates to neighbors."""
        while True:
            time.sleep(self.update_interval)
            self.send_update()

    def handle_display(self):
        """Display the current routing table."""
        print("Routing Table:")
        for destination_id in sorted(self.routing_table.keys()):
            next_hop, cost = self.routing_table[destination_id]
            cost_str = "inf" if cost == INFINITY else str(cost)
            print(f"{destination_id} {next_hop if next_hop else '-'} {cost_str}")

    def connection_list(self):
        """Display active connections."""
        print("Active Connections:")
        for connection_id, (_, address) in self.connections.items():
            print(f"{connection_id}: {address}")

    def listen_for_commands(self):
        """Listen for user commands and execute actions."""
        while True:
            command = input("Enter command: ").strip()
            if command == "list":
                self.connection_list()
            elif command == "display":
                self.handle_display()
            elif command == "step":
                self.send_update()
            else:
                print("Unknown command")

    def start_server(self):
        """Start the server."""
        threading.Thread(target=self.accept_connections, daemon=True).start()
        threading.Thread(target=self.connect_to_neighbors, daemon=True).start()
        threading.Thread(target=self.periodic_updates, daemon=True).start()
        self.listen_for_commands()


if __name__ == "__main__":
    if len(sys.argv) != 5 or sys.argv[1] != "-t" or sys.argv[3] != "-i":
        print("Usage: python dv.py -t <topology-file-name> -i <routing-update-interval>")
        sys.exit(1)

    topology_file = sys.argv[2]
    update_interval = int(sys.argv[4])
    print(f"Parsed arguments: Topology file: {topology_file}, Update interval: {update_interval}")  # Debugging line

    server = DistanceVectorRouting(topology_file, update_interval)
    server.parse_topology_file()
    server.setup_server_socket()
    server.start_server()

