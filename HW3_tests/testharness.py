import sys
import re
import subprocess
import threading
import time

# Manages server and client subprocesses, dispatches test commands.
# Each client is monitored by a daemon thread that reads its stdout and
# signals an Event when the shell prompt "[cwd=N]%" is observed. Shell
# commands block on the prompt rather than on a fixed sleep, which avoids
# race conditions between command dispatch and command completion.

servers = {}            # name -> (Popen, log_file)
clients = {}            # name -> ClientHandle
shelldelay = 10         # max seconds to wait for a single prompt; CLI-overridable

PROMPT_RE = re.compile(rb'\[cwd=\d+\]%')


class ClientHandle:
    """Wraps a client subprocess plus a reader thread that watches for the prompt."""

    def __init__(self, name, proc, log_file):
        self.name = name
        self.proc = proc
        self.log_file = log_file
        self._buf = bytearray()
        self._prompt_event = threading.Event()
        self._lock = threading.Lock()
        self._eof = False
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def _read_loop(self):
        try:
            while True:
                chunk = self.proc.stdout.read1(4096)
                if not chunk:
                    break
                try:
                    self.log_file.write(chunk.decode('utf-8', errors='replace'))
                    self.log_file.flush()
                except Exception:
                    pass
                with self._lock:
                    self._buf.extend(chunk)
                    if PROMPT_RE.search(self._buf):
                        self._prompt_event.set()
        finally:
            self._eof = True
            # Unblock any pending waiter so it doesn't hang forever
            self._prompt_event.set()

    def wait_prompt(self, timeout=None):
        """Block until the next "[cwd=N]%" prompt is seen on stdout (or timeout).

        Consumes the buffer up to and including the latest prompt so the next
        call waits for the *following* prompt. Returns True on prompt, False
        on timeout or EOF.
        """
        if timeout is None:
            timeout = shelldelay
        seen = self._prompt_event.wait(timeout=timeout)
        with self._lock:
            # Drop everything up to and including the last prompt found
            last = None
            for m in PROMPT_RE.finditer(self._buf):
                last = m
            if last is not None:
                del self._buf[:last.end()]
            self._prompt_event.clear()
            # If new bytes already contain another prompt, leave the event set
            if PROMPT_RE.search(self._buf):
                self._prompt_event.set()
        if not seen or self._eof:
            if self._eof:
                print(f"WARNING: {self.name} stdout closed (process may have exited)")
            else:
                print(f"WARNING: timed out waiting for prompt from {self.name} after {timeout}s")
            return False
        return True

    def send(self, cmd):
        try:
            self.proc.stdin.write((cmd + "\n").encode())
            self.proc.stdin.flush()
        except BrokenPipeError:
            print(f"ERROR: {self.name} pipe broken (process may have exited)")


def parse_command(line):
    """Parse a test command line and return (cmd_type, args) or None for blanks/comments."""
    line = line.strip()
    if not line or line.startswith('#'):
        return None

    m = re.match(r'(\w+)\((.+)\)', line)
    if not m:
        print(f"ERROR: Could not parse line: {line}")
        return None

    cmd = m.group(1)
    inner = m.group(2)

    # Split on first comma for commands with two args
    if ',' in inner:
        name, rest = inner.split(',', 1)
        name = name.strip()
        # Extract quoted string if present
        qm = re.search(r'"([^"]*)"', rest)
        arg = qm.group(1) if qm else rest.strip()
        return (cmd, name, arg)
    else:
        return (cmd, inner.strip(), None)


def server_start(name, args_str):
    if name in servers:
        print(f"ERROR: Server {name} already running")
        return
    log = open(f"{name}.log", "w")
    cmd = ["python3", "blockserver.py"] + args_str.split()
    print(f"Starting server {name}: {' '.join(cmd)}")
    proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
    servers[name] = (proc, log)
    # No prompt to wait for; give the server a moment to bind its socket.
    time.sleep(1)


def server_kill(name):
    if name not in servers:
        print(f"ERROR: Server {name} not found")
        return
    proc, log = servers[name]
    print(f"Killing server {name}")
    proc.terminate()
    proc.wait()
    log.close()
    del servers[name]


