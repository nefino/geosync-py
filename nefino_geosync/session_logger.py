"""Session logging utility that captures all stdout/stderr to timestamped log files."""

import os
import sys
from .storage import get_app_directory
from datetime import datetime
from typing import TextIO


class TeeStream:
    """A stream that writes to multiple outputs (console + log file)."""

    def __init__(self, original_stream: TextIO, log_file: TextIO, stream_name: str) -> None:
        self.original_stream = original_stream
        self.log_file = log_file
        self.stream_name = stream_name

    def write(self, text: str) -> None:
        # Write to original stream (console)
        self.original_stream.write(text)

        # Write to log file with stream prefix for clarity
        if text.strip():  # Only add prefix for non-empty content
            timestamp = datetime.now().strftime('%H:%M:%S')
            self.log_file.write(f'[{timestamp}] [{self.stream_name}] {text}')
        else:
            self.log_file.write(text)

        # Ensure immediate writing
        self.original_stream.flush()
        self.log_file.flush()

    def flush(self) -> None:
        self.original_stream.flush()
        self.log_file.flush()

    def __getattr__(self, name):
        # Delegate any other attributes to the original stream
        return getattr(self.original_stream, name)


class SessionLogger:
    """Manages session-wide logging to timestamped files."""

    def __init__(self) -> None:
        self.log_file = None
        self.original_stdout = None
        self.original_stderr = None
        self.started = False

    def start_logging(self) -> None:
        """Start capturing stdout and stderr to a timestamped log file."""
        if self.started:
            return

        # Create timestamped log file name
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_filename = f'nefino-geosync_{timestamp}.log'
        log_path = os.path.join(get_app_directory(), log_filename)

        # Open log file
        self.log_file = open(log_path, 'w', encoding='utf-8')

        # Write session header
        self.log_file.write('=== Nefino GeoSync Session Log ===\n')
        self.log_file.write(f'Started: {datetime.now().isoformat()}\n')
        self.log_file.write(f'Log file: {log_path}\n')
        self.log_file.write('=' * 50 + '\n\n')

        # Store original streams
        self.original_stdout = sys.stdout
        self.original_stderr = sys.stderr

        # Replace with tee streams
        sys.stdout = TeeStream(self.original_stdout, self.log_file, 'STDOUT')
        sys.stderr = TeeStream(self.original_stderr, self.log_file, 'STDERR')

        self.started = True
        print(f'Session logging started: {log_path}')

    def stop_logging(self) -> None:
        """Stop logging and restore original streams."""
        if not self.started:
            return

        print('Session logging stopped.')

        # Restore original streams
        sys.stdout = self.original_stdout
        sys.stderr = self.original_stderr

        # Write session footer and close log file
        if self.log_file:
            self.log_file.write('\n' + '=' * 50 + '\n')
            self.log_file.write(f'Session ended: {datetime.now().isoformat()}\n')
            self.log_file.close()

        self.started = False


# Global session logger instance
_session_logger = SessionLogger()


def start_session_logging() -> None:
    """Start session-wide logging."""
    _session_logger.start_logging()


def stop_session_logging() -> None:
    """Stop session-wide logging."""
    _session_logger.stop_logging()
