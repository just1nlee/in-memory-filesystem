import os.path
import logging
from fsconfig import FSError
from inodenumber import InodeNumber


class FSShell:
    def __init__(self, raw_blocks, file_operations_object, absolute_path_object, config):
        self.cwd = 0
        self.file_operations_object = file_operations_object
        self.absolute_path_object = absolute_path_object
        self.raw_blocks = raw_blocks
        self.config = config

        # Dispatch table: command_name -> (handler, arg_count, usage_msg)
        # arg_count is the total number of tokens expected (including the command itself)
        self._commands = {
            'cd':            (self._cmd_cd,            2, "Error: cd requires one argument"),
            'cat':           (self._cmd_cat,           2, "Error: cat requires one argument"),
            'ls':            (self._cmd_ls,            1, None),
            'showblock':     (self._cmd_showblock,     2, "Error: showblock requires one argument"),
            'showblockslice':(self._cmd_showblockslice,4, "Error: showblockslice requires three arguments"),
            'showinode':     (self._cmd_showinode,     2, "Error: showinode requires one argument"),
            'showfsconfig':  (self._cmd_showfsconfig,  1, "Error: showfsconfig do not require argument"),
            'load':          (self._cmd_load,          2, "Error: load requires 1 argument"),
            'save':          (self._cmd_save,          2, "Error: save requires 1 argument"),
            'mkdir':         (self._cmd_mkdir,         2, "Error: mkdir requires one argument"),
            'create':        (self._cmd_create,        2, "Error: create requires one argument"),
            'append':        (self._cmd_append,        3, "Error: append requires two arguments"),
            'slice':         (self._cmd_slice,         4, "Error: slice requires three arguments"),
            'mirror':        (self._cmd_mirror,        2, "Error: mirror requires one argument"),
            'rm':            (self._cmd_rm,            2, "Error: rm requires one argument"),
            'lnh':           (self._cmd_lnh,           3, "Error: lnh requires two arguments"),
            'lns':           (self._cmd_lns,           3, "Error: lns requires two arguments"),
            'mv':            (self._cmd_mv,            3, "Error: mv requires two arguments"),
        }

    def _cmd_showfsconfig(self):
        self.config.print_config()
        return 0

    def _cmd_showinode(self, i):
        try:
            i = int(i)
        except ValueError:
            print('Error: ' + i + ' not a valid Integer')
            return -1
        if i < 0 or i >= self.config.max_num_inodes:
            print('Error: inode number ' + str(i) + ' not in valid range [0, ' + str(self.config.max_num_inodes - 1) + ']')
            return -1
        inobj = InodeNumber(i, self.raw_blocks, self.config)
        inobj.inode_number_to_inode()
        inobj.inode.print_inode()
        return 0

    def _cmd_load(self, dumpfilename):
        if not os.path.isfile(dumpfilename):
            print("Error: Please provide valid file")
            return -1
        self.raw_blocks.load_from_dump(dumpfilename)
        self.cwd = 0
        return 0

    def _cmd_save(self, dumpfilename):
        self.raw_blocks.dump_to_disk(dumpfilename)
        return 0

    def _cmd_showblock(self, n):
        try:
            n = int(n)
        except ValueError:
            print('Error: ' + n + ' not a valid Integer')
            return -1
        if n < 0 or n >= self.config.total_num_blocks:
            print('Error: block number ' + str(n) + ' not in valid range [0, ' + str(self.config.total_num_blocks - 1) + ']')
            return -1
        print('Block (showing any string snippets in block the block) [' + str(n) + '] : \n' + str(
            (self.raw_blocks.get(n).decode(encoding='UTF-8', errors='ignore'))))
        print('Block (showing raw hex data in block) [' + str(n) + '] : \n' + str((self.raw_blocks.get(n).hex())))
        return 0

    def _cmd_showblockslice(self, n, start, end):
        try:
            n = int(n)
        except ValueError:
            print('Error: ' + n + ' not a valid Integer')
            return -1
        try:
            start = int(start)
        except ValueError:
            print('Error: ' + start + ' not a valid Integer')
            return -1
        try:
            end = int(end)
        except ValueError:
            print('Error: ' + end + ' not a valid Integer')
            return -1
        if n < 0 or n >= self.config.total_num_blocks:
            print('Error: block number ' + str(n) + ' not in valid range [0, ' + str(self.config.total_num_blocks - 1) + ']')
            return -1
        if start < 0 or start >= self.config.block_size:
            print('Error: start ' + str(start) + 'not in valid range [0, ' + str(self.config.block_size - 1) + ']')
            return -1
        if end < 0 or end >= self.config.block_size or end <= start:
            print('Error: end ' + str(end) + 'not in valid range [0, ' + str(self.config.block_size - 1) + ']')
            return -1
        wholeblock = self.raw_blocks.get(n)
        print('Block (raw hex block) [' + str(n) + '] : \n' + str((wholeblock[start:end + 1].hex())))
        return 0

    def _cmd_cd(self, dir_name):
        i = self.absolute_path_object.path_name_to_inode_number(dir_name, self.cwd)
        if i == -1:
            print("Error: not found\n")
            return -1
        inobj = InodeNumber(i, self.raw_blocks, self.config)
        inobj.inode_number_to_inode()
        if inobj.inode.type != self.config.inode_type_dir:
            print("Error: not a directory\n")
            return -1
        self.cwd = i

    def _cmd_ls(self):
        inobj = InodeNumber(self.cwd, self.raw_blocks, self.config)
        inobj.inode_number_to_inode()
        block_index = 0
        while block_index <= (inobj.inode.size // self.config.block_size):
            block = self.raw_blocks.get(inobj.inode.block_numbers[block_index])
            if block_index == (inobj.inode.size // self.config.block_size):
                end_position = inobj.inode.size % self.config.block_size
            else:
                end_position = self.config.block_size
            current_position = 0
            while current_position < end_position:
                entryname = block[current_position:current_position + self.config.max_filename]
                entryinode = block[current_position + self.config.max_filename:current_position + self.config.file_name_direntry_size]
                entryinodenumber = int.from_bytes(entryinode, byteorder='big')
                inobj2 = InodeNumber(entryinodenumber, self.raw_blocks, self.config)
                inobj2.inode_number_to_inode()
                if inobj2.inode.type == self.config.inode_type_dir:
                    print("[" + str(inobj2.inode.refcnt) + "]:" + entryname.decode() + "/")
                elif inobj2.inode.type == self.config.inode_type_sym:
                    sym_block_number = inobj2.inode.block_numbers[0]
                    sym_block = self.raw_blocks.get(sym_block_number)
                    target_slice = sym_block[0:inobj2.inode.size]
                    target = target_slice.decode()
                    print("[" + str(inobj2.inode.refcnt) + "]:" + entryname.decode() + "@ -> " + target)
                else:
                    print("[" + str(inobj2.inode.refcnt) + "]:" + entryname.decode())
                current_position += self.config.file_name_direntry_size
            block_index += 1
        return 0

    def _cmd_cat(self, filename):
        i = self.absolute_path_object.path_name_to_inode_number(filename, self.cwd)
        if i == -1:
            print("Error: not found\n")
            return -1
        inobj = InodeNumber(i, self.raw_blocks, self.config)
        inobj.inode_number_to_inode()
        if inobj.inode.type != self.config.inode_type_file:
            print("Error: not a file\n")
            return -1
        data, errorcode = self.file_operations_object.read(i, 0, self.config.max_file_size)
        if data == -1:
            print("Error: " + errorcode)
            return -1
        print(data.decode())
        return 0

    def _cmd_mkdir(self, dir_name):
        i, errorcode = self.file_operations_object.create(self.cwd, dir_name, self.config.inode_type_dir)
        if i == -1:
            print("Error: " + errorcode + "\n")
            return -1
        return 0

    def _cmd_create(self, file_name):
        i, errorcode = self.file_operations_object.create(self.cwd, file_name, self.config.inode_type_file)
        if i == -1:
            print("Error: " + errorcode + "\n")
            return -1
        return 0

    def _cmd_append(self, filename, string):
        i = self.absolute_path_object.path_name_to_inode_number(filename, self.cwd)
        if i == -1:
            print("Error: not found\n")
            return -1
        inobj = InodeNumber(i, self.raw_blocks, self.config)
        inobj.inode_number_to_inode()
        if inobj.inode.type != self.config.inode_type_file:
            print("Error: not a file\n")
            return -1
        written, errorcode = self.file_operations_object.write(i, inobj.inode.size, bytearray(string, "utf-8"))
        if written == -1:
            print("Error: " + errorcode)
            return -1
        print("Successfully appended " + str(written) + " bytes.")
        return 0

    def _cmd_slice(self, filename, offset, count):
        try:
            offset = int(offset)
        except ValueError:
            print('Error: ' + offset + ' not a valid Integer')
            return -1
        try:
            count = int(count)
        except ValueError:
            print('Error: ' + count + ' not a valid Integer')
            return -1
        i = self.absolute_path_object.path_name_to_inode_number(filename, self.cwd)
        if i == -1:
            print("Error: not found\n")
            return -1
        inobj = InodeNumber(i, self.raw_blocks, self.config)
        inobj.inode_number_to_inode()
        if inobj.inode.type != self.config.inode_type_file:
            print("Error: not a file\n")
            return -1
        data, errorcode = self.file_operations_object.slice_file(i, offset, count)
        if data == -1:
            print("Error: " + errorcode)
            return -1
        return 0

    def _cmd_mirror(self, filename):
        i = self.absolute_path_object.path_name_to_inode_number(filename, self.cwd)
        if i == -1:
            print("Error: not found\n")
            return -1
        inobj = InodeNumber(i, self.raw_blocks, self.config)
        inobj.inode_number_to_inode()
        if inobj.inode.type != self.config.inode_type_file:
            print("Error: not a file\n")
            return -1
        data, errorcode = self.file_operations_object.mirror(i)
        if data == -1:
            print("Error: " + errorcode)
            return -1
        return 0

    def _cmd_lnh(self, target, name):
        i, errorcode = self.absolute_path_object.hardlink(target, name, self.cwd)
        if i == -1:
            print("Error: " + errorcode + "\n")
            return -1
        return 0

    def _cmd_lns(self, target, name):
        i, errorcode = self.absolute_path_object.symlink(target, name, self.cwd)
        if i == -1:
            print("Error: " + errorcode + "\n")
            return -1
        return 0

    def _cmd_mv(self, source, target):
        i, errorcode = self.absolute_path_object.mv(source, target, self.cwd)
        if i == -1:
            print("Error: " + errorcode + "\n")
            return -1
        return 0

    def _cmd_rm(self, filename):
        i, errorcode = self.file_operations_object.unlink(self.cwd, filename)
        if i == -1:
            print("Error: " + errorcode + "\n")
            return -1
        return 0

    def interpreter(self):
        while True:
            command = input("[cwd=" + str(self.cwd) + "]%")
            splitcmd = command.split()
            if len(splitcmd) == 0:
                continue
            cmd_name = splitcmd[0]

            if cmd_name == "exit":
                return

            if cmd_name not in self._commands:
                print("command " + cmd_name + " not valid.\n")
                continue

            handler, arg_count, usage_msg = self._commands[cmd_name]
            if len(splitcmd) != arg_count:
                print(usage_msg)
                continue

            try:
                self.raw_blocks.acquire()
                handler(*splitcmd[1:])
            except FSError as e:
                print("Error: " + str(e))
            finally:
                self.raw_blocks.release()
