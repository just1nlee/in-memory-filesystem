import logging
from inodenumber import InodeNumber


class AbsolutePathName:
    def __init__(self, file_name_object, file_operations_object, config):
        self.file_name_object = file_name_object
        self.file_operations_object = file_operations_object
        self.config = config

    def path_to_inode_number(self, path, dir):

        logging.debug("AbsolutePathName::path_to_inode_number: path: " + str(path) + ", dir: " + str(dir))

        if "/" in path:
            split_path = path.split("/")
            first = split_path[0]
            del split_path[0]
            rest = "/".join(split_path)
            logging.debug("AbsolutePathName::path_to_inode_number: first: " + str(first) + ", rest: " + str(rest))
            d = self.file_name_object.lookup(first, dir)
            if d == -1:
                return -1
            return self.path_to_inode_number(rest, d)
        else:
            return self.file_name_object.lookup(path, dir)

    def general_path_to_inode_number(self, path, cwd):

        logging.debug("AbsolutePathName::general_path_to_inode_number: path: " + str(path) + ", cwd: " + str(cwd))

        if path[0] == "/":
            if len(path) == 1:  # special case: root
                logging.debug("AbsolutePathName::general_path_to_inode_number: returning root inode 0")
                return 0
            cut_path = path[1:len(path)]
            logging.debug("AbsolutePathName::general_path_to_inode_number: cut_path: " + str(cut_path))
            return self.path_to_inode_number(cut_path, 0)
        else:
            return self.path_to_inode_number(path, cwd)

    def path_name_to_inode_number(self, path, cwd):

        # resolves soft links; see textbook p. 105

        logging.debug("AbsolutePathName::path_name_to_inode_number: path: " + str(path) + ", cwd: " + str(cwd))

        i = self.general_path_to_inode_number(path, cwd)
        lookedup_inode = InodeNumber(i, self.file_name_object.raw_blocks, self.config)
        lookedup_inode.inode_number_to_inode()

        if lookedup_inode.inode.type == self.config.inode_type_sym:
            logging.debug("AbsolutePathName::path_name_to_inode_number: inode is symlink: " + str(i))
            # read block with target string from RawBlocks
            block_number = lookedup_inode.inode.block_numbers[0]
            block = self.file_name_object.raw_blocks.get(block_number)
            # extract slice with length of target string
            target_slice = block[0:lookedup_inode.inode.size]
            rest = target_slice.decode()
            logging.debug("AbsolutePathName::path_name_to_inode_number: rest: " + rest)
            i = self.general_path_to_inode_number(rest, cwd)

        return i

    def hardlink(self, target, name, cwd):

        logging.debug("AbsolutePathName::hardlink: target: " + str(target) + ", name: " + str(name) + ", cwd: " + str(cwd))

        target_inode_number = self.path_name_to_inode_number(target, cwd)
        if target_inode_number == -1:
            logging.debug("AbsolutePathName::hardlink: target does not exist")
            return -1, "ERROR_LINK_TARGET_DOESNOT_EXIST"

        cwd_inode = InodeNumber(cwd, self.file_name_object.raw_blocks, self.config)
        cwd_inode.inode_number_to_inode()
        if cwd_inode.inode.type != self.config.inode_type_dir:
            logging.debug("AbsolutePathName::hardlink: cwd is not a directory")
            return -1, "ERROR_LINK_NOT_DIRECTORY"

        # Find available slot in directory data block
        fileentry_position = self.file_name_object.find_available_file_entry(cwd)
        if fileentry_position == -1:
            logging.debug("AbsolutePathName::hardlink: no entry available for another link")
            return -1, "ERROR_LINK_DATA_BLOCK_NOT_AVAILABLE"

        # Ensure it's not a duplicate - if Lookup returns anything other than -1
        if self.file_name_object.lookup(name, cwd) != -1:
            logging.debug("AbsolutePathName::hardlink: name already exists")
            return -1, "ERROR_LINK_ALREADY_EXISTS"

        # Ensure target is a file
        target_obj = InodeNumber(target_inode_number, self.file_name_object.raw_blocks, self.config)
        target_obj.inode_number_to_inode()
        if target_obj.inode.type != self.config.inode_type_file:
            logging.debug("AbsolutePathName::hardlink: target must be a file")
            return -1, "ERROR_LINK_TARGET_NOT_FILE"

        # Add to directory (filename,inode) table
        self.file_name_object.insert_filename_inode_number(cwd_inode, name, target_inode_number)

        # Update refcnt of target and write to file system
        target_inode_number_object = InodeNumber(target_inode_number, self.file_name_object.raw_blocks, self.config)
        target_inode_number_object.inode_number_to_inode()
        target_inode_number_object.inode.refcnt += 1
        target_inode_number_object.store_inode()

        # Update refcnt of directory and write to file system
        cwd_inode.inode.refcnt += 1
        cwd_inode.store_inode()

        return 0, "SUCCESS"

    def symlink(self, target, name, cwd):

        logging.debug("AbsolutePathName::symlink: target: " + str(target) + ", name: " + str(name) + ", cwd: " + str(cwd))

        target_inode_number = self.path_name_to_inode_number(target, cwd)
        if target_inode_number == -1:
            logging.debug("AbsolutePathName::symlink: target does not exist")
            return -1, "ERROR_SYMLINK_TARGET_DOESNOT_EXIST"

        cwd_inode = InodeNumber(cwd, self.file_name_object.raw_blocks, self.config)
        cwd_inode.inode_number_to_inode()
        if cwd_inode.inode.type != self.config.inode_type_dir:
            logging.debug("AbsolutePathName::symlink: cwd is not a directory")
            return -1, "ERROR_SYMLINK_NOT_DIRECTORY"

        # Find available slot in directory data block
        fileentry_position = self.file_name_object.find_available_file_entry(cwd)
        if fileentry_position == -1:
            logging.debug("AbsolutePathName::symlink: no entry available for another link")
            return -1, "ERROR_SYMLINK_DATA_BLOCK_NOT_AVAILABLE"

        # Ensure it's not a duplicate - if Lookup returns anything other than -1
        if self.file_name_object.lookup(name, cwd) != -1:
            logging.debug("AbsolutePathName::symlink: name already exists")
            return -1, "ERROR_SYMLINK_ALREADY_EXISTS"

        # Find if there is an available inode
        inode_position = self.file_name_object.find_available_inode()
        if inode_position == -1:
            logging.debug("ERROR_SYMLINK_INODE_NOT_AVAILABLE")
            return -1, "ERROR_SYMLINK_INODE_NOT_AVAILABLE"

        # ensure target size fits in a block
        if len(target) > self.config.block_size:
            logging.debug("ERROR_SYMLINK_TARGET_EXCEEDS_BLOCK_SIZE")
            return -1, "ERROR_SYMLINK_TARGET_EXCEEDS_BLOCK_SIZE"

        # Create new Inode for symlink
        symlink_inode = InodeNumber(inode_position, self.file_name_object.raw_blocks, self.config)
        symlink_inode.inode_number_to_inode()
        symlink_inode.inode.type = self.config.inode_type_sym
        symlink_inode.inode.size = len(target)
        symlink_inode.inode.refcnt = 1

        # Allocate one data block and set as first entry in block_numbers[]
        symlink_inode.inode.block_numbers[0] = self.file_name_object.raw_blocks.allocate_data_block()
        symlink_inode.store_inode()

        # Add to directory's (filename,inode) table
        self.file_name_object.insert_filename_inode_number(cwd_inode, name, inode_position)

        # Write target path to block
        # first, we read the whole block from raw storage
        block_number = symlink_inode.inode.block_numbers[0]
        block = self.file_name_object.raw_blocks.get(block_number)
        # copy slice of data into the right position in the block
        stringbyte = bytearray(target, "utf-8")
        block[0:len(target)] = stringbyte
        # now write modified block back to disk
        self.file_name_object.raw_blocks.put(block_number, block)

        # Update refcnt of directory and write to file system
        cwd_inode.inode.refcnt += 1
        cwd_inode.store_inode()

        return 0, "SUCCESS"

    def _path_to_parent_and_name(self, path, cwd):
        """Split path into (parent_dir_inode, basename).

        Returns parent_dir_inode = -1 if the prefix does not resolve to a directory.
        """
        logging.debug("AbsolutePathName::_path_to_parent_and_name: path: " + str(path) + ", cwd: " + str(cwd))

        if "/" not in path:
            return cwd, path

        last_sep = path.rfind("/")
        # If the path starts with "/" and has no other separator (e.g. "/foo"),
        # prefix is the root.
        if last_sep == 0:
            prefix = "/"
        else:
            prefix = path[:last_sep]
        name = path[last_sep + 1:]

        parent_inode = self.general_path_to_inode_number(prefix, cwd)
        if parent_inode == -1:
            return -1, name

        parent_obj = InodeNumber(parent_inode, self.file_name_object.raw_blocks, self.config)
        parent_obj.inode_number_to_inode()
        if parent_obj.inode.type != self.config.inode_type_dir:
            return -1, name

        return parent_inode, name

    def mv(self, source, target, cwd):

        logging.debug("AbsolutePathName::mv: source: " + str(source) + ", target: " + str(target) + ", cwd: " + str(cwd))

        # Resolve source (do not follow trailing symlink)
        source_inode = self.general_path_to_inode_number(source, cwd)
        if source_inode == -1:
            logging.debug("AbsolutePathName::mv: source does not exist")
            return -1, "ERROR_MV_SOURCE_NOT_FOUND"

        source_obj = InodeNumber(source_inode, self.file_name_object.raw_blocks, self.config)
        source_obj.inode_number_to_inode()

        # Source must be a file or symlink
        if source_obj.inode.type == self.config.inode_type_dir:
            logging.debug("AbsolutePathName::mv: source is a directory")
            return -1, "ERROR_MV_SOURCE_DIR"

        # Decompose source path for the final unlink
        source_dir, source_name = self._path_to_parent_and_name(source, cwd)

        # Resolve target
        target_inode = self.general_path_to_inode_number(target, cwd)

        if target_inode != -1:
            target_obj = InodeNumber(target_inode, self.file_name_object.raw_blocks, self.config)
            target_obj.inode_number_to_inode()

            if target_obj.inode.type == self.config.inode_type_sym:
                logging.debug("AbsolutePathName::mv: target is a symlink")
                return -1, "ERROR_MV_TARGET_SYMLINK"

            if target_obj.inode.type == self.config.inode_type_file:
                target_dir, target_name = self._path_to_parent_and_name(target, cwd)
                self.file_operations_object.unlink(target_dir, target_name)
                self.file_operations_object.link(target_name, source_inode, target_dir)
                self.file_operations_object.unlink(source_dir, source_name)
                return 0, "SUCCESS"

            if target_obj.inode.type == self.config.inode_type_dir:
                self.file_operations_object.link(source_name, source_inode, target_inode)
                self.file_operations_object.unlink(source_dir, source_name)
                return 0, "SUCCESS"

        # Target does not exist
        prefix_inode, new_name = self._path_to_parent_and_name(target, cwd)
        if prefix_inode == -1:
            logging.debug("AbsolutePathName::mv: target prefix not found")
            return -1, "ERROR_MV_TARGET_NOT_FOUND"

        self.file_operations_object.link(new_name, source_inode, prefix_inode)
        self.file_operations_object.unlink(source_dir, source_name)
        return 0, "SUCCESS"
