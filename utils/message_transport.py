import os
import struct
import select
import errno

class MessagePipes:
    HEADER_SIZE = 4

    def __init__(self, read_path, write_path, write_first, max_size=30 * 1024 * 1024):
        self.read_path = read_path
        self.write_path = write_path
        self.max_size = max_size

        self.__ensure_fifo(read_path)
        self.__ensure_fifo(write_path)

        # Open both ends
        if write_first:
            self.fd_write = os.open(self.write_path, os.O_WRONLY)
            self.fd_read = os.open(self.read_path, os.O_RDONLY)
        else:
            self.fd_read = os.open(self.read_path, os.O_RDONLY)
            self.fd_write = os.open(self.write_path, os.O_WRONLY)
            

    # ---------- Low-level helpers ----------
    def __ensure_fifo(self, path):
        try:
            os.mkfifo(path)
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise

    def __write_full(self, data: bytes):
        total = 0
        while total < len(data):
            try:
                n = os.write(self.fd_write, data[total:])
                if n == 0:
                    raise RuntimeError("write returned 0")
                total += n

            except InterruptedError:
                continue  # retry

            except BrokenPipeError:
                print("Peer closed (BrokenPipe)")
                raise BrokenPipeError

    def __read_full(self, size: int) -> bytes:
        chunks = []
        total = 0

        while total < size:
            try:
                chunk = os.read(self.fd_read, size - total)
                if not chunk:
                    print("EOF: peer closed")
                    raise BrokenPipeError
                chunks.append(chunk)
                total += len(chunk)

            except InterruptedError:
                continue  # retry

        return b"".join(chunks)

    # ---------- Public API ----------
    def reinit_fd(self, write_first):
        if write_first:
            os.close(self.fd_write)
            self.fd_write = os.open(self.write_path, os.O_WRONLY)
            os.close(self.fd_read)
            self.fd_read = os.open(self.read_path, os.O_RDONLY)
        else:
            os.close(self.fd_read)
            self.fd_read = os.open(self.read_path, os.O_RDONLY)
            os.close(self.fd_write)
            self.fd_write = os.open(self.write_path, os.O_WRONLY)

    def send(self, payload: bytes):
        length = len(payload)
        if length > self.max_size:
            raise ValueError("Message too large")

        header = struct.pack("!I", length)
        self.__write_full(header)
        self.__write_full(payload)

    def recv(self, timeout=None) -> bytes:
        """
        timeout: seconds (float) or None (block forever)
        """
        if timeout is not None:
            rlist, _, _ = select.select([self.fd_read], [], [], timeout)
            if not rlist:
                raise TimeoutError("recv timeout")

        header = self.__read_full(self.HEADER_SIZE)
        (length,) = struct.unpack("!I", header)

        if length > self.max_size:
            raise RuntimeError("Invalid message size")

        return self.__read_full(length)

    def request(self, payload: bytes, timeout=None) -> bytes:
        """
        Send request and wait for response (your protocol)
        """
        self.send(payload)
        return self.recv(timeout=timeout)

    def close(self):
        try:
            os.close(self.fd_read)
        finally:
            os.close(self.fd_write)