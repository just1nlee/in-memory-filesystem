import argparse
import time
import os
import sys
import tempfile
from concurrent import futures
import threading

import grpc
from grpc_tools import protoc


# -----------------------------------------------------------------------------
# Service contract.
# -----------------------------------------------------------------------------

PROTO_SRC = '''syntax = "proto3";

package blockserver;

message PutRequest  { int32  block_number = 1; bytes data = 2; }
message PutReply    { int32  status = 1; }

message GetRequest  { int32  block_number = 1; }
message GetReply    { bytes  data = 1; }

message RSMRequest  { int32  block_number = 1; string request_id = 2; }
message RSMReply    { bytes  data = 1; }

service BlockServer {
    rpc Put (PutRequest) returns (PutReply);
    rpc Get (GetRequest) returns (GetReply);
    rpc RSM (RSMRequest) returns (RSMReply);
}
'''

def _compile_proto():
    """Compile PROTO_SRC into blockserver_pb2 / blockserver_pb2_grpc modules at runtime."""
    tmpdir = tempfile.mkdtemp(prefix="bs_grpc_")
    proto_file = os.path.join(tmpdir, "blockserver.proto")
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
        raise SystemExit("blockserver_grpc: protoc failed to compile embedded .proto")

    sys.path.insert(0, tmpdir)
    import blockserver_pb2          # noqa: E402
    import blockserver_pb2_grpc     # noqa: E402
    return blockserver_pb2, blockserver_pb2_grpc 

blockserver_pb2, blockserver_pb2_grpc = _compile_proto()


# -----------------------------------------------------------------------------
# Servicer: maps RPCs
# -----------------------------------------------------------------------------

class BlockServerServicer(blockserver_pb2_grpc.BlockServerServicer):
  def __init__(self, raw_blocks):
    # initialize blocks
    self.raw_blocks = raw_blocks

  def Put(self, request, context):
    self.raw_blocks.block[request.block_number] = bytearray(request.data)
    self.raw_blocks.Sleep()
    return blockserver_pb2.PutReply(status=0)

  def Get(self, request, context):
    result = bytes(self.raw_blocks.block[request.block_number])
    self.raw_blocks.Sleep()
    return blockserver_pb2.GetReply(data=result)

  def RSM(self, request, context):
    with self.raw_blocks.rsm_lock:
      # Check if this request_id has already been processed (duplicate detection)
      if request.request_id in self.raw_blocks.rsm_reply_cache:
        print("RSM_CACHED_REPLY")
        result = self.raw_blocks.rsm_reply_cache[request.request_id]
        self.raw_blocks.Sleep()
        return blockserver_pb2.RSMReply(data=result)
      RSM_LOCKED = bytearray(b'\x01') * 1
      result = bytes(self.raw_blocks.block[request.block_number])
      self.raw_blocks.block[request.block_number] = bytearray(RSM_LOCKED.ljust(BLOCK_SIZE,b'\x01'))
      # Cache the result for this request_id
      self.raw_blocks.rsm_reply_cache[request.request_id] = result
      self.raw_blocks.Sleep()
    return blockserver_pb2.RSMReply(data=result)

class DiskBlocks():
  def __init__(self, total_num_blocks, block_size, delayat):
    # This class stores the raw block array
    self.block = []
    # initialize request counter
    self.counter = 0
    self.delayat = delayat
    self.rsm_lock = threading.Lock()
    # RSM reply cache for duplicate detection: request_id -> cached result
    self.rsm_reply_cache = {}
    # Initialize raw blocks
    for i in range (0, total_num_blocks):
      putdata = bytearray(block_size)
      self.block.insert(i,putdata)

  def Sleep(self):
    self.counter += 1
    if (self.counter % self.delayat) == 0:
      time.sleep(10)


# -----------------------------------------------------------------------------
# Entry point
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument('-nb', '--total_num_blocks', type=int, help='an integer value')
    ap.add_argument('-bs', '--block_size', type=int, help='an integer value')
    ap.add_argument('-port', '--port', type=int, help='an integer value')
    ap.add_argument('-delayat', '--delayat', type=int, help='an integer value')
    args = ap.parse_args()

    if args.total_num_blocks:
      TOTAL_NUM_BLOCKS = args.total_num_blocks
    else:
      print('Must specify total number of blocks')
      quit()

    if args.block_size:
      BLOCK_SIZE = args.block_size
    else:
      print('Must specify block size')
      quit()

    if args.port:
      PORT = args.port
    else:
      print('Must specify port number')
      quit()

    if args.delayat:
      delayat = args.delayat
    else:
      # initialize delayat with artificially large number
      delayat = 1000000000

    # initialize blocks
    RawBlocks = DiskBlocks(TOTAL_NUM_BLOCKS, BLOCK_SIZE, delayat)

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    blockserver_pb2_grpc.add_BlockServerServicer_to_server(BlockServerServicer(RawBlocks), server)
    server.add_insecure_port(f"127.0.0.1:{args.port}")
    server.start()

    print(f"Running block server on port {args.port}")
    server.wait_for_termination()

