import pickle, logging
import xmlrpc.client, socket, time
from fsconfig import BlockOutOfRange, InvalidOperation


class DiskBlocks:
    def __init__(self, config):
        self.config = config

        # Initialize clientID
        if config.cid >= 0 and config.cid < config.max_clients:
            self.client_id = config.cid
        else:
            raise InvalidOperation('DiskBlocks::__init__: Must specify valid cid')

        # Initialize XML-RPC client connection to raw block server
        server_url = 'http://' + config.server_address + ':' + str(config.port)
        self.block_server = xmlrpc.client.ServerProxy(server_url, use_builtin_types=True)
        socket.setdefaulttimeout(config.socket_timeout)

        # Initialize block cache empty
        self.blockcache = {}

        # Initialize RSM request ID counter for duplicate detection
        self.rsm_request_id = 0

    def put(self, block_number, block_data):
        logging.debug(
            'DiskBlocks::put: block number ' + str(block_number) + ' len ' + str(len(block_data)) + '\n' + str(block_data.hex()))

        if len(block_data) > self.config.block_size:
            raise BlockOutOfRange('DiskBlocks::put: Block larger than block_size: ' + str(len(block_data)))

        if block_number in range(0, self.config.total_num_blocks):
            putdata = bytearray(block_data.ljust(self.config.block_size, b'\x00'))
            # Call Put() on the server with retry on timeout
            rpcretry = True
            while rpcretry:
                rpcretry = False
                try:
                    ret = self.block_server.Put(block_number, putdata)
                except socket.timeout:
                    print("SERVER_TIMED_OUT")
                    time.sleep(self.config.retry_interval)
                    rpcretry = True
            # Update block cache (write-through)
            if self.config.cmsg:
                print('CACHE_WRITE_THROUGH ' + str(block_number))
            self.blockcache[block_number] = putdata
            # Flag this client as the last writer
            # unless this is a write to the reserved blocks (lock or last-writer)
            if block_number < self.config.total_num_blocks - 2:
                last_writer_block = self.config.total_num_blocks - 2
                updated_block = bytearray(self.config.block_size)
                updated_block[0] = self.client_id
                rpcretry = True
                while rpcretry:
                    rpcretry = False
                    try:
                        self.block_server.Put(last_writer_block, updated_block)
                    except socket.timeout:
                        print("SERVER_TIMED_OUT")
                        time.sleep(self.config.retry_interval)
                        rpcretry = True
            if ret == -1:
                raise InvalidOperation('DiskBlocks::put: Server returns error')
            return 0
        else:
            raise BlockOutOfRange('DiskBlocks::put: Block out of range: ' + str(block_number))

    def get(self, block_number):
        logging.debug('DiskBlocks::get: ' + str(block_number))
        if block_number in range(0, self.config.total_num_blocks):
            # Don't look up cache for last two reserved blocks
            if (block_number < self.config.total_num_blocks - 2) and (block_number in self.blockcache):
                if self.config.cmsg:
                    print('CACHE_HIT ' + str(block_number))
                data = self.blockcache[block_number]
            else:
                if self.config.cmsg:
                    print('CACHE_MISS ' + str(block_number))
                rpcretry = True
                while rpcretry:
                    rpcretry = False
                    try:
                        data = self.block_server.Get(block_number)
                    except socket.timeout:
                        print("SERVER_TIMED_OUT")
                        time.sleep(self.config.retry_interval)
                        rpcretry = True
                # Add to cache
                self.blockcache[block_number] = data
            return bytearray(data)

        raise BlockOutOfRange('DiskBlocks::get: Block number larger than total_num_blocks: ' + str(block_number))

    ## RSM: read and set memory equivalent

    def rsm(self, block_number):
        logging.debug('DiskBlocks::rsm: ' + str(block_number))
        if block_number in range(0, self.config.total_num_blocks):
            # Generate a unique request ID for duplicate detection
            request_id = str(self.client_id) + "_" + str(self.rsm_request_id)
            self.rsm_request_id += 1
            rpcretry = True
            while rpcretry:
                rpcretry = False
                try:
                    data = self.block_server.RSM(block_number, request_id)
                except socket.timeout:
                    print("SERVER_TIMED_OUT")
                    time.sleep(self.config.retry_interval)
                    rpcretry = True
            return bytearray(data)

        raise BlockOutOfRange('DiskBlocks::rsm: Block number larger than total_num_blocks: ' + str(block_number))

    ## Acquire and Release using a disk block lock

    def acquire(self):
        logging.debug('DiskBlocks::acquire')
        rsm_block = self.config.total_num_blocks - 1
        lockvalue = self.rsm(rsm_block)
        logging.debug("RSM_BLOCK Lock value: " + str(lockvalue))
        while lockvalue[0] == 1:  # test just first byte of block to check if RSM_LOCKED
            logging.debug("acquire: spinning...")
            lockvalue = self.rsm(rsm_block)
        # Once the lock is acquired, check if need to invalidate cache
        self.check_and_invalidate_cache()
        return 0

    def release(self):
        logging.debug('DiskBlocks::release')
        rsm_block = self.config.total_num_blocks - 1
        # Put a zero-filled block to release lock
        self.put(rsm_block, bytearray(self.config.rsm_unlocked.ljust(self.config.block_size, b'\x00')))
        return 0

    def check_and_invalidate_cache(self):
        last_writer_block = self.config.total_num_blocks - 2
        last_writer = self.get(last_writer_block)
        # If ID of last writer is not self, invalidate and update
        if last_writer[0] != self.client_id:
            if self.config.cmsg:
                print("CACHE_INVALIDATED")
            self.blockcache = {}
            updated_block = bytearray(self.config.block_size)
            updated_block[0] = self.client_id
            self.put(last_writer_block, updated_block)

    def allocate_data_block(self):
        logging.debug('DiskBlocks::allocate_data_block: ')
        for block_number in range(self.config.data_blocks_offset, self.config.total_num_blocks):
            bitmap_block = self.config.freebitmap_block_offset + (block_number // self.config.block_size)
            block = self.get(bitmap_block)
            byte_bitmap = block[block_number % self.config.block_size]
            if byte_bitmap == 0:
                block[block_number % self.config.block_size] = 1
                self.put(bitmap_block, block)
                logging.debug('DiskBlocks::allocate_data_block: allocated ' + str(block_number))
                return block_number

        raise InvalidOperation('DiskBlocks::allocate_data_block: no free data blocks available')

    def free_data_block(self, block_number):
        logging.debug('DiskBlocks::free_data_block: ' + str(block_number))
        if block_number == 0:
            return
        bitmap_block = self.config.freebitmap_block_offset + (block_number // self.config.block_size)
        block = self.get(bitmap_block)
        block[block_number % self.config.block_size] = 0
        self.put(bitmap_block, block)

    def dump_to_disk(self, filename):
        logging.info("DiskBlocks::dump_to_disk: Dumping pickled blocks to file " + filename)
        file = open(filename, 'wb')
        file_system_constants = "BS_" + str(self.config.block_size) + "_NB_" + str(self.config.total_num_blocks) + "_IS_" + str(self.config.inode_size) \
                                + "_MI_" + str(self.config.max_num_inodes) + "_MF_" + str(self.config.max_filename) + "_IDS_" + str(self.config.inode_number_direntry_size)
        pickle.dump(file_system_constants, file)
        # Fetch all blocks from server and pickle
        all_blocks = []
        for i in range(0, self.config.total_num_blocks):
            all_blocks.append(self.get(i))
        pickle.dump(all_blocks, file)
        file.close()

    def load_from_dump(self, filename):
        logging.info("DiskBlocks::load_from_dump: Reading blocks from pickled file " + filename)
        file = open(filename, 'rb')
        file_system_constants = "BS_" + str(self.config.block_size) + "_NB_" + str(self.config.total_num_blocks) + "_IS_" + str(self.config.inode_size) \
                                + "_MI_" + str(self.config.max_num_inodes) + "_MF_" + str(self.config.max_filename) + "_IDS_" + str(self.config.inode_number_direntry_size)
        try:
            read_file_system_constants = pickle.load(file)
            if file_system_constants != read_file_system_constants:
                print('DiskBlocks::load_from_dump Error: File System constants of File :' + read_file_system_constants + ' do not match with current file system constants :' + file_system_constants)
                return -1
            block = pickle.load(file)
            for i in range(0, self.config.total_num_blocks):
                self.put(i, block[i])
            return 0
        except TypeError:
            print("DiskBlocks::load_from_dump: Error: File not in proper format, encountered type error ")
            return -1
        except EOFError:
            print("DiskBlocks::load_from_dump: Error: File not in proper format, encountered EOFError error ")
            return -1
        finally:
            file.close()

    def print_blocks(self, tag, min_block, max_block):
        print('#### Raw disk blocks: ' + tag)
        for i in range(min_block, max_block):
            print('Block [' + str(i) + '] : ' + str((self.get(i)).hex()))
