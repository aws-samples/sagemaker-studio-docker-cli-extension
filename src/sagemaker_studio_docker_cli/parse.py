import argparse

class ParseArgs():
    """
    Parsing Arguments class
    """
    def __init__(self):
        """
        """
        parser = argparse.ArgumentParser(prog="sagemaker_studio_docker_cli")
        commands = [
            "create-host",
            "terminate-current-host",
            "terminate-host"
        ]
        sub_args = {
            "create-host": [
                ("--instance-type", True),
                ("--subnet-id", False)
            ],
            "terminate-current-host": [],
            "terminate-host": [
                ("--instance-id", True)
            ]
        }
        command_parser = parser.add_subparsers(title="commands", dest=str(commands), required=True)
        arg_commands = {}
        for command in commands:
            arg_commands[command] = command_parser.add_parser(command)
            arg_commands[command].set_defaults(func=command)
            for sub_arg, required in sub_args[command]:
                arg_commands[command].add_argument(sub_arg, required=required)
        args = parser.parse_args()
        self.parser = parser
        self.args = args
