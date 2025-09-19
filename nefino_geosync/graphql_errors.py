import html
import json
import re
import sys
from .parse_args import parse_args
from datetime import datetime
from prompt_toolkit import print_formatted_text
from prompt_toolkit.formatted_text import HTML


def check_errors(data: dict, context: str = None) -> None:
    """Check for errors in a GraphQL response."""
    args = parse_args()
    if 'errors' in data:
        if args.verbose:
            pp('<b>GraphQL operation with errors:</b> ' + html.escape(json.dumps(data, indent=4)))

        if is_token_invalid(data):
            pp(
                '<b fg="red">ERROR:</b> Invalid token. Please run <b>nefino-geosync --configure</b> and double-check your API key.'
            )
        else:
            if not args.verbose:
                try:
                    pp(
                        '<b>Received GraphQL error from server:</b> '
                        + html.escape(json.dumps(data['errors'], indent=4))
                    )
                except Exception as e:
                    print(e)
                    print(data['errors'])

            # Add context information if provided
            if context:
                pp(f'<b fg="red">Context:</b> {context}')

            if not args.verbose:
                pp("""<b fg="red">ERROR:</b> A GraphQL error occurred. Run with <b>--verbose</b> to see more information.
If this error persists, please contact Nefino support: https://www.nefino.de/kontakt
Exiting due to the above error.""")
            else:
                pp('<b fg="red">ERROR:</b> A GraphQL error occurred.')
                pp(
                    '<b fg="red">If this error persists, please contact Nefino support: https://www.nefino.de/kontakt</b>'
                )
                pp('<b fg="red">Exiting due to the above error.</b>')

        sys.exit(1)


def pp(to_print: str) -> None:
    # Display formatted text in console
    print_formatted_text(HTML(to_print))

    # For logging: check if stdout has been replaced by TeeStream
    # If so, write plain text directly to the log file to avoid duplication
    if hasattr(sys.stdout, 'log_file'):
        # Remove HTML tags for plain text logging
        plain_text = re.sub(r'<[^>]+>', '', to_print)

        timestamp = datetime.now().strftime('%H:%M:%S')
        sys.stdout.log_file.write(f'[{timestamp}] [STDOUT] {plain_text}\n')
        sys.stdout.log_file.flush()


def is_token_invalid(data: dict) -> bool:
    """Check if the token is invalid."""
    try:
        if data['errors'][0]['extensions']['nefino_type'] == 'AuthTokenInvalid':
            return True
    except KeyError:
        return False
    return False
