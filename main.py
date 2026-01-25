import argparse
import json
import os
import shutil
import sys

from config import Config
from generate import Generator


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--config", type=str, default="./config.json")
    parser.add_argument("--serve", action='store_true', default=False)
    parser.add_argument("--no-cache", action='store_true', default=False)
    args = parser.parse_args(sys.argv[1:])

    config: Config | None
    if not os.path.exists(args.config):
        config = None
    else:
        try:
            with open(args.config, "r") as f:
                conf = json.load(f)
            config = Config.from_dict(conf)
        except (json.decoder.JSONDecodeError, FileNotFoundError, KeyError):
            config = None

    if config is None:
        config = Config.default()
        with open(args.config, "w") as f:
            json.dump(config.to_dict(), f, indent=2)

    if args.no_cache:
        shutil.rmtree(config.cache_dir, ignore_errors=True)

    generator = Generator(config)
    generator.run()

    if args.serve:
        serve(config)

def serve(config: Config):
    print(f"[Server] Starting server. Please note that this is not recommended for production use.")
    import http.server
    import socketserver

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(config.output_dir), **kwargs)

    print(f"[Server] Serving at http://localhost:8000")
    with socketserver.TCPServer(("localhost", 8000), Handler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("[Server] Stopping...")
            httpd.shutdown()

if __name__ == '__main__':
    main()
