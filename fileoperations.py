import logging
from inodenumber import InodeNumber


class FileOperations:
    def __init__(self, file_name_object, config):
        self.file_name_object = file_name_object
        self.config = config

    def _block_ranges(self, offset, length):
        """Yields (block_index, start_in_block, end_in_block, data_offset) tuples."""
        data_offset = 0
        current_offset = offset
        end = offset + length
        while data_offset < length:
            block_index = current_offset // self.config.block_size
            next_boundary = (block_index + 1) * self.config.block_size
            start_in_block = current_offset % self.config.block_size
            if end >= next_boundary:
                end_in_block = self.config.block_size
            else:
                end_in_block = end % self.config.block_size
            chunk = end_in_block - start_in_block
            yield block_index, start_in_block, end_in_block, data_offset
            data_offset += chunk
            current_offset += chunk

    def create(self, dir_inode_num, name, type_val):
        logging.debug("FileOperations::create: dir: " + str(dir_inode_num) + ", name: " + str(name) + ", type: " + str(type_val))

        if not (type_val == self.config.inode_type_file or type_val == self.config.inode_type_dir):
            logging.debug("ERROR_CREATE_INVALID_TYPE " + str(type_val))
            return -1, "ERROR_CREATE_INVALID_TYPE"

        inode_position = self.file_name_object.find_available_inode()
        if inode_position == -1:
            logging.debug("ERROR_CREATE_INODE_NOT_AVAILABLE")
            return -1, "ERROR_CREATE_INODE_NOT_AVAILABLE"

        dir_inode = InodeNumber(dir_inode_num, self.file_name_object.raw_blocks, self.config)
        dir_inode.inode_number_to_inode()
        if dir_inode.inode.type != self.config.inode_type_dir:
            logging.debug("ERROR_CREATE_INVALID_DIR " + str(dir_inode_num))
            return -1, "ERROR_CREATE_INVALID_DIR"

        fileentry_position = self.file_name_object.find_available_file_entry(dir_inode_num)
        if fileentry_position == -1:
            logging.debug("ERROR_CREATE_DATA_BLOCK_NOT_AVAILABLE")
            return -1, "ERROR_CREATE_DATA_BLOCK_NOT_AVAILABLE"

        if self.file_name_object.lookup(name, dir_inode_num) != -1:
            logging.debug("ERROR_CREATE_ALREADY_EXISTS " + str(name))
            return -1, "ERROR_CREATE_ALREADY_EXISTS"

        logging.debug("FileOperations::create: inode_position: " + str(inode_position) + ", fileentry_position: " + str(fileentry_position))

        if type_val == self.config.inode_type_dir:
            newdir_inode = InodeNumber(inode_position, self.file_name_object.raw_blocks, self.config)
            newdir_inode.inode_number_to_inode()
            newdir_inode.inode.type = self.config.inode_type_dir
            newdir_inode.inode.size = 0
            newdir_inode.inode.refcnt = 1
            newdir_inode.inode.block_numbers[0] = self.file_name_object.raw_blocks.allocate_data_block()
            newdir_inode.store_inode()

            self.file_name_object.insert_filename_inode_number(dir_inode, name, inode_position)
            self.file_name_object.insert_filename_inode_number(newdir_inode, ".", inode_position)
            self.file_name_object.insert_filename_inode_number(newdir_inode, "..", dir_inode_num)

            dir_inode.inode.refcnt += 1
            dir_inode.store_inode()

        elif type_val == self.config.inode_type_file:
            newfile_inode = InodeNumber(inode_position, self.file_name_object.raw_blocks, self.config)
            newfile_inode.inode_number_to_inode()
            newfile_inode.inode.type = self.config.inode_type_file
            newfile_inode.inode.size = 0
            newfile_inode.inode.refcnt = 1
            newfile_inode.store_inode()

            self.file_name_object.insert_filename_inode_number(dir_inode, name, inode_position)

            dir_inode.inode.refcnt += 1
            dir_inode.store_inode()

        return inode_position, "SUCCESS"

    def write(self, file_inode_number, offset, data):
        logging.debug(
            "FileOperations::write: file_inode_number: " + str(file_inode_number) + ", offset: " + str(offset) + ", len(data): " + str(len(data)))

        file_inode = InodeNumber(file_inode_number, self.file_name_object.raw_blocks, self.config)
        file_inode.inode_number_to_inode()

        if file_inode.inode.type != self.config.inode_type_file:
            logging.debug("ERROR_WRITE_NOT_FILE " + str(file_inode_number))
            return -1, "ERROR_WRITE_NOT_FILE"

        if offset > file_inode.inode.size:
            logging.debug("ERROR_WRITE_OFFSET_LARGER_THAN_SIZE " + str(offset))
            return -1, "ERROR_WRITE_OFFSET_LARGER_THAN_SIZE"

        if offset + len(data) > self.config.max_file_size:
            logging.debug("ERROR_WRITE_EXCEEDS_FILE_SIZE " + str(offset + len(data)))
            return -1, "ERROR_WRITE_EXCEEDS_FILE_SIZE"

        bytes_written = 0
        for block_index, write_start, write_end, data_offset in self._block_ranges(offset, len(data)):
            logging.debug('FileOperations::write: current_block_index: ' + str(block_index) + ' , write_start: ' + str(write_start) + ' , write_end: ' + str(write_end))

            block_number = file_inode.inode.block_numbers[block_index]
            if block_number == 0:
                new_block = self.file_name_object.raw_blocks.allocate_data_block()
                file_inode.inode.block_numbers[block_index] = new_block
                block_number = new_block

            block = self.file_name_object.raw_blocks.get(block_number)
            chunk = write_end - write_start
            block[write_start:write_end] = data[data_offset:data_offset + chunk]
            self.file_name_object.raw_blocks.put(block_number, block)
            bytes_written += chunk

            logging.debug('FileOperations::write: bytes_written: ' + str(bytes_written) + ' , len(data): ' + str(len(data)))

        file_inode.inode.size = offset + bytes_written
        file_inode.store_inode()

        return bytes_written, "SUCCESS"

    def read(self, file_inode_number, offset, count):
        logging.debug("FileOperations::read: file_inode_number: " + str(file_inode_number) + ", offset: " + str(offset) + ", count: " + str(count))

        file_inode = InodeNumber(file_inode_number, self.file_name_object.raw_blocks, self.config)
        file_inode.inode_number_to_inode()

        if file_inode.inode.type != self.config.inode_type_file:
            logging.debug("ERROR_READ_NOT_FILE " + str(file_inode_number))
            return -1, "ERROR_READ_NOT_FILE"

        if offset > file_inode.inode.size:
            logging.debug("ERROR_READ_OFFSET_LARGER_THAN_SIZE " + str(offset))
            return -1, "ERROR_READ_OFFSET_LARGER_THAN_SIZE"

        if offset + count > file_inode.inode.size:
            bytes_to_read = file_inode.inode.size - offset
        else:
            bytes_to_read = count

        read_data = bytearray(bytes_to_read)

        for block_index, read_start, read_end, data_offset in self._block_ranges(offset, bytes_to_read):
            logging.debug('FileOperations::read: current_block_index: ' + str(block_index) + ' , read_start: ' + str(read_start) + ' , read_end: ' + str(read_end))

            block_number = file_inode.inode.block_numbers[block_index]
            block = self.file_name_object.raw_blocks.get(block_number)

            chunk = read_end - read_start
            read_data[data_offset:data_offset + chunk] = block[read_start:read_end]

            logging.debug('FileOperations::read: data_offset: ' + str(data_offset + chunk))

        return read_data, "SUCCESS"

    def slice_file(self, file_inode_number, offset, count):
        logging.debug("FileOperations::slice_file: file_inode_number: " + str(file_inode_number) + ", offset: " + str(offset) + ", count: " + str(count))
        file_inode = InodeNumber(file_inode_number, self.file_name_object.raw_blocks, self.config)
        file_inode.inode_number_to_inode()
        if offset > file_inode.inode.size:
            logging.debug("ERROR_SLICE_OFFSET_OUT_BOUNDS " + str(offset))
            return -1, "ERROR_SLICE_OFFSET_OUT_BOUNDS"
        if (offset + count) > file_inode.inode.size:
            logging.debug("ERROR_SLICE_COUNT_OUT_BOUNDS " + str(count + offset))
            return -1, "ERROR_SLICE_COUNT_OUT_BOUNDS"
        block_slice, status = self.read(file_inode_number, offset, count)
        if status == -1:
            logging.debug("ERROR_SLICE_READ_ERROR")
            return -1, "ERROR_SLICE_READ_ERROR"
        bytes_written, message = self.write(file_inode_number, 0, block_slice)
        return bytes_written, message

    def mirror(self, file_inode_number):
        logging.debug("FileOperations::mirror: file_inode_number: " + str(file_inode_number))
        file_inode = InodeNumber(file_inode_number, self.file_name_object.raw_blocks, self.config)
        file_inode.inode_number_to_inode()
        block_original, status = self.read(file_inode_number, 0, file_inode.inode.size)
        if status == -1:
            logging.debug("ERROR_MIRROR_READ_ERROR")
            return -1, "ERROR_MIRROR_READ_ERROR"
        block_mirrored = bytearray(file_inode.inode.size)
        for i in range(0, file_inode.inode.size):
            block_mirrored[file_inode.inode.size - i - 1] = block_original[i]
        bytes_written, message = self.write(file_inode_number, 0, block_mirrored)
        return bytes_written, message

    def link(self, name, inode, dir_node_num):
        logging.debug("FileOperations::link: name: " + str(name) + ", inode: " + str(inode) + ", dir_node_num: " + str(dir_node_num))

        dir_inode = InodeNumber(dir_node_num, self.file_name_object.raw_blocks, self.config)
        dir_inode.inode_number_to_inode()
        if dir_inode.inode.type != self.config.inode_type_dir:
            logging.debug("ERROR_LINK_NOT_DIRECTORY " + str(dir_node_num))
            return -1, "ERROR_LINK_NOT_DIRECTORY"

        # Find available slot in directory data block
        if self.file_name_object.find_available_file_entry(dir_node_num) == -1:
            logging.debug("ERROR_LINK_DATA_BLOCK_NOT_AVAILABLE")
            return -1, "ERROR_LINK_DATA_BLOCK_NOT_AVAILABLE"

        # Reject duplicate name in the directory
        if self.file_name_object.lookup(name, dir_node_num) != -1:
            logging.debug("ERROR_LINK_ALREADY_EXISTS " + str(name))
            return -1, "ERROR_LINK_ALREADY_EXISTS"

        # Add (name, inode) to the directory's table
        self.file_name_object.insert_filename_inode_number(dir_inode, name, inode)

        # Update refcnt of target inode
        target_inode = InodeNumber(inode, self.file_name_object.raw_blocks, self.config)
        target_inode.inode_number_to_inode()
        target_inode.inode.refcnt += 1
        target_inode.store_inode()

        # Update refcnt of directory
        dir_inode.inode.refcnt += 1
        dir_inode.store_inode()

        return 0, "SUCCESS"

    def unlink(self, dir_inode_num, name):
        logging.debug("FileOperations::unlink: dir: " + str(dir_inode_num) + ", name: " + str(name))

        dir_inode = InodeNumber(dir_inode_num, self.file_name_object.raw_blocks, self.config)
        dir_inode.inode_number_to_inode()
        if dir_inode.inode.type != self.config.inode_type_dir:
            logging.debug("ERROR_UNLINK_INVALID_DIR " + str(dir_inode_num))
            return -1, "ERROR_UNLINK_INVALID_DIR"

        file_inode_num = self.file_name_object.lookup(name, dir_inode_num)
        if file_inode_num == -1:
            logging.debug("ERROR_UNLINK_DOESNOT_EXIST " + str(name))
            return -1, "ERROR_UNLINK_DOESNOT_EXIST"

        file = InodeNumber(file_inode_num, self.file_name_object.raw_blocks, self.config)
        file.inode_number_to_inode()
        if file.inode.type != self.config.inode_type_file and file.inode.type != self.config.inode_type_sym:
            logging.debug("ERROR_UNLINK_NOT_FILE " + str(name))
            return -1, "ERROR_UNLINK_NOT_FILE"

        # Step 1: Remove binding from directory
        # Note: remove_filename_entry also decrements dir_inode.refcnt internally
        self.file_name_object.remove_filename_entry(dir_inode, name)

        # Step 2: Decrement refcnt of file being unlinked
        file.inode.refcnt -= 1
        file.store_inode()

        # Step 3: If last reference, free data blocks and inode
        if file.inode.refcnt == 0:
            logging.debug("FileOperations::unlink: last reference; freeing data blocks and inode")
            for i in range(0, self.config.max_inode_block_numbers):
                block_number = file.inode.block_numbers[i]
                if block_number != 0:
                    self.file_name_object.raw_blocks.free_data_block(block_number)

            new_blank_inode = InodeNumber(file_inode_num, self.file_name_object.raw_blocks, self.config)
            new_blank_inode.store_inode()

        return 0, "SUCCESS"
