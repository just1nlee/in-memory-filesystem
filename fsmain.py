import logging
import argparse

from fsconfig import configure_fs_constants
from block import DiskBlocks
from filename import FileName
from fileoperations import FileOperations
from absolutepath import AbsolutePathName
from shell import FSShell


if __name__ == "__main__":

    # Initialize file for logging
    # Change logging level to INFO to remove debugging messages
    logging.basicConfig(filename='memoryfs.log', filemode='w', level=logging.DEBUG)

    # Redirect INFO logs to console as well
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    logging.getLogger().addHandler(console_handler)

    # Construct the argument parser
    ap = argparse.ArgumentParser()
    ap.add_argument('-nb', '--total_num_blocks', type=int, help='an integer value')
    ap.add_argument('-bs', '--block_size', type=int, help='an integer value')
    ap.add_argument('-ni', '--max_num_inodes', type=int, help='an integer value')
    ap.add_argument('-is', '--inode_size', type=int, help='an integer value')
    ap.add_argument('-cid', '--client_id', type=int, help='an integer value')
    ap.add_argument('-port', '--port', type=int, help='an integer value')
    ap.add_argument('-cmsg', '--cmsg', type=int, help='1=print cache messages, 0=suppress')

    # Other than FS args, consecutive args will be captured in by 'arg' as list
    ap.add_argument('arg', nargs='*')

    # Parse arguments
    args = ap.parse_args()

    # Initialize file system configuration
    config = configure_fs_constants(args)

    # Initialize empty file system data in raw storage
    raw_blocks = DiskBlocks(config)

    # Create a FileName object and initialize the root's inode
    # (only the cid=0 client initializes; other clients attach to existing FS state)
    file_object = FileName(raw_blocks, config)
    if config.cid == 0:
        file_object.init_root_inode()

    # Create a FileOperations object
    file_operations_object = FileOperations(file_object, config)

    # Create an AbsolutePathName object for path resolution
    absolute_path_object = AbsolutePathName(file_object, file_operations_object, config)

    # Run the interactive shell interpreter
    myshell = FSShell(raw_blocks, file_operations_object, absolute_path_object, config)
    myshell.interpreter()