def client_start(name, args_str):
    if name in clients:
        print(f"ERROR: Client {name} already running")
        return
    log = open(f"{name}.log", "w")
    # -u: unbuffered stdout so the prompt flushes immediately to our pipe.
    cmd = ["python3", "-u", "fsmain.py"] + args_str.split()
    print(f"Starting client {name}: {' '.join(cmd)}")
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    handle = ClientHandle(name, proc, log)
    clients[name] = handle
    # Wait until the client prints its first prompt — only then is it ready
    # to receive shell commands. The first prompt may arrive after various
    # init output (config dump, etc.), which is why we can't use a fixed sleep.
    handle.wait_prompt()


def client_kill(name):
    if name not in clients:
        print(f"ERROR: Client {name} not found")
        return
    handle = clients[name]
    print(f"Killing client {name}")
    try:
        handle.proc.stdin.write(b"exit\n")
        handle.proc.stdin.flush()
        handle.proc.wait(timeout=5)
    except Exception:
        handle.proc.terminate()
        handle.proc.wait()
    # Reader thread exits on EOF; give it a brief moment to drain.
    handle._reader.join(timeout=2)
    handle.log_file.close()
    del clients[name]


def shell_run(name, shell_cmd):
    if name not in clients:
        print(f"ERROR: Client {name} not found")
        return
    handle = clients[name]
    print(f"  {name} << {shell_cmd}")
    handle.send(shell_cmd)
    # Block until the shell prints the next prompt — i.e. the command has
    # finished executing. Replaces the old race-prone fixed sleep.
    handle.wait_prompt()


def run_test_file(filepath):
    with open(filepath, 'r') as f:
        lines = f.readlines()

    for lineno, line in enumerate(lines, 1):
        parsed = parse_command(line)
        if parsed is None:
            continue

        cmd = parsed[0]
        name = parsed[1]
        arg = parsed[2]

        print(f"[line {lineno}] {line.strip()}")

        if cmd == 'SERVERSTART':
            server_start(name, arg)
        elif cmd == 'SERVERKILL':
            server_kill(name)
        elif cmd == 'CLIENTSTART':
            client_start(name, arg)
        elif cmd == 'CLIENTKILL':
            client_kill(name)
        elif cmd == 'SHELLRUN':
            shell_run(name, arg)
        else:
            print(f"ERROR: Unknown command: {cmd}")

    # Clean up any remaining processes
    for name in list(clients):
        print(f"Cleaning up client {name}")
        client_kill(name)
    for name in list(servers):
        print(f"Cleaning up server {name}")
        server_kill(name)

    # Generate clean log files for all client logs
    generate_clean_logs()

    print("Test complete.")


def generate_clean_logs():
    """Post-process client log files to produce clean versions."""
    import glob
    for logfile in glob.glob("C*.log"):
        # Only process client logs (C0.log, C1.log, etc.), skip clean logs
        if "_clean" in logfile:
            continue
        clean_name = logfile.replace(".log", "_clean.log")
        try:
            with open(logfile, 'r', errors='replace') as f:
                raw = f.read()
        except FileNotFoundError:
            continue

        # Remove non-printable/special characters, keeping newlines, tabs, and standard printable ASCII
        cleaned = []
        for ch in raw:
            if ch == '\n' or ch == '\t' or (32 <= ord(ch) <= 126):
                cleaned.append(ch)
        cleaned = ''.join(cleaned)

        # Add a newline after each prompt character %
        cleaned = cleaned.replace('%', '%\n')

        # Collapse runs of multiple blank lines into one
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)

        with open(clean_name, 'w') as f:
            f.write(cleaned)
        print(f"Generated {clean_name}")


if __name__ == "__main__":
    if len(sys.argv) < 2 or len(sys.argv) > 3:
        print(f"Usage: python3 {sys.argv[0]} <test_file> [shelldelay]")
        print("  shelldelay: max seconds to wait for each prompt (default 10)")
        sys.exit(1)
    if len(sys.argv) == 3:
        try:
            shelldelay = int(sys.argv[2])
        except ValueError:
            print(f"ERROR: shelldelay must be an integer, got: {sys.argv[2]}")
            sys.exit(1)
    run_test_file(sys.argv[1])
