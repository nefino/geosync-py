from prompt_toolkit import print_formatted_text
from prompt_toolkit.formatted_text import HTML
from .parse_args import parse_args
import json

def check_errors(data: dict) -> None:
    """Check for errors in a GraphQL response."""
    args = parse_args()
    if 'errors' in data:
        if args.verbose:
            pp("<b>GraphQL operation with errors:</b> " + json.dumps(data, indent=4))

        message = data['errors'][0]['message']
        if "AnonymousUser" in message or message == "Unauthorized":
            pp('<b fg="red">ERROR:</b> Auth failed. Please run <b>nefino-geosync --configure</b> and double-check your API key.')
        else:
            if not args.verbose:
                pp("<b>Received GraphQL error from server:</b> " + json.dumps(data['errors'], indent=4))
                pp("""<b fg="red">ERROR:</b> A GraphQL error occurred. Run with <b>--verbose</b> to see more information.
Exiting due to the above error.""")
            if args.verbose:
                pp('<b fg="red">ERROR:</b> A GraphQL error occurred. Exiting due to the above error.')

        exit(1)

def pp(to_print: str):
    print_formatted_text(HTML(to_print))