import struct
import logging
from fsconfig import InvalidOperation


class Inode:
    def __init__(self, config):
        self.config = config
        self.type = config.inode_type_invalid
        self.size = 0
        self.refcnt = 0
        self.block_numbers = [0] * config.max_inode_block_numbers

    def inode_from_bytearray(self, b):
        if len(b) > self.config.inode_size:
            raise InvalidOperation('inode_from_bytearray: exceeds inode size ' + str(b))

        n = self.config.max_inode_block_numbers
        fmt = '>IHH' + str(n) + 'I'
        values = struct.unpack_from(fmt, b)
        self.size = values[0]
        self.type = values[1]
        self.refcnt = values[2]
        for i in range(n):
            self.block_numbers[i] = values[3 + i]

    def inode_to_bytearray(self):
        n = self.config.max_inode_block_numbers
        fmt = '>IHH' + str(n) + 'I'
        return bytearray(struct.pack(fmt, self.size, self.type, self.refcnt, *self.block_numbers))

    def print_inode(self):
        logging.info('Inode size   : ' + str(self.size))
        logging.info('Inode type   : ' + str(self.type))
        logging.info('Inode refcnt : ' + str(self.refcnt))
        logging.info('Block numbers: ')
        s = ""
        for i in range(0, self.config.max_inode_block_numbers):
            s += str(self.block_numbers[i])
            s += ","
        logging.info(s)
