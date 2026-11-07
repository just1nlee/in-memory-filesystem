import logging
from collections import namedtuple
from fsconfig import InvalidOperation
from inodenumber import InodeNumber

DirEntry = namedtuple('DirEntry', ['name', 'inode_number'])


class FileName:
    def __init__(self, raw_blocks, config):
        self.raw_blocks = raw_blocks
        self.config = config

    def get_dir_entry(self, block, index):
        logging.debug('FileName::get_dir_entry: ' + str(block.hex()) + ', ' + str(index))
        string_start = index * self.config.file_name_direntry_size
        string_end = string_start + self.config.max_filename
        inode_start = string_end
        inode_end = inode_start + self.config.inode_number_direntry_size
        name = block[string_start:string_end]
        inode_number = int.from_bytes(block[inode_start:inode_end], byteorder='big')
        return DirEntry(name, inode_number)

    def find_available_inode(self):
        logging.debug('FileName::find_available_inode: ')
        for i in range(0, self.config.max_num_inodes):
            inode_number = InodeNumber(i, self.raw_blocks, self.config)
            inode_number.inode_number_to_inode()
            if inode_number.inode.type == self.config.inode_type_invalid:
                logging.debug("FileName::find_available_inode: " + str(i))
                return i
        logging.debug("FileName::find_available_inode: no available inodes")
        return -1

    def find_available_file_entry(self, dir_inode_num):
        logging.debug('FileName::find_available_file_entry: dir: ' + str(dir_inode_num))
        inode_number = InodeNumber(dir_inode_num, self.raw_blocks, self.config)
        inode_number.inode_number_to_inode()
        if inode_number.inode.size >= self.config.max_file_size:
            logging.debug("FileName::find_available_file_entry: no entries available")
            return -1
        logging.debug("FileName::find_available_file_entry: " + str(inode_number.inode.size))
        return inode_number.inode.size

    def insert_filename_inode_number(self, insert_to, filename, inodenumber):
        logging.debug('FileName::insert_filename_inode_number: ' + str(filename) + ', ' + str(inodenumber))

        if len(filename) > self.config.max_filename:
            raise InvalidOperation('FileName::insert_filename_inode_number: file name exceeds maximum')

        if insert_to.inode.type != self.config.inode_type_dir:
            raise InvalidOperation('FileName::insert_filename_inode_number: not a directory inode: ' + str(insert_to.inode.type))

        index = insert_to.inode.size
        if index >= self.config.max_file_size:
            raise InvalidOperation('FileName::insert_filename_inode_number: no space for another entry in inode')

        block_number_index = index // self.config.block_size
        if index % self.config.block_size == 0:
            if index != 0:
                new_block = self.raw_blocks.allocate_data_block()
                insert_to.inode.block_numbers[block_number_index] = new_block

        block_number = insert_to.inode.block_numbers[block_number_index]
        block = self.raw_blocks.get(block_number)

        index_modulo = index % self.config.block_size

        string_start = index_modulo
        string_end = string_start + self.config.max_filename
        stringbyte = bytearray(filename, "utf-8")

        inode_start = index_modulo + self.config.max_filename
        inode_end = inode_start + self.config.inode_number_direntry_size

        logging.debug('FileName::insert_filename_inode_number: block read \n' + str(block.hex()))
        logging.debug('FileName::insert_filename_inode_number: string_start ' + str(string_start) + ', string_end ' + str(string_end))
        logging.debug('FileName::insert_filename_inode_number: inode_start ' + str(inode_start) + ', inode_end ' + str(inode_end))

        block[string_start:string_end] = bytearray(stringbyte.ljust(self.config.max_filename, b'\x00'))
        block[inode_start:inode_end] = inodenumber.to_bytes(self.config.inode_number_direntry_size, 'big')
        self.raw_blocks.put(block_number, block)

        logging.debug('FileName::insert_filename_inode_number: insert_to.inode.size ' + str(insert_to.inode.size))
        insert_to.inode.size += self.config.file_name_direntry_size
        insert_to.store_inode()

    def remove_filename_entry(self, dir_inode, name):
        logging.debug('FileName::remove_filename_entry: name: ' + str(name))

        block_index = 0
        num_blocks = (dir_inode.inode.size // self.config.block_size) + 1
        tempdirtable = bytearray(num_blocks * self.config.block_size)
        while block_index < num_blocks:
            src = self.raw_blocks.get(dir_inode.inode.block_numbers[block_index])
            tempdirtable[block_index * self.config.block_size:block_index * self.config.block_size + self.config.block_size] = src
            block_index += 1
        logging.debug("FileName::remove_filename_entry: tempdirtable: " + str(tempdirtable.hex()))

        padded_filename = bytearray(name, "utf-8")
        padded_filename = bytearray(padded_filename.ljust(self.config.max_filename, b'\x00'))

        current_position = 0
        end_position = dir_inode.inode.size
        while current_position < end_position:
            entryname = tempdirtable[current_position:current_position + self.config.max_filename]
            entryname_padded = bytearray(entryname.ljust(self.config.max_filename, b'\x00'))
            if entryname_padded == padded_filename:
                logging.debug("FileName::remove_filename_entry: found a match " + str(padded_filename))
                break
            else:
                current_position += self.config.file_name_direntry_size

        while current_position < end_position:
            tempdirtable[current_position:current_position + self.config.file_name_direntry_size] = tempdirtable[current_position + self.config.file_name_direntry_size:current_position + 2 * self.config.file_name_direntry_size]
            current_position += self.config.file_name_direntry_size

        block_index = 0
        while block_index < num_blocks:
            logging.debug("FileName::remove_filename_entry: writing back block_index " + str(block_index))
            self.raw_blocks.put(dir_inode.inode.block_numbers[block_index], tempdirtable[block_index * self.config.block_size:block_index * self.config.block_size + self.config.block_size])
            block_index += 1

        dir_inode.inode.size = dir_inode.inode.size - self.config.file_name_direntry_size
        dir_inode.inode.refcnt -= 1
        dir_inode.store_inode()

    def init_root_inode(self):
        logging.debug('FileName::init_root_inode')

        root_inode = InodeNumber(0, self.raw_blocks, self.config)
        root_inode.inode_number_to_inode()
        root_inode.inode.type = self.config.inode_type_dir
        root_inode.inode.size = 0
        root_inode.inode.refcnt = 1
        logging.debug('FileName::init_root_inode: calling allocate_data_block')
        root_inode.inode.block_numbers[0] = self.raw_blocks.allocate_data_block()
        logging.debug('FileName::init_root_inode: calling insert_filename_inode_number')
        self.insert_filename_inode_number(root_inode, ".", 0)
        logging.debug('FileName::init_root_inode: calling store_inode')
        root_inode.store_inode()

    def lookup(self, filename, dir_inode_num):
        logging.debug('FileName::lookup: ' + str(filename) + ', ' + str(dir_inode_num))

        inode_number = InodeNumber(dir_inode_num, self.raw_blocks, self.config)
        inode_number.inode_number_to_inode()

        if inode_number.inode.type != self.config.inode_type_dir:
            logging.error("FileName::lookup: not a directory inode: " + str(dir_inode_num) + " , " + str(inode_number.inode.type))
            return -1

        offset = 0
        scanned = 0
        while offset < inode_number.inode.size:
            b = inode_number.inode_number_to_block(offset)

            for i in range(0, self.config.file_entries_per_data_block):
                if inode_number.inode.size > scanned:
                    scanned += self.config.file_name_direntry_size

                    entry = self.get_dir_entry(b, i)
                    logging.debug("FileName::lookup for " + filename + " in " + str(dir_inode_num) + ": searching string " + str(entry.name))
                    padded_filename = bytearray(filename, "utf-8")
                    padded_filename = bytearray(padded_filename.ljust(self.config.max_filename, b'\x00'))

                    if entry.name == padded_filename:
                        logging.debug("FileName::lookup successful: " + str(entry.inode_number))
                        return entry.inode_number

            offset += self.config.block_size

        logging.debug("FileName::lookup: file not found: " + str(filename) + " in " + str(dir_inode_num))
        return -1
