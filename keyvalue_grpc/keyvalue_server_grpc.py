"""Tutorial-style gRPC server: simple in-memory key/value store.

Exposes two RPCs:

    Put(key, value)  -> status   (stores value under key)
    Get(key)         -> (value, found)

Both key and value are strings. Intended as a stepping-stone example for
students transitioning from XML-RPC to gRPC before tackling HW3's
blockserver_grpc.py.

Requires:
    pip install grpcio grpcio-tools

Usage:
    python3 keyvalue_server_grpc.py -port 9100
"""

import argparse
import os
import sys
import tempfile
from concurrent import futures

import grpc
from grpc_tools import protoc


# -----------------------------------------------------------------------------
# Service contract.
# Same single-file pattern as blockserver_grpc.py: the .proto is embedded as
# a string and compiled at startup so this server lives in one file.
# -----------------------------------------------------------------------------

PROTO_SRC = '''syntax = "proto3";

package keyvalue;

message PutRequest  { string key = 1; string value = 2; }
message PutReply    { int32  status = 1; }

message GetRequest  { string key = 1; }
message GetReply    { string value = 1; bool found = 2; }

message DeleteRequest { string key = 1; }
message DeleteReply   { string value = 1; bool found = 2; }

service KeyValue {
    rpc Put (PutRequest) returns (PutReply);
    rpc Get (GetRequest) returns (GetReply);
    rpc Delete (DeleteRequest) returns (DeleteReply);
}
'''


def _compile_proto():
    """Compile PROTO_SRC into keyvalue_pb2 / keyvalue_pb2_grpc modules at runtime."""
    tmpdir = tempfile.mkdtemp(prefix="kv_grpc_")
    proto_file = os.path.join(tmpdir, "keyvalue.proto")
    with open(proto_file, "w") as f:
        f.write(PROTO_SRC)

    well_known = os.path.join(os.path.dirname(protoc.__file__), "_proto")
    rc = protoc.main([
        "grpc_tools.protoc",
        f"-I{tmpdir}",
        f"-I{well_known}",
        f"--python_out={tmpdir}",
        f"--grpc_python_out={tmpdir}",
        proto_file,
    ])
    if rc != 0:
        raise SystemExit("keyvalue_server_grpc: protoc failed to compile embedded .proto")

    sys.path.insert(0, tmpdir)
    import keyvalue_pb2          # noqa: E402
    import keyvalue_pb2_grpc     # noqa: E402
    return keyvalue_pb2, keyvalue_pb2_grpc


keyvalue_pb2, keyvalue_pb2_grpc = _compile_proto()


# -----------------------------------------------------------------------------
# Servicer: maps the two RPCs onto an in-memory dict
# -----------------------------------------------------------------------------

class KeyValueServicer(keyvalue_pb2_grpc.KeyValueServicer):
    def __init__(self):
        self.store = {}

    def Put(self, request, context):
        self.store[request.key] = request.value
        return keyvalue_pb2.PutReply(status=0)

    def Get(self, request, context):
        if request.key in self.store:
            return keyvalue_pb2.GetReply(value=self.store[request.key], found=True)
        return keyvalue_pb2.GetReply(value="", found=False)

    def Delete(self, request, context):
        if request.key in self.store:
            deleted_value = self.store.pop(request.key)
            return keyvalue_pb2.DeleteReply(value=deleted_value, found=True)
        return keyvalue_pb2.DeleteReply(value="", found=False)


# -----------------------------------------------------------------------------
# Entry point
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument('-port', '--port', type=int, required=True, help='TCP port to listen on')
    args = ap.parse_args()

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    keyvalue_pb2_grpc.add_KeyValueServicer_to_server(KeyValueServicer(), server)
    server.add_insecure_port(f"127.0.0.1:{args.port}")
    server.start()

    print(f"Running keyvalue server on port {args.port}")
    server.wait_for_termination()
