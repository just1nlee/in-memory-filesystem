"""Tutorial-style gRPC client for the in-memory key/value store.

Interactive shell. Type:
    Put <key> <value>     to store a value under a key
    Get <key>             to retrieve the value stored under a key
    exit                  to quit

<key> and <value> must each be single tokens (no spaces). The client mirrors
the timeout/retry pattern used by block.py in HW3 so students can see the
same shape applied to a simpler service.

Usage:
    python3 keyvalue_client_grpc.py -port 9100
"""

import argparse
import time

import grpc

# Reuse the proto stubs compiled at import time by keyvalue_server_grpc.
# This is the same single-source pattern that block.py uses with
# blockserver_grpc.py — keep the .proto in one place.
from keyvalue_server_grpc import keyvalue_pb2, keyvalue_pb2_grpc


# Per-call deadline (seconds) and pause between retries on a timeout.
# In block.py these come from config.socket_timeout / config.retry_interval.
SOCKET_TIMEOUT = 5
RETRY_INTERVAL = 10


def _is_timeout(rpc_error):
    """True if a grpc.RpcError corresponds to a deadline / availability issue worth retrying.

    Same helper as block.py — students can lift it verbatim into their HW3 client.
    """
    code = rpc_error.code() if hasattr(rpc_error, 'code') else None
    return code in (grpc.StatusCode.DEADLINE_EXCEEDED, grpc.StatusCode.UNAVAILABLE)


def do_put(stub, key, value):
    rpcretry = True
    while rpcretry:
        rpcretry = False
        try:
            reply = stub.Put(
                keyvalue_pb2.PutRequest(key=key, value=value),
                timeout=SOCKET_TIMEOUT,
            )
            print(f"OK status={reply.status}")
        except grpc.RpcError as e:
            if _is_timeout(e):
                print("SERVER_TIMED_OUT")
                time.sleep(RETRY_INTERVAL)
                rpcretry = True
            else:
                raise


def do_get(stub, key):
    rpcretry = True
    while rpcretry:
        rpcretry = False
        try:
            reply = stub.Get(
                keyvalue_pb2.GetRequest(key=key),
                timeout=SOCKET_TIMEOUT,
            )
            if reply.found:
                print(reply.value)
            else:
                print(f"(no entry for '{key}')")
        except grpc.RpcError as e:
            if _is_timeout(e):
                print("SERVER_TIMED_OUT")
                time.sleep(RETRY_INTERVAL)
                rpcretry = True
            else:
                raise

def do_delete(stub, key):
    rpcretry = True
    while rpcretry:
        rpcretry = False
        try:
            reply = stub.Delete(
                keyvalue_pb2.DeleteRequest(key=key),
                timeout=SOCKET_TIMEOUT,
            )
            if reply.found:
                print(reply.value)
            else:
                print(f"(no entry for '{key}')")
        except grpc.RpcError as e:
            if _is_timeout(e):
                print("SERVER_TIMED_OUT")
                time.sleep(RETRY_INTERVAL)
                rpcretry = True
            else:
                raise

def repl(stub):
    print("Commands: Put <key> <value>  |  Get <key>  |  Delete <key>  |  exit")
    while True:
        try:
            line = input("> ").strip()
        except EOFError:
            print()
            return
        if not line:
            continue
        if line == "exit":
            return

        parts = line.split()
        cmd = parts[0]

        if cmd == "Put":
            if len(parts) != 3:
                print("Usage: Put <key> <value>")
                continue
            do_put(stub, parts[1], parts[2])
        elif cmd == "Get":
            if len(parts) != 2:
                print("Usage: Get <key>")
                continue
            do_get(stub, parts[1])
        elif cmd == "Delete":
            if len(parts) != 2:
                print("Usage: Delete <key>")
                continue
            do_delete(stub, parts[1])
        else:
            print(f"Unknown command: {cmd}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument('-port', '--port', type=int, required=True, help='server TCP port')
    args = ap.parse_args()

    channel = grpc.insecure_channel(f"127.0.0.1:{args.port}")
    stub = keyvalue_pb2_grpc.KeyValueStub(channel)
    repl(stub)
