import logging
from dataclasses import dataclass


# --- Exception hierarchy ---

class FSError(Exception):
    pass

class BlockOutOfRange(FSError):
    pass

class InodeNotAvailable(FSError):
    pass

class FileNotFound(FSError):
    pass

class InvalidOperation(FSError):
    pass


# --- File system configuration as a frozen dataclass ---

@dataclass(frozen=True)
class FSConfig:
    # Primary parameters (may be overridden via CLI)
    total_num_blocks: int = 256
    block_size: int = 128
    max_num_inodes: int = 16
    inode_size: int = 16
    cid: int = 0
    port: int = 8000
    # cmsg: 1 prints CACHE_HIT / CACHE_MISS / CACHE_WRITE_THROUGH /
    # CACHE_INVALIDATED messages, 0 suppresses them.
    cmsg: int = 1

    # Constants that should never be modified
    max_filename: int = 12
    inode_number_direntry_size: int = 4
    freebitmap_block_offset: int = 2
    inode_bytes_size_type_refcnt: int = 8
    inode_bytes_store_block_number: int = 4

    # Inode types
    inode_type_invalid: int = 0
    inode_type_file: int = 1
    inode_type_dir: int = 2
    inode_type_sym: int = 3

    # Network/lock constants
    rsm_unlocked: bytes = None
    rsm_locked: bytes = None
    server_address: str = '127.0.0.1'
    max_clients: int = 8
    socket_timeout: int = 5
    retry_interval: int = 10

    def __post_init__(self):
        if self.rsm_unlocked is None:
            object.__setattr__(self, 'rsm_unlocked', bytearray(b'\x00') * 1)
        if self.rsm_locked is None:
            object.__setattr__(self, 'rsm_locked', bytearray(b'\x01') * 1)

    # Derived properties
    @property
    def inodes_per_block(self):
        return self.block_size // self.inode_size

    @property
    def freebitmap_num_blocks(self):
        return self.total_num_blocks // self.block_size

    @property
    def inode_block_offset(self):
        return 2 + self.freebitmap_num_blocks

    @property
    def inode_num_blocks(self):
        return (self.max_num_inodes * self.inode_size) // self.block_size

    @property
    def max_inode_block_numbers(self):
        return (self.inode_size - self.inode_bytes_size_type_refcnt) // self.inode_bytes_store_block_number

    @property
    def max_file_size(self):
        return self.max_inode_block_numbers * self.block_size

    @property
    def data_blocks_offset(self):
        return self.inode_block_offset + self.inode_num_blocks

    @property
    def data_num_blocks(self):
        return self.total_num_blocks - self.data_blocks_offset

    @property
    def file_name_direntry_size(self):
        return self.max_filename + self.inode_number_direntry_size

    @property
    def file_entries_per_data_block(self):
        return self.block_size // self.file_name_direntry_size

    def print_config(self):
        print('#### File system information:')
        print('Number of blocks          : ' + str(self.total_num_blocks))
        print('Block size (Bytes)        : ' + str(self.block_size))
        print('Number of inodes          : ' + str(self.max_num_inodes))
        print('inode size (Bytes)        : ' + str(self.inode_size))
        print('inodes per block          : ' + str(self.inodes_per_block))
        print('Free bitmap offset        : ' + str(self.freebitmap_block_offset))
        print('Free bitmap size (blocks) : ' + str(self.freebitmap_num_blocks))
        print('Inode table offset        : ' + str(self.inode_block_offset))
        print('Inode table size (blocks) : ' + str(self.inode_num_blocks))
        print('Max blocks per file       : ' + str(self.max_inode_block_numbers))
        print('Data blocks offset        : ' + str(self.data_blocks_offset))
        print('Data block size (blocks)  : ' + str(self.data_num_blocks))
        print('Raw block layer layout: (B: boot, S: superblock, F: free bitmap, I: inode, D: data')
        layout = "BS"
        id_str = "01"
        id_count = 2
        for i in range(0, self.freebitmap_num_blocks):
            layout += "F"
            id_str += str(id_count)
            id_count = (id_count + 1) % 10
        for i in range(0, self.inode_num_blocks):
            layout += "I"
            id_str += str(id_count)
            id_count = (id_count + 1) % 10
        for i in range(0, self.data_num_blocks):
            layout += "D"
            id_str += str(id_count)
            id_count = (id_count + 1) % 10
        print(id_str)
        print(layout)


def configure_fs_constants(args):
    kwargs = {}
    if args.total_num_blocks:
        kwargs['total_num_blocks'] = args.total_num_blocks
    if args.block_size:
        kwargs['block_size'] = args.block_size
    if args.max_num_inodes:
        kwargs['max_num_inodes'] = args.max_num_inodes
    if args.inode_size:
        kwargs['inode_size'] = args.inode_size
    if args.client_id:
        kwargs['cid'] = args.client_id
    if args.port:
        kwargs['port'] = args.port
    # cmsg may legitimately be 0, so test for "not None" instead of truthiness
    if getattr(args, 'cmsg', None) is not None:
        kwargs['cmsg'] = args.cmsg
    return FSConfig(**kwargs)
