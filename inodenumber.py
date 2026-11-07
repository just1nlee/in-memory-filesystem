import logging
from fsconfig import InodeNotAvailable
from inode import Inode


class InodeNumber:
    def __init__(self, number, raw_blocks, config):
        self.config = config
        self.raw_blocks = raw_blocks
        self.inode = Inode(config)

        if number > config.max_num_inodes:
            raise InodeNotAvailable('InodeNumber::Init: inode number exceeds limit: ' + str(number))
        self.inode_number = number

    def inode_number_to_inode(self):
        logging.debug('InodeNumber::inode_number_to_inode: ' + str(self.inode_number))

        inode_table_raw_block_number = self.config.inode_block_offset + ((self.inode_number * self.config.inode_size) // self.config.block_size)
        inode_table_raw_block = self.raw_blocks.get(inode_table_raw_block_number)

        start = (self.inode_number * self.config.inode_size) % self.config.block_size
        end = start + self.config.inode_size
        inode_slice = inode_table_raw_block[start:end]

        self.inode.inode_from_bytearray(inode_slice)

        logging.debug('InodeNumber::inode_number_to_inode: inode_number ' + str(self.inode_number) + ' raw_block_number: ' + str(inode_table_raw_block_number) + ' slice start: ' + str(start) + ' end: ' + str(end))
        logging.debug('inode_slice: ' + str(inode_slice.hex()))

    def store_inode(self):
        logging.debug('InodeNumber::store_inode: ' + str(self.inode_number))

        inode_table_raw_block_number = self.config.inode_block_offset + ((self.inode_number * self.config.inode_size) // self.config.block_size)
        logging.debug('InodeNumber::store_inode: inode_table_raw_block_number ' + str(inode_table_raw_block_number))

        inode_table_raw_block = self.raw_blocks.get(inode_table_raw_block_number)
        logging.debug('InodeNumber::store_inode: inode_table_raw_block:\n' + str(inode_table_raw_block.hex()))

        start = (self.inode_number * self.config.inode_size) % self.config.block_size
        end = start + self.config.inode_size
        logging.debug('InodeNumber::store_inode: start: ' + str(start) + ', end: ' + str(end))

        inode_bytearray = self.inode.inode_to_bytearray()
        inode_table_raw_block[start:end] = inode_bytearray
        logging.debug('InodeNumber::store_inode: tempblock:\n' + str(inode_table_raw_block.hex()))

        self.raw_blocks.put(inode_table_raw_block_number, inode_table_raw_block)

    def inode_number_to_block(self, offset):
        logging.debug('InodeNumber::inode_number_to_block: ' + str(offset))

        self.inode_number_to_inode()
        o = offset // self.config.block_size
        b = self.inode.block_numbers[o]
        block = self.raw_blocks.get(b)
        return block
