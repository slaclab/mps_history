import argparse
from pathlib import Path
from mps_processor import HistoryBroker

def get_db_filepath(directory_path):
    """Get the first .db file found in the directory"""
    path = Path(directory_path)
    
    # Find all .db files
    db_files = list(path.glob("*.db"))
    print(f"path: {path}")
    print(f"files: {db_files}")
    
    if db_files:
        print(f"DB file found: {db_files[0].name}")
        return str(db_files[0])
    else:
        return None
    
def main():
    parser = argparse.ArgumentParser(description='Receive MPS history messages')
    parser.add_argument('--port', metavar='port', type=int, nargs='?', help='server port (default=3356)')
    parser.add_argument('--host', metavar='host', help='Server Host (default=localhost)')
    parser.add_argument('--database', metavar='db', nargs=1, default='mps_gun_history.db', 
                        help='database file name (e.g. mps_gun_history.db)') # Currently: database argument isn't used
    parser.add_argument('--dev', action='store_true', help='flag for dev-rhel7 db paths')
    args = parser.parse_args()

    #host = socket.gethostname()
    if args.host:
        host = args.host
    else:
        host = '127.0.0.1'

    #Set default port number
    if args.port:
        port = args.port
    else:    
        port=3356

    # Set dev mode
    if args.dev:
        dev = True
    else:
        dev = False

    # Usage
    if dev:
        current_mps_configuration_dir = "/afs/slac/g/lcls/physics/mps_configuration/9999-99-99-z"
    else:
        current_mps_configuration_dir = "/afs/slac/g/lcls/physics/mps_configuration/current"
    db_filename = get_db_filepath(current_mps_configuration_dir)

    main_processor = HistoryBroker.HistoryBroker(db_filename, dev=dev)
    main_processor.process_loop()

    return

if __name__ == "__main__":
    main()